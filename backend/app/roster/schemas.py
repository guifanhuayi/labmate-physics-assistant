from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ClassCreate(BaseModel):
    class_code: str = Field(alias="classCode", min_length=1, max_length=64)
    class_name: str = Field(alias="className", min_length=1, max_length=120)
    semester: str = Field(min_length=1, max_length=32)
    teacher_id: UUID | None = Field(default=None, alias="teacherId")


class ClassView(BaseModel):
    id: UUID
    class_code: str = Field(alias="classCode")
    class_name: str = Field(alias="className")
    semester: str
    teacher_id: UUID = Field(alias="teacherId")
    teacher_name: str = Field(alias="teacherName")
    student_count: int = Field(alias="studentCount")


class TeacherView(BaseModel):
    id: UUID
    account: str
    name: str


class StudentView(BaseModel):
    id: UUID
    account: str
    name: str
    student_number: str = Field(alias="studentNumber")
    joined_at: datetime = Field(alias="joinedAt")
    enrollment_completed: bool = Field(alias="enrollmentCompleted")


class ImportErrorView(BaseModel):
    row: int
    field: str
    message: str


class ImportPreviewView(BaseModel):
    id: UUID
    class_id: UUID = Field(alias="classId")
    source_name: str = Field(alias="sourceName")
    status: str
    valid_count: int = Field(alias="validCount")
    error_count: int = Field(alias="errorCount")
    errors: list[ImportErrorView]


class ImportResultView(BaseModel):
    id: UUID
    created: int
    existing: int
    memberships_added: int = Field(alias="membershipsAdded")
    requires_enrollment: int = Field(alias="requiresEnrollment")
