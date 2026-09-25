from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select

from app.db.models import Assignment, AuditLog, ClassMember, LabClass, SharedDataRevision, SharedDataset, SubmissionDraft
from app.retention import purge_expired_assignments


SCHEMA = {
    "title": "阶段四测试实验",
    "steps": [{"id": "record", "title": "记录读数", "instruction": "记录小组和个人数据。", "tableId": "readings"}],
    "tables": [{
        "id": "readings", "title": "读数表", "minimumRows": 1, "maximumRows": 1,
        "fields": [
            {"key": "voltage", "label": "电压", "type": "number", "unit": "V", "required": True, "scope": "group"},
            {"key": "comment", "label": "备注", "type": "text", "unit": "", "required": False, "scope": "individual"},
        ],
        "grid": {"rows": 2, "columns": 2, "cells": [
            {"id": f"r{row + 1}c{column + 1}", "row": row, "column": column,
             "rowSpan": 1, "colSpan": 1, "kind": "label" if row == 0 else "field", "text": "",
             **({"fieldKey": "voltage" if column == 0 else "comment"} if row else {})}
            for row in range(2) for column in range(2)
        ]},
    }],
    "calculations": [], "charts": [], "checks": [], "requiredArtifacts": [],
}


def login(client, account):
    response = client.post("/api/auth/login", json={"account": account, "password": "InitialPass2026"})
    assert response.status_code == 200


def setup_assignment(client, seed_user, db, sharing=True):
    teacher = seed_user(role="teacher", account="t0001")
    first = seed_user(role="student", account="20260001")
    second = seed_user(role="student", account="20260002")
    outsider = seed_user(role="student", account="20260003")
    lab_class = LabClass(class_code="PHY4", class_name="阶段四班", semester="2026秋",
                         teacher_id=teacher.id, created_at=datetime.now(UTC))
    db.add(lab_class)
    db.flush()
    db.add_all(ClassMember(class_id=lab_class.id, user_id=user.id, joined_at=datetime.now(UTC))
               for user in (first, second))
    db.commit()
    login(client, "t0001")
    template_id = client.post("/api/templates", json={"name": "阶段四测试实验"}).json()["id"]
    assert client.put(f"/api/templates/{template_id}/draft", json={
        "name": "阶段四测试实验", "description": "", "schema": SCHEMA,
    }).status_code == 200
    version_id = client.post(f"/api/templates/{template_id}/publish").json()["id"]
    assignment = client.post("/api/assignments", json={
        "templateVersionId": version_id, "classId": str(lab_class.id), "title": "阶段四实验",
        "startAt": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        "dueAt": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "groupSharingEnabled": sharing,
    })
    assert assignment.status_code == 201, assignment.text
    return assignment.json()["id"], first, second, outsider


def mutation(base, values, request_id=None):
    return {"baseVersion": base, "values": values, "requestId": str(request_id or uuid4())}


def test_student_reads_published_schema_and_own_draft_only(client, seed_user, db):
    assignment_id, first, _, outsider = setup_assignment(client, seed_user, db, sharing=False)
    login(client, outsider.account)
    assert client.get(f"/api/student/assignments/{assignment_id}").status_code == 404
    login(client, first.account)
    detail = client.get(f"/api/student/assignments/{assignment_id}")
    assert detail.status_code == 200
    assert detail.json()["schema"]["title"] == SCHEMA["title"]
    assert detail.json()["versionNumber"] == 1
    assert client.get("/api/student/assignments").json()[0]["id"] == assignment_id
    url = f"/api/student/assignments/{assignment_id}/draft"
    assert client.get(url).json()["version"] == 0
    saved = client.put(url, json=mutation(0, {"readings:r2c1": "2.4", "readings:r2c2": "正常"}))
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == 1
    assert client.get(url).json()["values"]["readings:r2c1"] == "2.4"


def test_draft_rejects_invalid_fields_and_reports_conflicts(client, seed_user, db):
    assignment_id, first, _, _ = setup_assignment(client, seed_user, db, sharing=False)
    login(client, first.account)
    url = f"/api/student/assignments/{assignment_id}/draft"
    bad = client.put(url, json=mutation(0, {"readings:r2c1": "nonsense"}))
    assert bad.status_code == 422
    assert bad.json()["error"]["details"]["path"] == "readings:r2c1"
    assert client.put(url, json=mutation(0, {"unexpected": "1"})).status_code == 422
    request_id = uuid4()
    first_write = client.put(url, json=mutation(0, {"readings:r2c1": "2.4"}, request_id))
    assert first_write.status_code == 200
    assert client.put(url, json=mutation(0, {"readings:r2c1": "2.4"}, request_id)).json()["version"] == 1
    conflict = client.put(url, json=mutation(0, {"readings:r2c1": "3.4"}))
    assert conflict.status_code == 409
    assert conflict.json()["error"]["details"]["values"]["readings:r2c1"] == "2.4"


def test_group_sharing_requires_teacher_toggle_field_scope_and_membership(client, seed_user, db):
    assignment_id, first, second, outsider = setup_assignment(client, seed_user, db)
    groups_url = f"/api/assignments/{assignment_id}/groups"
    created = client.post(groups_url, json={"name": "第一组", "memberIds": [str(first.id), str(second.id)]})
    assert created.status_code == 201, created.text
    assert len(created.json()["members"]) == 2
    assert client.post(groups_url, json={"name": "越界组", "memberIds": [str(outsider.id)]}).status_code == 422
    login(client, first.account)
    shared_url = f"/api/student/assignments/{assignment_id}/shared"
    assert client.put(f"/api/student/assignments/{assignment_id}/draft", json=mutation(0, {"readings:r2c1": "1"})).status_code == 422
    assert client.put(shared_url, json=mutation(0, {"readings:r2c2": "not shared"})).status_code == 422
    saved = client.put(shared_url, json=mutation(0, {"readings:r2c1": "3.1"}))
    assert saved.status_code == 200, saved.text
    assert saved.json()["sources"]["readings:r2c1"]["editorName"] == first.name
    login(client, second.account)
    assert client.get(shared_url).json()["values"]["readings:r2c1"] == "3.1"
    assert client.put(shared_url, json=mutation(0, {"readings:r2c1": "4.1"})).status_code == 409
    assert client.put(shared_url, json=mutation(1, {"readings:r2c1": "4.1"})).status_code == 200
    db.expire_all()
    revisions = db.scalars(select(SharedDataRevision)).all()
    assert len(revisions) == 2
    assert revisions[1].changes_json["readings:r2c1"] == {"before": "3.1", "after": "4.1"}
    login(client, outsider.account)
    assert client.get(shared_url).status_code == 404


def test_group_data_not_available_without_teacher_enablement(client, seed_user, db):
    assignment_id, first, _, _ = setup_assignment(client, seed_user, db, sharing=False)
    login(client, first.account)
    assert client.get(f"/api/student/assignments/{assignment_id}/shared").status_code == 403


def test_draft_is_read_only_after_due_time(client, seed_user, db):
    assignment_id, first, _, _ = setup_assignment(client, seed_user, db, sharing=False)
    assignment = db.get(Assignment, UUID(assignment_id))
    assignment.due_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    login(client, first.account)
    detail = client.get(f"/api/student/assignments/{assignment_id}")
    assert detail.json()["editable"] is False
    response = client.put(f"/api/student/assignments/{assignment_id}/draft", json=mutation(0, {"readings:r2c1": "1"}))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "assignment_closed"


def test_deleted_assignment_is_hidden_for_30_days_and_restorable_with_student_data(client, seed_user, db):
    assignment_id, first, _, outsider = setup_assignment(client, seed_user, db, sharing=False)
    login(client, first.account)
    draft_url = f"/api/student/assignments/{assignment_id}/draft"
    assert client.put(draft_url, json=mutation(0, {"readings:r2c2": "已测量"})).status_code == 200
    login(client, outsider.account)
    assert client.delete(f"/api/assignments/{assignment_id}").status_code == 403
    login(client, "t0001")

    deleted = client.delete(f"/api/assignments/{assignment_id}")
    assert deleted.status_code == 200
    assert (datetime.fromisoformat(deleted.json()["purgeAfter"]) - datetime.fromisoformat(deleted.json()["deletedAt"])).days == 30
    assert client.get("/api/assignments").json() == []
    assert client.get("/api/assignments/deleted").json()[0]["id"] == assignment_id
    db.expire_all()
    assert db.get(SubmissionDraft, db.scalar(select(SubmissionDraft.id).where(SubmissionDraft.assignment_id == UUID(assignment_id)))).values_json == {"readings:r2c2": "已测量"}
    login(client, first.account)
    assert client.get("/api/student/assignments").json() == []
    assert client.get(draft_url).status_code == 404
    assert client.put(draft_url, json=mutation(1, {"readings:r2c2": "改写"})).status_code == 404

    login(client, "t0001")
    assert client.post(f"/api/assignments/{assignment_id}/restore").status_code == 204
    assert len(client.get("/api/assignments").json()) == 1
    login(client, first.account)
    assert client.get(draft_url).json()["values"] == {"readings:r2c2": "已测量"}


def test_expired_assignment_purge_removes_saved_data_only_after_deadline(client, seed_user, db):
    assignment_id, first, _, _ = setup_assignment(client, seed_user, db, sharing=True)
    assert client.post(f"/api/assignments/{assignment_id}/groups", json={"name": "第一组", "memberIds": [str(first.id)]}).status_code == 201
    login(client, first.account)
    assert client.put(f"/api/student/assignments/{assignment_id}/draft", json=mutation(0, {"readings:r2c2": "保留中"})).status_code == 200
    assert client.put(f"/api/student/assignments/{assignment_id}/shared", json=mutation(0, {"readings:r2c1": "2.4"})).status_code == 200
    login(client, "t0001")
    assert client.delete(f"/api/assignments/{assignment_id}").status_code == 200
    assert purge_expired_assignments(db) == 0
    assignment = db.get(Assignment, UUID(assignment_id))
    assignment.purge_after = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert client.post(f"/api/assignments/{assignment_id}/restore").status_code == 410

    assert purge_expired_assignments(db) == 1
    assert db.get(Assignment, UUID(assignment_id)) is None
    assert db.scalars(select(SubmissionDraft).where(SubmissionDraft.assignment_id == UUID(assignment_id))).all() == []
    assert db.scalars(select(SharedDataset).where(SharedDataset.assignment_id == UUID(assignment_id))).all() == []


def test_membership_changes_are_audited_and_student_cannot_manage_groups(client, seed_user, db):
    assignment_id, first, second, _ = setup_assignment(client, seed_user, db)
    groups_url = f"/api/assignments/{assignment_id}/groups"
    group_id = client.post(groups_url, json={"name": "第一组", "memberIds": [str(first.id)]}).json()["id"]
    changed = client.put(f"{groups_url}/{group_id}/members", json={"memberIds": [str(second.id)]})
    assert changed.status_code == 200
    assert changed.json()["memberIds"] == [str(second.id)]
    db.expire_all()
    audit = db.scalars(select(AuditLog).where(AuditLog.action == "group.members_changed").order_by(AuditLog.created_at.desc())).first()
    assert audit is not None
    assert str(first.id) in audit.metadata_json["removed"]
    assert str(second.id) in audit.metadata_json["added"]
    login(client, first.account)
    assert client.get(groups_url).status_code == 403
    assert client.get(f"/api/student/assignments/{assignment_id}/shared").status_code == 403


def test_sharing_configuration_locks_after_student_starts_recording(client, seed_user, db):
    assignment_id, first, _, _ = setup_assignment(client, seed_user, db, sharing=False)
    login(client, first.account)
    assert client.put(f"/api/student/assignments/{assignment_id}/draft", json=mutation(0, {"readings:r2c1": "1"})).status_code == 200
    login(client, "t0001")
    response = client.put(f"/api/assignments/{assignment_id}/sharing", json={"enabled": True})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "sharing_configuration_locked"
