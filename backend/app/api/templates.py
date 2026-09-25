from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, File, UploadFile
from sqlalchemy import func, select

from app.api.deps import Current, Db, require_roles
from app.auth.errors import AuthError
from app.db.models import Assignment, AuditLog, ExperimentTemplate, LabClass, TemplateVersion
from app.templates.schemas import (
    AssignmentCreate,
    AssignmentDeletionView,
    AssignmentSummary,
    AssignmentView,
    TemplateCreate,
    TemplateDraftUpdate,
    TemplateVersionView,
    TemplateView,
    ValidationView,
    WordImportView,
)
from app.templates.service import TemplateService
from app.templates.excel_import import MAX_XLSX_BYTES, import_excel_template
from app.templates.word_import import MAX_DOCX_BYTES, import_word_template


router = APIRouter(prefix="/api")
template_service = TemplateService()


def _owned_template(db, current, template_id: UUID) -> ExperimentTemplate:
    item = db.get(ExperimentTemplate, template_id)
    if not item or item.status == "archived":
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
    statement = statement.where(ExperimentTemplate.status != "archived")
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


@router.post("/templates/import-docx", response_model=WordImportView)
async def preview_word_template(current: Current, file: UploadFile = File(...)) -> WordImportView:
    require_roles(current, "teacher")
    content = await file.read(MAX_DOCX_BYTES + 1)
    try:
        schema, warnings = import_word_template(content, file.filename or "")
    except ValueError as exc:
        raise AuthError("invalid_word_template", str(exc), 422) from exc
    return WordImportView(schema=schema, warnings=warnings)


@router.post("/templates/import-xlsx", response_model=WordImportView)
async def preview_excel_template(current: Current, file: UploadFile = File(...)) -> WordImportView:
    require_roles(current, "teacher")
    content = await file.read(MAX_XLSX_BYTES + 1)
    try:
        schema, warnings = import_excel_template(content, file.filename or "")
    except ValueError as exc:
        raise AuthError("invalid_excel_template", str(exc), 422) from exc
    return WordImportView(schema=schema, warnings=warnings)


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(template_id: UUID, db: Db, current: Current) -> None:
    require_roles(current, "teacher")
    item = _owned_template(db, current, template_id)
    item.status = "archived"
    item.updated_at = datetime.now(UTC)
    db.commit()


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
    if not version or not template or template.status == "archived" or template.owner_teacher_id != current.user.id:
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
        group_sharing_enabled=payload.group_sharing_enabled,
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
        groupSharingEnabled=item.group_sharing_enabled,
    )


@router.get("/assignments", response_model=list[AssignmentSummary])
def list_assignments(db: Db, current: Current) -> list[AssignmentSummary]:
    require_roles(current, "teacher", "admin")
    statement = (
        select(Assignment, LabClass, TemplateVersion, ExperimentTemplate)
        .join(LabClass, LabClass.id == Assignment.class_id)
        .join(TemplateVersion, TemplateVersion.id == Assignment.template_version_id)
        .join(ExperimentTemplate, ExperimentTemplate.id == TemplateVersion.template_id)
        .where(Assignment.deleted_at.is_(None))
        .order_by(Assignment.created_at.desc())
    )
    if current.user.role == "teacher":
        statement = statement.where(Assignment.created_by == current.user.id)
    return _assignment_summaries(db.execute(statement).all())


def _assignment_summaries(rows) -> list[AssignmentSummary]:
    return [
        AssignmentSummary(
            id=item.id,
            templateVersionId=version.id,
            classId=lab_class.id,
            title=item.title,
            startAt=item.start_at,
            dueAt=item.due_at,
            status=item.status,
            groupSharingEnabled=item.group_sharing_enabled,
            templateName=template.name,
            versionNumber=version.version_number,
            className=lab_class.class_name,
            classCode=lab_class.class_code,
            deletedAt=item.deleted_at,
            purgeAfter=item.purge_after,
        )
        for item, lab_class, version, template in rows
    ]


@router.get("/assignments/deleted", response_model=list[AssignmentSummary])
def list_deleted_assignments(db: Db, current: Current) -> list[AssignmentSummary]:
    require_roles(current, "teacher", "admin")
    statement = (
        select(Assignment, LabClass, TemplateVersion, ExperimentTemplate)
        .join(LabClass, LabClass.id == Assignment.class_id)
        .join(TemplateVersion, TemplateVersion.id == Assignment.template_version_id)
        .join(ExperimentTemplate, ExperimentTemplate.id == TemplateVersion.template_id)
        .where(Assignment.deleted_at.is_not(None), Assignment.purge_after > datetime.now(UTC))
        .order_by(Assignment.deleted_at.desc())
    )
    if current.user.role == "teacher":
        statement = statement.where(Assignment.created_by == current.user.id)
    return _assignment_summaries(db.execute(statement).all())


@router.delete("/assignments/{assignment_id}", response_model=AssignmentDeletionView)
def delete_assignment(assignment_id: UUID, db: Db, current: Current) -> AssignmentDeletionView:
    require_roles(current, "teacher")
    item = db.get(Assignment, assignment_id)
    if not item or item.created_by != current.user.id or item.deleted_at is not None:
        raise AuthError("assignment_not_found", "实验任务不存在。", 404)
    now = datetime.now(UTC)
    item.deleted_at = now
    item.purge_after = now + timedelta(days=30)
    db.add(AuditLog(actor_id=current.user.id, action="assignment.deleted", resource_type="assignment",
                    resource_id=str(item.id), metadata_json={"purgeAfter": item.purge_after.isoformat()}, created_at=now))
    db.commit()
    return AssignmentDeletionView(id=item.id, deletedAt=item.deleted_at, purgeAfter=item.purge_after)


@router.post("/assignments/{assignment_id}/restore", status_code=204)
def restore_assignment(assignment_id: UUID, db: Db, current: Current) -> None:
    require_roles(current, "teacher")
    item = db.get(Assignment, assignment_id)
    if not item or item.created_by != current.user.id or item.deleted_at is None:
        raise AuthError("assignment_not_found", "待恢复的实验任务不存在。", 404)
    now = datetime.now(UTC)
    deadline = item.purge_after.replace(tzinfo=UTC) if item.purge_after and item.purge_after.tzinfo is None else item.purge_after
    if deadline is None or deadline <= now:
        raise AuthError("assignment_retention_expired", "30 天恢复期已结束，任务无法恢复。", 410)
    item.deleted_at = None
    item.purge_after = None
    db.add(AuditLog(actor_id=current.user.id, action="assignment.restored", resource_type="assignment",
                    resource_id=str(item.id), metadata_json={}, created_at=now))
    db.commit()


@router.get("/assignments/{assignment_id}", response_model=AssignmentView)
def get_assignment(assignment_id: UUID, db: Db, current: Current) -> AssignmentView:
    require_roles(current, "teacher", "admin")
    item = db.get(Assignment, assignment_id)
    if not item or item.deleted_at is not None:
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
        groupSharingEnabled=item.group_sharing_enabled,
    )
