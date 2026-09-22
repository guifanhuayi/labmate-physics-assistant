from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)


class TemplateDraftUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)
    schema_data: dict[str, Any] = Field(alias="schema")
    model_config = ConfigDict(populate_by_name=True)


class TemplateView(BaseModel):
    id: UUID
    name: str
    description: str
    status: str
    schema_data: dict[str, Any] = Field(alias="schema")
    version_count: int = Field(alias="versionCount")
    latest_version_id: UUID | None = Field(alias="latestVersionId")
    model_config = ConfigDict(populate_by_name=True)


class ValidationIssue(BaseModel):
    path: str
    message: str


class ValidationView(BaseModel):
    valid: bool
    issues: list[ValidationIssue]


class TemplateVersionView(BaseModel):
    id: UUID
    template_id: UUID = Field(alias="templateId")
    version_number: int = Field(alias="versionNumber")
    schema_data: dict[str, Any] = Field(alias="schema")
    published_at: datetime = Field(alias="publishedAt")
    model_config = ConfigDict(populate_by_name=True)


class AssignmentCreate(BaseModel):
    template_version_id: UUID = Field(alias="templateVersionId")
    class_id: UUID = Field(alias="classId")
    title: str = Field(min_length=1, max_length=180)
    start_at: datetime = Field(alias="startAt")
    due_at: datetime = Field(alias="dueAt")
    status: Literal["draft", "open"] = "open"


class AssignmentView(BaseModel):
    id: UUID
    template_version_id: UUID = Field(alias="templateVersionId")
    class_id: UUID = Field(alias="classId")
    title: str
    start_at: datetime = Field(alias="startAt")
    due_at: datetime = Field(alias="dueAt")
    status: str


class AssignmentSummary(AssignmentView):
    template_name: str = Field(alias="templateName")
    version_number: int = Field(alias="versionNumber")
    class_name: str = Field(alias="className")
    class_code: str = Field(alias="classCode")
    model_config = ConfigDict(populate_by_name=True)
