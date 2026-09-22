from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping
from uuid import UUID


class Role(StrEnum):
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"


class Action(StrEnum):
    VIEW_WORKSPACE = "workspace.view"


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    role: Role


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str | None = None


class Authorizer:
    """Role decisions live behind one interface shared by routes and tests."""

    def authorize(
        self,
        principal: Principal,
        action: Action,
        resource: Mapping[str, object],
    ) -> Decision:
        if action is Action.VIEW_WORKSPACE and resource.get("role") == principal.role:
            return Decision(allowed=True)
        return Decision(allowed=False, reason="forbidden")
