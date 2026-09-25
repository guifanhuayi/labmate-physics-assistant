"""Student data entry, versioned drafts, and explicitly enabled group data."""

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from app.api.deps import Current, Db, require_roles
from app.auth.errors import AuthError
from app.db.models import (
    Assignment, AuditLog, ClassMember, DraftMutation, ExperimentGroup, GroupMember,
    SharedDataRevision, SharedDataset, SubmissionDraft, TemplateVersion, User,
)


router = APIRouter(prefix="/api")


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    member_ids: list[UUID] = Field(default_factory=list, alias="memberIds")


class GroupMembersUpdate(BaseModel):
    member_ids: list[UUID] = Field(alias="memberIds")


class SharingUpdate(BaseModel):
    enabled: bool


class ValuesUpdate(BaseModel):
    base_version: int = Field(ge=0, alias="baseVersion")
    request_id: UUID = Field(alias="requestId")
    values: dict[str, str] = Field(max_length=6000)


def _assignment(db, assignment_id: UUID) -> Assignment:
    item = db.get(Assignment, assignment_id)
    if not item or item.deleted_at is not None:
        raise AuthError("assignment_not_found", "实验任务不存在。", 404)
    return item


def _teacher_assignment(db, current, assignment_id: UUID) -> Assignment:
    require_roles(current, "teacher", "admin")
    item = _assignment(db, assignment_id)
    if current.user.role != "admin" and item.created_by != current.user.id:
        raise AuthError("forbidden", "你没有权限管理该实验任务。", 403)
    return item


def _student_assignment(db, current, assignment_id: UUID) -> Assignment:
    require_roles(current, "student")
    item = _assignment(db, assignment_id)
    member = db.scalar(select(ClassMember.id).where(ClassMember.class_id == item.class_id, ClassMember.user_id == current.user.id))
    if not member or item.status == "draft":
        raise AuthError("assignment_not_found", "实验任务不存在。", 404)
    return item


def _editable(item: Assignment) -> bool:
    now = datetime.now(UTC)
    start = item.start_at.replace(tzinfo=UTC) if item.start_at.tzinfo is None else item.start_at
    due = item.due_at.replace(tzinfo=UTC) if item.due_at.tzinfo is None else item.due_at
    return item.status == "open" and start <= now <= due


def _assert_editable(item: Assignment) -> None:
    if not _editable(item):
        raise AuthError("assignment_closed", "当前实验任务不在录入开放时间内。", 403)


def _group(db, assignment_id: UUID, user_id: UUID) -> ExperimentGroup | None:
    return db.scalar(
        select(ExperimentGroup).join(GroupMember, GroupMember.group_id == ExperimentGroup.id)
        .where(GroupMember.assignment_id == assignment_id, GroupMember.user_id == user_id)
    )


def _fields(db, item: Assignment) -> dict[str, dict[str, Any]]:
    version = db.get(TemplateVersion, item.template_version_id)
    result: dict[str, dict[str, Any]] = {}
    for table in version.schema_json.get("tables", []):
        table_id = table["id"]
        fields = {field["key"]: field for field in table.get("fields", [])}
        grid = table.get("grid")
        if grid:
            cells = grid.get("cells", [])
        else:
            cells = [
                {"id": f"r{row + 1}c{column + 1}", "kind": "field", "fieldKey": field["key"]}
                for row in range(1, table.get("minimumRows", 1) + 1)
                for column, field in enumerate(table.get("fields", []))
            ]
        for cell in cells:
            if cell.get("kind") == "field" and cell.get("fieldKey") in fields:
                result[f"{table_id}:{cell['id']}"] = fields[cell["fieldKey"]]
    return result


def _validate_values(db, item: Assignment, values: dict[str, str], shared: bool) -> None:
    fields = _fields(db, item)
    if len(values) > len(fields):
        raise AuthError("invalid_values", "录入数据数量超出模板范围。", 422)
    for key, value in values.items():
        field = fields.get(key)
        if field is None or not isinstance(value, str) or len(value) > 4000:
            raise AuthError("invalid_value", "录入数据与已发布模板不匹配。", 422, {"path": key})
        is_shared = item.group_sharing_enabled and field.get("scope") == "group"
        if is_shared != shared:
            raise AuthError("invalid_scope", "该测量数据不属于当前记录。", 422, {"path": key})
        if not value.strip():
            continue  # Drafts may be incomplete.
        kind = field.get("type")
        if kind in {"number", "integer"}:
            try:
                number = Decimal(value)
            except InvalidOperation:
                number = Decimal("NaN")
            if not number.is_finite() or (kind == "integer" and number != number.to_integral_value()):
                raise AuthError("invalid_value", "请输入有效数值。", 422, {"path": key})
        elif kind == "enum" and value not in field.get("options", []):
            raise AuthError("invalid_value", "请选择模板中的选项。", 422, {"path": key})
        elif kind == "time":
            try:
                datetime.fromisoformat(value)
            except ValueError as exc:
                raise AuthError("invalid_value", "请输入有效时间。", 422, {"path": key}) from exc
        elif kind == "image":
            raise AuthError("file_stage_not_ready", "图片附件将在下一阶段开放。", 422, {"path": key})


def _group_view(db, group: ExperimentGroup) -> dict:
    members = db.execute(
        select(User.id, User.name, User.student_number)
        .join(GroupMember, GroupMember.user_id == User.id)
        .where(GroupMember.group_id == group.id).order_by(User.student_number)
    ).all()
    return {"id": group.id, "name": group.name, "memberIds": [row.id for row in members],
            "members": [{"id": row.id, "name": row.name, "studentNumber": row.student_number} for row in members]}


def _replace_members(db, item: Assignment, group: ExperimentGroup, member_ids: list[UUID], actor_id: UUID) -> None:
    ids = set(member_ids)
    if len(ids) != len(member_ids):
        raise AuthError("duplicate_member", "同一学生不能重复加入小组。", 422)
    if ids:
        eligible = set(db.scalars(
            select(User.id).join(ClassMember, ClassMember.user_id == User.id)
            .where(ClassMember.class_id == item.class_id, User.role == "student", User.id.in_(ids))
        ).all())
        if eligible != ids:
            raise AuthError("invalid_group_member", "小组成员必须是本班学生。", 422)
        other = db.scalar(select(GroupMember).where(
            GroupMember.assignment_id == item.id, GroupMember.group_id != group.id, GroupMember.user_id.in_(ids)
        ))
        if other:
            raise AuthError("group_member_exists", "学生已属于本实验的另一小组。", 409)
    old_ids = set(db.scalars(select(GroupMember.user_id).where(GroupMember.group_id == group.id)).all())
    db.execute(delete(GroupMember).where(GroupMember.group_id == group.id))
    now = datetime.now(UTC)
    db.add_all(GroupMember(assignment_id=item.id, group_id=group.id, user_id=user_id, joined_at=now) for user_id in ids)
    db.add(AuditLog(actor_id=actor_id, action="group.members_changed", resource_type="experiment_group",
                    resource_id=str(group.id), metadata_json={"assignmentId": str(item.id),
                    "added": sorted(map(str, ids - old_ids)), "removed": sorted(map(str, old_ids - ids))}, created_at=now))
    db.commit()


@router.put("/assignments/{assignment_id}/sharing")
def set_sharing(assignment_id: UUID, payload: SharingUpdate, db: Db, current: Current) -> dict:
    item = _teacher_assignment(db, current, assignment_id)
    before = item.group_sharing_enabled
    if before == payload.enabled:
        return {"groupSharingEnabled": before}
    if db.scalar(select(SubmissionDraft.id).where(SubmissionDraft.assignment_id == item.id)) or db.scalar(
        select(SharedDataset.id).where(SharedDataset.assignment_id == item.id)
    ):
        raise AuthError("sharing_configuration_locked", "已有学生录入数据，不能改变测量数据的归属和共享设置。", 409)
    item.group_sharing_enabled = payload.enabled
    db.add(AuditLog(actor_id=current.user.id, action="assignment.sharing_changed", resource_type="assignment",
                    resource_id=str(item.id), metadata_json={"before": before, "after": payload.enabled}, created_at=datetime.now(UTC)))
    db.commit()
    return {"groupSharingEnabled": item.group_sharing_enabled}


@router.get("/assignments/{assignment_id}/groups")
def list_groups(assignment_id: UUID, db: Db, current: Current) -> list[dict]:
    _teacher_assignment(db, current, assignment_id)
    return [_group_view(db, group) for group in db.scalars(
        select(ExperimentGroup).where(ExperimentGroup.assignment_id == assignment_id).order_by(ExperimentGroup.name)
    )]


@router.post("/assignments/{assignment_id}/groups", status_code=201)
def create_group(assignment_id: UUID, payload: GroupCreate, db: Db, current: Current) -> dict:
    item = _teacher_assignment(db, current, assignment_id)
    name = payload.name.strip()
    if not name:
        raise AuthError("invalid_group_name", "小组名称不能为空。", 422)
    if db.scalar(select(ExperimentGroup.id).where(ExperimentGroup.assignment_id == item.id, ExperimentGroup.name == name)):
        raise AuthError("group_exists", "本实验已有同名小组。", 409)
    group = ExperimentGroup(assignment_id=item.id, name=name, created_by=current.user.id, created_at=datetime.now(UTC))
    db.add(group)
    db.flush()
    _replace_members(db, item, group, payload.member_ids, current.user.id)
    return _group_view(db, group)


@router.put("/assignments/{assignment_id}/groups/{group_id}/members")
def set_group_members(assignment_id: UUID, group_id: UUID, payload: GroupMembersUpdate, db: Db, current: Current) -> dict:
    item = _teacher_assignment(db, current, assignment_id)
    group = db.get(ExperimentGroup, group_id)
    if not group or group.assignment_id != item.id:
        raise AuthError("group_not_found", "实验小组不存在。", 404)
    _replace_members(db, item, group, payload.member_ids, current.user.id)
    return _group_view(db, group)


@router.get("/student/assignments")
def student_assignments(db: Db, current: Current) -> list[dict]:
    require_roles(current, "student")
    items = db.execute(
        select(Assignment, TemplateVersion).join(ClassMember, ClassMember.class_id == Assignment.class_id)
        .join(TemplateVersion, TemplateVersion.id == Assignment.template_version_id)
        .where(ClassMember.user_id == current.user.id, Assignment.status != "draft", Assignment.deleted_at.is_(None))
        .order_by(Assignment.due_at.desc())
    ).all()
    return [{"id": item.id, "title": item.title, "startAt": item.start_at, "dueAt": item.due_at,
             "status": item.status, "editable": _editable(item), "versionNumber": version.version_number,
             "groupSharingEnabled": item.group_sharing_enabled} for item, version in items]


@router.get("/student/assignments/{assignment_id}")
def student_assignment(assignment_id: UUID, db: Db, current: Current) -> dict:
    item = _student_assignment(db, current, assignment_id)
    version = db.get(TemplateVersion, item.template_version_id)
    group = _group(db, item.id, current.user.id) if item.group_sharing_enabled else None
    return {"id": item.id, "title": item.title, "startAt": item.start_at, "dueAt": item.due_at,
            "status": item.status, "editable": _editable(item), "versionId": version.id,
            "versionNumber": version.version_number, "schema": version.schema_json,
            "groupSharingEnabled": item.group_sharing_enabled,
            "group": {"id": group.id, "name": group.name} if group else None}


def _draft_view(draft: SubmissionDraft | None) -> dict:
    return {"version": draft.version if draft else 0, "values": draft.values_json if draft else {},
            "updatedAt": draft.updated_at if draft else None, "locked": bool(draft and draft.locked_at)}


@router.get("/student/assignments/{assignment_id}/draft")
def get_draft(assignment_id: UUID, db: Db, current: Current) -> dict:
    _student_assignment(db, current, assignment_id)
    draft = db.scalar(select(SubmissionDraft).where(
        SubmissionDraft.assignment_id == assignment_id, SubmissionDraft.student_id == current.user.id
    ))
    return _draft_view(draft)


@router.put("/student/assignments/{assignment_id}/draft")
def save_draft(assignment_id: UUID, payload: ValuesUpdate, db: Db, current: Current) -> dict:
    item = _student_assignment(db, current, assignment_id)
    _assert_editable(item)
    _validate_values(db, item, payload.values, shared=False)
    request_id = str(payload.request_id)
    previous = db.scalar(select(DraftMutation).where(DraftMutation.request_id == request_id))
    if previous:
        draft = db.get(SubmissionDraft, previous.draft_id)
        if not draft or draft.assignment_id != item.id or draft.student_id != current.user.id:
            raise AuthError("request_id_reused", "请求编号已被其他操作使用。", 409)
        if draft.version == previous.version:
            return _draft_view(draft)
        raise AuthError("request_id_reused", "请求编号对应旧版本，请合并最新数据。", 409, _draft_view(draft))
    draft = db.scalar(select(SubmissionDraft).where(
        SubmissionDraft.assignment_id == item.id, SubmissionDraft.student_id == current.user.id
    ))
    if (draft.version if draft else 0) != payload.base_version:
        raise AuthError("draft_conflict", "草稿已在其他位置更新。", 409, _draft_view(draft))
    if draft and draft.locked_at:
        raise AuthError("draft_locked", "已提交的数据不能修改。", 403)
    now = datetime.now(UTC)
    try:
        if draft:
            result = db.execute(update(SubmissionDraft).where(
                SubmissionDraft.id == draft.id, SubmissionDraft.version == payload.base_version,
                SubmissionDraft.locked_at.is_(None)
            ).values(values_json=payload.values, version=payload.base_version + 1, updated_at=now))
            if result.rowcount != 1:
                db.rollback()
                latest = db.scalar(select(SubmissionDraft).where(
                    SubmissionDraft.assignment_id == item.id, SubmissionDraft.student_id == current.user.id
                ))
                raise AuthError("draft_conflict", "草稿已在其他位置更新。", 409, _draft_view(latest))
        else:
            draft = SubmissionDraft(assignment_id=item.id, student_id=current.user.id, version=1,
                                    values_json=payload.values, updated_at=now)
            db.add(draft)
            db.flush()
        db.add(DraftMutation(draft_id=draft.id, request_id=request_id, version=payload.base_version + 1, created_at=now))
        db.commit()
    except IntegrityError:
        db.rollback()
        latest = db.scalar(select(SubmissionDraft).where(
            SubmissionDraft.assignment_id == item.id, SubmissionDraft.student_id == current.user.id
        ))
        raise AuthError("draft_conflict", "草稿已在其他位置更新。", 409, _draft_view(latest)) from None
    db.refresh(draft)
    return _draft_view(draft)


def _shared_access(db, current, item: Assignment) -> ExperimentGroup:
    if not item.group_sharing_enabled:
        raise AuthError("sharing_disabled", "教师未开启本实验组内共享。", 403)
    group = _group(db, item.id, current.user.id)
    if not group:
        raise AuthError("group_required", "你尚未加入本实验小组。", 403)
    return group


def _shared_view(dataset: SharedDataset | None, group: ExperimentGroup) -> dict:
    return {"groupId": group.id, "groupName": group.name, "version": dataset.version if dataset else 0,
            "values": dataset.values_json if dataset else {}, "sources": dataset.sources_json if dataset else {},
            "updatedAt": dataset.updated_at if dataset else None, "locked": bool(dataset and dataset.locked_at)}


@router.get("/student/assignments/{assignment_id}/shared")
def get_shared(assignment_id: UUID, db: Db, current: Current) -> dict:
    item = _student_assignment(db, current, assignment_id)
    group = _shared_access(db, current, item)
    dataset = db.scalar(select(SharedDataset).where(SharedDataset.group_id == group.id))
    return _shared_view(dataset, group)


@router.put("/student/assignments/{assignment_id}/shared")
def save_shared(assignment_id: UUID, payload: ValuesUpdate, db: Db, current: Current) -> dict:
    item = _student_assignment(db, current, assignment_id)
    _assert_editable(item)
    group = _shared_access(db, current, item)
    _validate_values(db, item, payload.values, shared=True)
    request_id = str(payload.request_id)
    previous = db.scalar(select(SharedDataRevision).where(SharedDataRevision.request_id == request_id))
    if previous:
        dataset = db.get(SharedDataset, previous.dataset_id)
        if not dataset or dataset.group_id != group.id:
            raise AuthError("request_id_reused", "请求编号已被其他操作使用。", 409)
        if dataset.version == previous.version:
            return _shared_view(dataset, group)
        raise AuthError("request_id_reused", "请求编号对应旧版本，请合并最新数据。", 409, _shared_view(dataset, group))
    dataset = db.scalar(select(SharedDataset).where(SharedDataset.group_id == group.id))
    if (dataset.version if dataset else 0) != payload.base_version:
        raise AuthError("shared_conflict", "同组数据已被更新。", 409, _shared_view(dataset, group))
    if dataset and dataset.locked_at:
        raise AuthError("shared_locked", "已提交的组内数据不能修改。", 403)
    now = datetime.now(UTC)
    before = dataset.values_json if dataset else {}
    changes = {key: {"before": before.get(key), "after": payload.values.get(key)}
               for key in set(before) | set(payload.values) if before.get(key) != payload.values.get(key)}
    sources = dict(dataset.sources_json) if dataset else {}
    for key in changes:
        if key in payload.values:
            sources[key] = {"editorId": str(current.user.id), "editorName": current.user.name, "editedAt": now.isoformat()}
        else:
            sources.pop(key, None)
    try:
        if dataset:
            result = db.execute(update(SharedDataset).where(
                SharedDataset.id == dataset.id, SharedDataset.version == payload.base_version,
                SharedDataset.locked_at.is_(None)
            ).values(values_json=payload.values, sources_json=sources, version=payload.base_version + 1, updated_at=now))
            if result.rowcount != 1:
                db.rollback()
                latest = db.scalar(select(SharedDataset).where(SharedDataset.group_id == group.id))
                raise AuthError("shared_conflict", "同组数据已被更新。", 409, _shared_view(latest, group))
        else:
            dataset = SharedDataset(assignment_id=item.id, group_id=group.id, version=1,
                                    values_json=payload.values, sources_json=sources, updated_at=now)
            db.add(dataset)
            db.flush()
        db.add(SharedDataRevision(dataset_id=dataset.id, request_id=request_id,
                                  version=payload.base_version + 1, changes_json=changes,
                                  edited_by=current.user.id, created_at=now))
        db.commit()
    except IntegrityError:
        db.rollback()
        latest = db.scalar(select(SharedDataset).where(SharedDataset.group_id == group.id))
        raise AuthError("shared_conflict", "同组数据已被更新。", 409, _shared_view(latest, group)) from None
    db.refresh(dataset)
    return _shared_view(dataset, group)
