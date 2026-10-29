import secrets
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse

from tess_chat.adapters.auth.google import GoogleAuthError
from tess_chat.adapters.auth.session import COOKIE_NAME
from tess_chat.adapters.http.container import Container
from tess_chat.adapters.http.dependencies import ContainerDep, CurrentUser
from tess_chat.adapters.http.schemas import AuthConfigOut, EmailLoginIn, MeOut, UserOut
from tess_chat.domain.errors import InvalidInput, NotFound

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/config")
async def auth_config(container: ContainerDep) -> AuthConfigOut:
    return AuthConfigOut(
        google_login=container.google is not None,
        email_login=container.send_login_link is not None,
    )


@router.get("/google")
async def google_start(request: Request, container: ContainerDep) -> RedirectResponse:
    if container.google is None:
        raise NotFound("google login disabled")
    state = secrets.token_urlsafe(24)
    response = RedirectResponse(container.google.authorize_url(_callback(request), state))
    response.set_cookie(
        STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        secure=container.secure_cookies,
        samesite="lax",
    )
    return response


@router.get("/google/callback")
async def google_callback(
    request: Request, container: ContainerDep, code: str = "", state: str = ""
) -> RedirectResponse:
    if container.google is None:
        raise NotFound("google login disabled")
    expected = request.cookies.get(STATE_COOKIE)
    if not code or not expected or not secrets.compare_digest(state, expected):
        return _failed()
    try:
        profile = await container.google.profile(code, _callback(request))
    except GoogleAuthError:
        return _failed()
    user = await container.sign_in.execute(profile.email, profile.name, "google")
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(STATE_COOKIE)
    _start_session(response, container, user.id)
    return response


@router.post("/email", status_code=202)
async def email_start(body: EmailLoginIn, request: Request, container: ContainerDep) -> None:
    if container.send_login_link is None:
        raise NotFound("email login disabled")
    callback = request.url_for("email_callback")
    await container.send_login_link.execute(
        body.email, lambda token: str(callback.include_query_params(token=token))
    )


@router.get("/email/callback")
async def email_callback(container: ContainerDep, token: str = "") -> RedirectResponse:
    try:
        user = await container.use_login_link.execute(token)
    except InvalidInput:
        return RedirectResponse("/login?error=link", status_code=303)
    response = RedirectResponse("/", status_code=303)
    _start_session(response, container, user.id)
    return response


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)


@router.get("/me")
async def me(user: CurrentUser, container: ContainerDep) -> MeOut:
    return MeOut(user=UserOut.of(user), balance=await container.get_balance.execute(user.id))


STATE_COOKIE = "tess_oauth_state"


def _callback(request: Request) -> str:
    return str(request.url_for("google_callback"))


def _failed() -> RedirectResponse:
    response = RedirectResponse("/login?error=google", status_code=303)
    response.delete_cookie(STATE_COOKIE)
    return response


def _start_session(response: Response, container: Container, user_id: UUID) -> None:
    response.set_cookie(
        COOKIE_NAME,
        container.sessions.encode(user_id),
        max_age=container.sessions.ttl_seconds,
        httponly=True,
        secure=container.secure_cookies,
        samesite="lax",
    )
