from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


RoleName = Literal["student", "teacher", "admin"]


class LoginRequest(BaseModel):
    account: str = Field(max_length=64)
    password: str = Field(max_length=256)


class StudentEnrollmentIdentity(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    student_number: str = Field(alias="studentNumber", min_length=1, max_length=64)
    phone: str = Field(pattern=r"^1[3-9]\d{9}$")
    model_config = ConfigDict(populate_by_name=True)


class StudentVerificationRequest(StudentEnrollmentIdentity):
    pass


class StudentEnrollmentRequest(StudentEnrollmentIdentity):
    verification_code: str = Field(alias="verificationCode", pattern=r"^\d{6}$")
    password: str = Field(min_length=12, max_length=256)


class VerificationRequested(BaseModel):
    expires_in_seconds: int = Field(alias="expiresInSeconds")
    model_config = ConfigDict(populate_by_name=True)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(alias="currentPassword", min_length=1, max_length=256)
    new_password: str = Field(alias="newPassword", min_length=12, max_length=256)
    model_config = ConfigDict(populate_by_name=True)


class UserView(BaseModel):
    id: UUID
    account: str
    name: str
    role: RoleName
    must_change_password: bool = Field(alias="mustChangePassword")
    enrollment_completed: bool = Field(alias="enrollmentCompleted")
    phone_masked: str | None = Field(alias="phoneMasked")
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class WorkspaceView(BaseModel):
    role: RoleName
    title: str
    description: str
