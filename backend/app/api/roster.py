from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, UploadFile
from sqlalchemy import delete, func, select

from app.api.auth import auth_service
from app.api.deps import Current, Db, require_roles
from app.auth.errors import AuthError
from app.db.models import Assignment, AuditLog, ClassMember, LabClass, RosterImport, User
from app.roster.schemas import ClassCreate, ClassView, ImportPreviewView, ImportResultView, StudentView, TeacherView
from app.roster.service import RosterService


router = APIRouter(prefix="/api")
roster_service = RosterService(auth_service)


def _allowed_class(db, current, class_id: UUID) -> LabClass:
    lab_class = db.get(LabClass, class_id)
    if not lab_class:
        raise AuthError("class_not_found", "班级不存在。", 404)
    if current.user.role != "admin" and lab_class.teacher_id != current.user.id:
        raise AuthError("forbidden", "你没有权限管理该班级。", 403)
    return lab_class


@router.get("/teachers", response_model=list[TeacherView])
def list_teachers(db: Db, current: Current) -> list[TeacherView]:
    require_roles(current, "admin")
    teachers = db.scalars(select(User).where(User.role == "teacher", User.status == "active").order_by(User.name)).all()
    return [TeacherView(id=teacher.id, account=teacher.account, name=teacher.name) for teacher in teachers]


@router.get("/classes", response_model=list[ClassView])
def list_classes(db: Db, current: Current) -> list[ClassView]:
    require_roles(current, "teacher", "admin")
    statement = (
        select(LabClass, User.name, func.count(ClassMember.id))
        .join(User, User.id == LabClass.teacher_id)
        .outerjoin(ClassMember, ClassMember.class_id == LabClass.id)
        .group_by(LabClass.id, User.name)
        .order_by(LabClass.semester.desc(), LabClass.class_code)
    )
    if current.user.role == "teacher":
        statement = statement.where(LabClass.teacher_id == current.user.id)
    return [
        ClassView(
            id=item.id,
            classCode=item.class_code,
            className=item.class_name,
            semester=item.semester,
            teacherId=item.teacher_id,
            teacherName=teacher_name,
            studentCount=student_count,
        )
        for item, teacher_name, student_count in db.execute(statement).all()
    ]


@router.post("/classes", response_model=ClassView, status_code=201)
def create_class(payload: ClassCreate, db: Db, current: Current) -> ClassView:
    require_roles(current, "teacher", "admin")
    teacher_id = payload.teacher_id if current.user.role == "admin" else current.user.id
    if not teacher_id:
        raise AuthError("teacher_required", "管理员创建班级时必须选择教师。", 422)
    teacher = db.get(User, teacher_id)
    if not teacher or teacher.role != "teacher":
        raise AuthError("teacher_not_found", "指定教师不存在。", 422)
    duplicate = db.scalar(
        select(LabClass).where(LabClass.class_code == payload.class_code, LabClass.semester == payload.semester)
    )
    if duplicate:
        raise AuthError("class_exists", "同一学期已存在该班级代码。", 409)
    item = LabClass(
        class_code=payload.class_code.strip(),
        class_name=payload.class_name.strip(),
        semester=payload.semester.strip(),
        teacher_id=teacher.id,
        created_at=datetime.now(UTC),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return ClassView(
        id=item.id,
        classCode=item.class_code,
        className=item.class_name,
        semester=item.semester,
        teacherId=item.teacher_id,
        teacherName=teacher.name,
        studentCount=0,
    )


@router.get("/classes/{class_id}/students", response_model=list[StudentView])
def list_class_students(class_id: UUID, db: Db, current: Current) -> list[StudentView]:
    require_roles(current, "teacher", "admin")
    _allowed_class(db, current, class_id)
    statement = (
        select(User, ClassMember.joined_at)
        .join(ClassMember, ClassMember.user_id == User.id)
        .where(ClassMember.class_id == class_id, User.role == "student")
        .order_by(User.student_number, User.name)
    )
    return [
        StudentView(
            id=user.id,
            account=user.account,
            name=user.name,
            studentNumber=user.student_number or user.account,
            joinedAt=joined_at,
            enrollmentCompleted=user.enrollment_completed,
        )
        for user, joined_at in db.execute(statement).all()
    ]


@router.delete("/classes/{class_id}", status_code=204)
def delete_class(class_id: UUID, db: Db, current: Current) -> None:
    require_roles(current, "teacher", "admin")
    lab_class = _allowed_class(db, current, class_id)
    assignment_count = db.scalar(select(func.count(Assignment.id)).where(Assignment.class_id == class_id)) or 0
    if assignment_count:
        raise AuthError("class_has_assignments", "该班级已有实验任务，不能删除。", 409)
    member_count = db.scalar(select(func.count(ClassMember.id)).where(ClassMember.class_id == class_id)) or 0
    db.execute(delete(ClassMember).where(ClassMember.class_id == class_id))
    db.execute(delete(RosterImport).where(RosterImport.class_id == class_id))
    db.delete(lab_class)
    db.add(
        AuditLog(
            actor_id=current.user.id,
            action="class.deleted",
            resource_type="class",
            resource_id=str(class_id),
            metadata_json={
                "classCode": lab_class.class_code,
                "className": lab_class.class_name,
                "semester": lab_class.semester,
                "removedMemberships": member_count,
            },
            created_at=datetime.now(UTC),
        )
    )
    db.commit()


@router.post("/roster-imports/preview", response_model=ImportPreviewView, status_code=201)
async def preview_roster(
    class_id: UUID,
    db: Db,
    current: Current,
    file: Annotated[UploadFile, File()],
) -> ImportPreviewView:
    require_roles(current, "teacher", "admin")
    lab_class = _allowed_class(db, current, class_id)
    content = await file.read()
    preview = roster_service.preview(db, lab_class, current.user, file.filename or "roster.xlsx", content)
    return ImportPreviewView(
        id=preview.id,
        classId=preview.class_id,
        sourceName=preview.source_name,
        status=preview.status,
        validCount=len(preview.rows_json) - len({error["row"] for error in preview.errors_json if error["row"] > 1}),
        errorCount=len(preview.errors_json),
        errors=preview.errors_json,
    )


@router.post("/roster-imports/{preview_id}/commit", response_model=ImportResultView)
def commit_roster(preview_id: UUID, db: Db, current: Current) -> ImportResultView:
    require_roles(current, "teacher", "admin")
    preview = db.get(RosterImport, preview_id)
    if not preview:
        raise AuthError("import_not_found", "名单预览不存在。", 404)
    _allowed_class(db, current, preview.class_id)
    return ImportResultView.model_validate(roster_service.commit(db, preview))


@router.get("/roster-imports/{preview_id}/errors")
def roster_errors(preview_id: UUID, db: Db, current: Current) -> dict:
    require_roles(current, "teacher", "admin")
    preview = db.get(RosterImport, preview_id)
    if not preview:
        raise AuthError("import_not_found", "名单预览不存在。", 404)
    _allowed_class(db, current, preview.class_id)
    return {"errors": preview.errors_json}
