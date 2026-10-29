from datetime import timedelta

import pytest

from tess_chat.application.use_cases.auth import SendLoginLink, SignIn, UseLoginLink
from tess_chat.domain.errors import InvalidInput
from tests.fakes import FixedClock, MemUnitOfWorkFactory


class Outbox:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append((to, body))


def setup() -> tuple[MemUnitOfWorkFactory, FixedClock, Outbox, SendLoginLink, UseLoginLink]:
    uow, clock, outbox = MemUnitOfWorkFactory(), FixedClock(), Outbox()
    sign_in = SignIn(uow, clock, 1000)
    return uow, clock, outbox, SendLoginLink(uow, clock, outbox), UseLoginLink(uow, clock, sign_in)


async def test_link_signs_in_once() -> None:
    uow, _, outbox, send, use = setup()
    tokens: list[str] = []
    await send.execute(" Ana@Example.com ", lambda t: tokens.append(t) or f"https://x/{t}")
    assert outbox.sent[0][0] == "ana@example.com"
    assert f"https://x/{tokens[0]}" in outbox.sent[0][1]

    user = await use.execute(tokens[0])
    assert user.email == "ana@example.com"
    with pytest.raises(InvalidInput):
        await use.execute(tokens[0])
    assert "auth.login_link_sent" in [e.action for e in uow.store.audit]


async def test_link_expires() -> None:
    _, clock, _, send, use = setup()
    tokens: list[str] = []
    await send.execute("a@b.co", lambda t: tokens.append(t) or t)
    clock.current += timedelta(minutes=16)
    with pytest.raises(InvalidInput):
        await use.execute(tokens[0])


async def test_links_are_rate_limited() -> None:
    _, _, outbox, send, _ = setup()
    for _ in range(7):
        await send.execute("a@b.co", lambda t: t)
    assert len(outbox.sent) == 5
