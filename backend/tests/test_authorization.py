from uuid import uuid4

from app.auth.authorization import Action, Authorizer, Principal, Role


def test_student_cannot_open_teacher_workspace() -> None:
    principal = Principal(user_id=uuid4(), role=Role.STUDENT)

    decision = Authorizer().authorize(
        principal,
        Action.VIEW_WORKSPACE,
        {"role": Role.TEACHER},
    )

    assert decision.allowed is False
    assert decision.reason == "forbidden"
