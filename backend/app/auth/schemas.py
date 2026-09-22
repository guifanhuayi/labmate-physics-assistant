from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


RoleName = Literal["student", "teacher", "admin"]


class LoginRequest(BaseModel):
    account: str = Field(max_length=64)
    password: str = Field(max_length=256)


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
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class WorkspaceView(BaseModel):
    role: RoleName
    title: str
    description: str
