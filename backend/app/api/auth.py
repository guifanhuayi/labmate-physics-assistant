from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response
from sqlalchemy.orm import Session

from app.auth.authorization import Action, Authorizer, Principal, Role
from app.auth.errors import AuthError
from app.auth.schemas import (
    AuthModeView,
    ChangePasswordRequest,
    LoginRequest,
    RoleName,
    StudentEnrollmentRequest,
    StudentVerificationRequest,
    UserView,
    VerificationRequested,
    WorkspaceView,
)
from app.auth.service import AuthService, CurrentSession
from app.config import Settings, get_settings
from app.db.session import get_db


router = APIRouter(prefix="/api")
settings = get_settings()
auth_service = AuthService(settings)
authorizer = Authorizer()


def set_session_cookie(response: Response, token: str, config: Settings) -> None:
    response.set_cookie(
        config.session_cookie_name,
        token,
        max_age=config.session_hours * 60 * 60,
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
        path="/",
    )


def read_current_session(
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
) -> CurrentSession:
    return auth_service.current(db, token)


@router.get("/auth/mode", response_model=AuthModeView)
def auth_mode() -> AuthModeView:
    return AuthModeView(
        demoEnabled=settings.demo_auth_enabled,
        demoAccounts={
            "student": "",
            "teacher": settings.demo_teacher_account,
            "admin": settings.demo_admin_account,
        } if settings.demo_auth_enabled else {},
    )


@router.post("/auth/login", response_model=UserView)
def login(payload: LoginRequest, request: Request, response: Response, db: Annotated[Session, Depends(get_db)]) -> UserView:
    result = auth_service.authenticate(db, payload.account, payload.password, request.client.host if request.client else None)
    set_session_cookie(response, result.token, settings)
    return UserView.model_validate(result.user)


@router.post("/auth/student-enrollment/sms", response_model=VerificationRequested, status_code=202)
def request_student_verification(
    payload: StudentVerificationRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> VerificationRequested:
    expires_in = auth_service.request_student_verification(
        db,
        name=payload.name,
        student_number=payload.student_number,
        phone=payload.phone,
        client_ip=request.client.host if request.client else None,
    )
    return VerificationRequested(expiresInSeconds=expires_in)


@router.post("/auth/student-enrollment/complete", response_model=UserView)
def complete_student_enrollment(
    payload: StudentEnrollmentRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> UserView:
    result = auth_service.complete_student_enrollment(
        db,
        name=payload.name,
        student_number=payload.student_number,
        phone=payload.phone,
        verification_code=payload.verification_code,
        password=payload.password,
        client_ip=request.client.host if request.client else None,
    )
    set_session_cookie(response, result.token, settings)
    return UserView.model_validate(result.user)


@router.get("/auth/me", response_model=UserView)
def me(current: Annotated[CurrentSession, Depends(read_current_session)]) -> UserView:
    return UserView.model_validate(current.user)


@router.post("/auth/change-initial-password", response_model=UserView)
def change_initial_password(
    payload: ChangePasswordRequest,
    response: Response,
    current: Annotated[CurrentSession, Depends(read_current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> UserView:
    result = auth_service.change_initial_password(db, current, payload.current_password, payload.new_password)
    set_session_cookie(response, result.token, settings)
    return UserView.model_validate(result.user)


@router.post("/auth/logout", status_code=204)
def logout(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
) -> None:
    current = None
    if token:
        try:
            current = auth_service.current(db, token)
        except AuthError:
            current = None
    auth_service.logout(db, current)
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/workspaces/{role}", response_model=WorkspaceView)
def workspace(
    role: RoleName,
    current: Annotated[CurrentSession, Depends(read_current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> WorkspaceView:
    decision = authorizer.authorize(
        Principal(user_id=current.user.id, role=Role(current.user.role)),
        Action.VIEW_WORKSPACE,
        {"role": Role(role)},
    )
    if not decision.allowed:
        auth_service.audit_denied(db, current.user, role)
        raise AuthError("forbidden", "你没有权限访问这个工作台。", 403)
    content = {
        "student": ("学生工作台", "实验任务将在后续功能中开放。"),
        "teacher": ("教师工作台", "班级、模板和审核功能将在后续切片中开放。"),
        "admin": ("管理员工作台", "账号与组织管理将在名单导入阶段开放。"),
    }
    title, description = content[role]
    return WorkspaceView(role=role, title=title, description=description)
