from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.api.deps import CurrentUser, DbDep, LimiterDep, SettingsDep, client_ip
from app.core.config import Settings
from app.core.rate_limit import enforce
from app.core.security import CSRF_COOKIE, SESSION_COOKIE, new_csrf_token
from app.schemas.auth import CsrfOut, LoginRequest, RegisterRequest, UserOut
from app.services import auth as auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session_cookie(response: Response, settings: Settings, token: str, max_age: int) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


def _rotate_csrf_cookie(response: Response, settings: Settings) -> str:
    token = new_csrf_token(settings.session_secret)
    # Not HttpOnly by design: the frontend reads it and echoes it in the X-CSRF-Token header.
    response.set_cookie(CSRF_COOKIE, token, httponly=False, secure=settings.secure_cookies, samesite="lax", path="/")
    return token


@router.get("/csrf", response_model=CsrfOut)
def csrf(response: Response, settings: SettingsDep) -> CsrfOut:
    return CsrfOut(csrf_token=_rotate_csrf_cookie(response, settings))


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    body: RegisterRequest, request: Request, response: Response, db: DbDep, settings: SettingsDep, limiter: LimiterDep
) -> UserOut:
    enforce(limiter, f"register:ip:{client_ip(request)}", settings.register_rate_limit_per_hour, 3600)
    issued = auth_service.register(db, settings, email=body.email, password=body.password, timezone=body.timezone)
    _set_session_cookie(response, settings, issued.token, issued.max_age_seconds)
    _rotate_csrf_cookie(response, settings)
    return UserOut.model_validate(issued.user)


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest, request: Request, response: Response, db: DbDep, settings: SettingsDep, limiter: LimiterDep
) -> UserOut:
    ip = client_ip(request)
    # Two limits: one slows guessing against a single account, the other slows spraying across accounts.
    enforce(limiter, f"login:ip:{ip}", settings.login_ip_rate_limit_per_minute, 60)
    enforce(
        limiter, f"login:acct:{auth_service.normalize_email(body.email)}:{ip}", settings.login_rate_limit_per_minute, 60
    )
    issued = auth_service.login(db, settings, email=body.email, password=body.password)
    _set_session_cookie(response, settings, issued.token, issued.max_age_seconds)
    _rotate_csrf_cookie(response, settings)
    return UserOut.model_validate(issued.user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: DbDep, settings: SettingsDep) -> Response:
    auth_service.logout(db, request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/", secure=settings.secure_cookies, httponly=True, samesite="lax")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
