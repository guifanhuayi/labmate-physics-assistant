from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import UUID

from openpyxl import Workbook
from sqlalchemy import func, select

from app.api import auth as auth_api
from app.auth.service import AuthService
from app.config import Settings
from app.db.models import Assignment, ClassMember, ExperimentTemplate, LabClass, RosterImport, TemplateVersion, User


def login(client, account="t0001"):
    return client.post("/api/auth/login", json={"account": account, "password": "InitialPass2026"})


def create_class(client, teacher_id):
    return client.post(
        "/api/classes",
        json={"classCode": "PHY2401", "className": "物理2401", "semester": "2026秋", "teacherId": str(teacher_id)},
    )


def test_teacher_can_create_class_preview_and_commit_csv(client, seed_user, db) -> None:
    teacher = seed_user(role="teacher", account="t0001")
    assert login(client).status_code == 200
    created_class = create_class(client, teacher.id)
    assert created_class.status_code == 201
    class_id = created_class.json()["id"]
    csv_data = "学号,姓名\n20260002,李明\n"

    preview = client.post(
        f"/api/roster-imports/preview?class_id={class_id}",
        files={"file": ("roster.csv", csv_data.encode("utf-8-sig"), "text/csv")},
    )

    assert preview.status_code == 201
    assert preview.json()["errorCount"] == 0
    committed = client.post(f"/api/roster-imports/{preview.json()['id']}/commit")
    assert committed.status_code == 200
    assert committed.json()["created"] == 1
    assert committed.json()["membershipsAdded"] == 1
    assert committed.json()["requiresEnrollment"] == 1
    db.expire_all()
    imported = db.scalar(select(User).where(User.student_number == "20260002"))
    assert imported.name == "李明"
    assert imported.enrollment_completed is False
    assert db.scalar(select(func.count(ClassMember.id))) == 1


def test_imported_roster_student_can_sign_in_with_any_demo_password(client, seed_user, monkeypatch) -> None:
    teacher = seed_user(role="teacher", account="t0001")
    seed_user(role="student", account="20269999")  # Existing but not imported.
    assert login(client).status_code == 200
    class_id = create_class(client, teacher.id).json()["id"]
    preview = client.post(
        f"/api/roster-imports/preview?class_id={class_id}",
        files={"file": ("roster.csv", "学号,姓名\n20260022,李明\n".encode("utf-8-sig"), "text/csv")},
    )
    assert preview.status_code == 201
    assert client.post(f"/api/roster-imports/{preview.json()['id']}/commit").status_code == 200

    demo_settings = Settings(demo_auth_enabled=True)
    monkeypatch.setattr(auth_api, "settings", demo_settings)
    monkeypatch.setattr(auth_api, "auth_service", AuthService(demo_settings))
    imported = client.post("/api/auth/login", json={"account": "20260022", "password": "任意演示密码!"})
    assert imported.status_code == 200
    assert imported.json()["account"] == "20260022"
    assert imported.json()["role"] == "student"
    for number in ("20260023", "20269999"):
        denied = client.post("/api/auth/login", json={"account": number, "password": "anything"})
        assert denied.status_code == 401
        assert denied.json()["error"]["code"] == "invalid_demo_credentials"


def test_roster_preview_accepts_xlsx_and_blocks_errors(client, seed_user, db) -> None:
    teacher = seed_user(role="teacher", account="t0001")
    seed_user(account="20260003", name="原姓名")
    assert login(client).status_code == 200
    class_id = create_class(client, teacher.id).json()["id"]
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["学号", "姓名"])
    sheet.append(["20260003", "冲突姓名"])
    binary = BytesIO()
    workbook.save(binary)

    preview = client.post(
        f"/api/roster-imports/preview?class_id={class_id}",
        files={"file": ("roster.xlsx", binary.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert preview.status_code == 201
    assert preview.json()["errorCount"] == 1
    blocked = client.post(f"/api/roster-imports/{preview.json()['id']}/commit")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "preview_has_errors"
    db.expire_all()
    assert db.scalar(select(func.count(ClassMember.id))) == 0


def test_legacy_class_columns_are_ignored_and_selected_class_is_authoritative(client, seed_user) -> None:
    seed_user(role="teacher", account="t0001")
    assert login(client).status_code == 200
    lab_class = client.post(
        "/api/classes",
        json={"classCode": "NH2502", "className": "能化2502", "semester": "2025秋"},
    ).json()
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["姓名", "学号", "班级"])
    sheet.append(["测试学生", "20252201001", "完全不同的班级"])
    binary = BytesIO()
    workbook.save(binary)

    preview = client.post(
        f"/api/roster-imports/preview?class_id={lab_class['id']}",
        files={"file": ("compact-roster.xlsx", binary.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert preview.status_code == 201
    assert preview.json()["errorCount"] == 0
    assert preview.json()["validCount"] == 1


def test_roster_commit_is_not_repeatable(client, seed_user) -> None:
    teacher = seed_user(role="teacher", account="t0001")
    assert login(client).status_code == 200
    class_id = create_class(client, teacher.id).json()["id"]
    csv_data = "学号,姓名\n20260004,王芳\n"
    preview = client.post(
        f"/api/roster-imports/preview?class_id={class_id}",
        files={"file": ("roster.csv", csv_data.encode("utf-8-sig"), "text/csv")},
    ).json()
    assert client.post(f"/api/roster-imports/{preview['id']}/commit").status_code == 200
    repeated = client.post(f"/api/roster-imports/{preview['id']}/commit")
    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "already_committed"


def test_student_cannot_manage_classes(client, seed_user) -> None:
    seed_user(role="student", account="20260001")
    assert login(client, "20260001").status_code == 200
    assert client.get("/api/classes").status_code == 403


def test_admin_can_list_teachers_for_class_assignment(client, seed_user) -> None:
    teacher = seed_user(role="teacher", account="t0001", name="张老师")
    seed_user(role="admin", account="admin")
    assert login(client, "admin").status_code == 200

    response = client.get("/api/teachers")

    assert response.status_code == 200
    assert response.json() == [{"id": str(teacher.id), "account": "t0001", "name": "张老师"}]


def test_teacher_can_list_students_after_roster_import(client, seed_user) -> None:
    teacher = seed_user(role="teacher", account="t0001")
    assert login(client).status_code == 200
    class_id = create_class(client, teacher.id).json()["id"]
    csv_data = "姓名,学号,班级\n李明,20260012,物理2401\n"
    preview = client.post(
        f"/api/roster-imports/preview?class_id={class_id}",
        files={"file": ("roster.csv", csv_data.encode("utf-8-sig"), "text/csv")},
    ).json()
    assert client.post(f"/api/roster-imports/{preview['id']}/commit").status_code == 200

    response = client.get(f"/api/classes/{class_id}/students")

    assert response.status_code == 200
    assert response.json()[0]["name"] == "李明"
    assert response.json()[0]["studentNumber"] == "20260012"


def test_teacher_can_delete_unassigned_class_without_deleting_student_accounts(client, seed_user, db) -> None:
    teacher = seed_user(role="teacher", account="t0001")
    assert login(client).status_code == 200
    class_id = create_class(client, teacher.id).json()["id"]
    csv_data = "姓名,学号,班级\n王芳,20260013,物理2401\n"
    preview = client.post(
        f"/api/roster-imports/preview?class_id={class_id}",
        files={"file": ("roster.csv", csv_data.encode("utf-8-sig"), "text/csv")},
    ).json()
    assert client.post(f"/api/roster-imports/{preview['id']}/commit").status_code == 200

    response = client.delete(f"/api/classes/{class_id}")

    assert response.status_code == 204
    assert client.get("/api/classes").json() == []
    db.expire_all()
    assert db.scalar(select(User).where(User.student_number == "20260013")) is not None
    assert db.scalar(select(func.count(ClassMember.id))) == 0
    assert db.scalar(select(func.count(RosterImport.id))) == 0


def test_class_with_assignment_cannot_be_deleted(client, seed_user, db) -> None:
    teacher = seed_user(role="teacher", account="t0001")
    assert login(client).status_code == 200
    class_id = create_class(client, teacher.id).json()["id"]
    now = datetime.now(UTC)
    template = ExperimentTemplate(
        name="测试模板",
        description="",
        owner_teacher_id=teacher.id,
        status="published",
        draft_schema_json={},
        created_at=now,
        updated_at=now,
    )
    db.add(template)
    db.flush()
    version = TemplateVersion(template_id=template.id, version_number=1, schema_json={}, published_at=now)
    db.add(version)
    db.flush()
    db.add(
        Assignment(
            template_version_id=version.id,
            class_id=UUID(class_id),
            title="测试任务",
            start_at=now,
            due_at=now + timedelta(days=1),
            status="open",
            created_by=teacher.id,
            created_at=now,
        )
    )
    db.commit()

    response = client.delete(f"/api/classes/{class_id}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "class_has_assignments"
    assert db.get(LabClass, UUID(class_id)) is not None
