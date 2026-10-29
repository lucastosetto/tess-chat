from typing import Annotated, cast

from fastapi import Depends, Request

from tess_chat.adapters.auth.session import COOKIE_NAME
from tess_chat.adapters.http.container import Container
from tess_chat.domain.errors import NotFound
from tess_chat.domain.user import User


class Unauthenticated(Exception):
    pass


def get_container(request: Request) -> Container:
    return cast(Container, request.app.state.container)


ContainerDep = Annotated[Container, Depends(get_container)]


async def current_user(request: Request, container: ContainerDep) -> User:
    token = request.cookies.get(COOKIE_NAME)
    user_id = container.sessions.decode(token) if token else None
    if user_id is None:
        raise Unauthenticated
    try:
        return await container.current_user.execute(user_id)
    except NotFound as exc:
        raise Unauthenticated from exc


CurrentUser = Annotated[User, Depends(current_user)]
