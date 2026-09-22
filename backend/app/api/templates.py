from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import Current, Db, require_roles
from app.auth.errors import AuthError
from app.db.models import Assignment, ExperimentTemplate, LabClass, TemplateVersion
from app.templates.schemas import (
    AssignmentCreate,
    AssignmentSummary,
    AssignmentView,
    TemplateCreate,
    TemplateDraftUpdate,
    TemplateVersionView,
    TemplateView,
    ValidationView,
)
from app.templates.service import TemplateService


router = APIRouter(prefix="/api")
template_service = TemplateService()


def _owned_template(db, current, template_id: UUID) -> ExperimentTemplate:
    item = db.get(ExperimentTemplate, template_id)
    if not item:
        raise AuthError("template_not_found", "实验模板不存在。", 404)
    if current.user.role != "admin" and item.owner_teacher_id != current.user.id:
        raise AuthError("forbidden", "你没有权限管理该模板。", 403)
    return item


@router.get("/templates", response_model=list[TemplateView])
def list_templates(db: Db, current: Current) -> list[TemplateView]:
    require_roles(current, "teacher", "admin")
    statement = select(ExperimentTemplate).order_by(ExperimentTemplate.updated_at.desc())
    if current.user.role == "teacher":
        statement = statement.where(ExperimentTemplate.owner_teacher_id == current.user.id)
    result: list[TemplateView] = []
    for item in db.scalars(statement):
        versions = db.scalars(
            select(TemplateVersion)
            .where(TemplateVersion.template_id == item.id)
            .order_by(TemplateVersion.version_number.desc())
        ).all()
        result.append(
            TemplateView(
                id=item.id,
                name=item.name,
                description=item.description,
                status=item.status,
                schema=item.draft_schema_json,
                versionCount=len(versions),
                latestVersionId=versions[0].id if versions else None,
            )
        )
    return result


@router.post("/templates", response_model=TemplateView, status_code=201)
def create_template(payload: TemplateCreate, db: Db, current: Current) -> TemplateView:
    require_roles(current, "teacher")
    now = datetime.now(UTC)
    item = ExperimentTemplate(
        name=payload.name.strip(),
        description=payload.description.strip(),
        owner_teacher_id=current.user.id,
        status="draft",
        draft_schema_json={"title": payload.name.strip(), "tables": [], "calculations": [], "charts": [], "checks": []},
        created_at=now,
        updated_at=now,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return TemplateView(
        id=item.id,
        name=item.name,
        description=item.description,
        status=item.status,
        schema=item.draft_schema_json,
        versionCount=0,
        latestVersionId=None,
    )


@router.put("/templates/{template_id}/draft", response_model=TemplateView)
def update_template(template_id: UUID, payload: TemplateDraftUpdate, db: Db, current: Current) -> TemplateView:
    require_roles(current, "teacher")
    item = _owned_template(db, current, template_id)
    item.name = payload.name.strip()
    item.description = payload.description.strip()
    item.draft_schema_json = payload.schema_data
    item.updated_at = datetime.now(UTC)
    db.commit()
    version_count = db.scalar(select(func.count(TemplateVersion.id)).where(TemplateVersion.template_id == item.id)) or 0
    latest = db.scalar(
        select(TemplateVersion)
        .where(TemplateVersion.template_id == item.id)
        .order_by(TemplateVersion.version_number.desc())
    )
    return TemplateView(
        id=item.id,
        name=item.name,
        description=item.description,
        status=item.status,
        schema=item.draft_schema_json,
        versionCount=version_count,
        latestVersionId=latest.id if latest else None,
    )


@router.post("/templates/{template_id}/validate", response_model=ValidationView)
def validate_template(template_id: UUID, db: Db, current: Current) -> ValidationView:
    require_roles(current, "teacher")
    item = _owned_template(db, current, template_id)
    issues = template_service.validate(item.draft_schema_json)
    return ValidationView(valid=not issues, issues=issues)


@router.post("/templates/{template_id}/publish", response_model=TemplateVersionView, status_code=201)
def publish_template(template_id: UUID, db: Db, current: Current) -> TemplateVersionView:
    require_roles(current, "teacher")
    item = _owned_template(db, current, template_id)
    version = template_service.publish(db, item)
    return TemplateVersionView(
        id=version.id,
        templateId=version.template_id,
        versionNumber=version.version_number,
        schema=version.schema_json,
        publishedAt=version.published_at,
    )


@router.post("/assignments", response_model=AssignmentView, status_code=201)
def create_assignment(payload: AssignmentCreate, db: Db, current: Current) -> AssignmentView:
    require_roles(current, "teacher")
    lab_class = db.get(LabClass, payload.class_id)
    if not lab_class or lab_class.teacher_id != current.user.id:
        raise AuthError("class_not_found", "班级不存在或不属于当前教师。", 404)
    version = db.get(TemplateVersion, payload.template_version_id)
    template = db.get(ExperimentTemplate, version.template_id) if version else None
    if not version or not template or template.owner_teacher_id != current.user.id:
        raise AuthError("version_not_found", "已发布模板版本不存在。", 404)
    if payload.due_at <= payload.start_at:
        raise AuthError("invalid_assignment_time", "截止时间必须晚于开放时间。", 422)
    item = Assignment(
        template_version_id=version.id,
        class_id=lab_class.id,
        title=payload.title.strip(),
        start_at=payload.start_at,
        due_at=payload.due_at,
        status=payload.status,
        created_by=current.user.id,
        created_at=datetime.now(UTC),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return AssignmentView(
        id=item.id,
        templateVersionId=item.template_version_id,
        classId=item.class_id,
        title=item.title,
        startAt=item.start_at,
        dueAt=item.due_at,
        status=item.status,
    )


@router.get("/assignments", response_model=list[AssignmentSummary])
def list_assignments(db: Db, current: Current) -> list[AssignmentSummary]:
    require_roles(current, "teacher", "admin")
    statement = (
        select(Assignment, LabClass, TemplateVersion, ExperimentTemplate)
        .join(LabClass, LabClass.id == Assignment.class_id)
        .join(TemplateVersion, TemplateVersion.id == Assignment.template_version_id)
        .join(ExperimentTemplate, ExperimentTemplate.id == TemplateVersion.template_id)
        .order_by(Assignment.created_at.desc())
    )
    if current.user.role == "teacher":
        statement = statement.where(Assignment.created_by == current.user.id)
    return [
        AssignmentSummary(
            id=item.id,
            templateVersionId=version.id,
            classId=lab_class.id,
            title=item.title,
            startAt=item.start_at,
            dueAt=item.due_at,
            status=item.status,
            templateName=template.name,
            versionNumber=version.version_number,
            className=lab_class.class_name,
            classCode=lab_class.class_code,
        )
        for item, lab_class, version, template in db.execute(statement).all()
    ]


@router.get("/assignments/{assignment_id}", response_model=AssignmentView)
def get_assignment(assignment_id: UUID, db: Db, current: Current) -> AssignmentView:
    require_roles(current, "teacher", "admin")
    item = db.get(Assignment, assignment_id)
    if not item:
        raise AuthError("assignment_not_found", "实验任务不存在。", 404)
    lab_class = db.get(LabClass, item.class_id)
    if current.user.role == "teacher" and (not lab_class or lab_class.teacher_id != current.user.id):
        raise AuthError("forbidden", "你没有权限查看该实验任务。", 403)
    return AssignmentView(
        id=item.id,
        templateVersionId=item.template_version_id,
        classId=item.class_id,
        title=item.title,
        startAt=item.start_at,
        dueAt=item.due_at,
        status=item.status,
    )
