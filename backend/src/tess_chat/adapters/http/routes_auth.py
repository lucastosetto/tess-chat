from fastapi import APIRouter, Response

from tess_chat.adapters.auth.session import COOKIE_NAME
from tess_chat.adapters.http.dependencies import ContainerDep, CurrentUser
from tess_chat.adapters.http.schemas import AuthConfigOut, DevLoginIn, MeOut, UserOut
from tess_chat.domain.errors import NotFound

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/config")
async def auth_config(container: ContainerDep) -> AuthConfigOut:
    return AuthConfigOut(dev_login=container.auth_dev_mode, google_login=False)


@router.post("/dev-login")
async def dev_login(body: DevLoginIn, response: Response, container: ContainerDep) -> MeOut:
    if not container.auth_dev_mode:
        raise NotFound("dev login disabled")
    user = await container.sign_in.execute(body.email, body.name, "dev")
    response.set_cookie(
        COOKIE_NAME,
        container.sessions.encode(user.id),
        max_age=container.sessions.ttl_seconds,
        httponly=True,
        secure=container.secure_cookies,
        samesite="lax",
    )
    return MeOut(user=UserOut.of(user), balance=await container.get_balance.execute(user.id))


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)


@router.get("/me")
async def me(user: CurrentUser, container: ContainerDep) -> MeOut:
    return MeOut(user=UserOut.of(user), balance=await container.get_balance.execute(user.id))
