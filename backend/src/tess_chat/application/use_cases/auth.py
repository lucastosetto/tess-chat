from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from tess_chat.application.ports.clock import Clock
from tess_chat.application.ports.email import EmailSender
from tess_chat.application.ports.unit_of_work import UnitOfWorkFactory
from tess_chat.domain import credits, events
from tess_chat.domain.errors import InvalidInput, NotFound
from tess_chat.domain.login_link import LoginLink, hash_token
from tess_chat.domain.user import Role, User


@dataclass(frozen=True)
class SignIn:
    uow: UnitOfWorkFactory
    clock: Clock
    credit_grant: int
    admin_emails: frozenset[str] = frozenset()

    async def execute(self, email: str, name: str, method: str) -> User:
        async with self.uow() as uow:
            user = await uow.users.get_by_email(email.strip().lower())
            if user is None:
                now = self.clock.now()
                role = Role.ADMIN if email.strip().lower() in self.admin_emails else Role.USER
                user = User.register(email, name, now, role)
                await uow.users.add(user)
                entry = credits.grant(user.id, self.credit_grant, now)
                await uow.ledger.add(entry)
                uow.record(
                    events.user_registered(user.id, user.email),
                    events.credits_event("granted", user.id, entry.id, amount=entry.amount),
                )
            uow.record(events.user_logged_in(user.id, method))
            await uow.commit()
            return user


@dataclass(frozen=True)
class GetCurrentUser:
    uow: UnitOfWorkFactory

    async def execute(self, user_id: UUID) -> User:
        async with self.uow() as uow:
            user = await uow.users.get(user_id)
        if user is None:
            raise NotFound("user not found")
        return user


LINKS_PER_WINDOW = 5
LINK_WINDOW = timedelta(minutes=15)


@dataclass(frozen=True)
class SendLoginLink:
    uow: UnitOfWorkFactory
    clock: Clock
    email: EmailSender

    async def execute(self, address: str, url_for: Callable[[str], str]) -> None:
        now = self.clock.now()
        link, token = LoginLink.issue(address, now)
        async with self.uow() as uow:
            if await uow.login_links.count_since(link.email, now - LINK_WINDOW) >= LINKS_PER_WINDOW:
                return
            await uow.login_links.add(link)
            uow.record(events.login_link_sent(link.email))
            await uow.commit()
        await self.email.send(
            link.email,
            "Your Tess magic link",
            f"Sign in to Tess:\n\n{url_for(token)}\n\n"
            "This link expires in 15 minutes and works once. "
            "If you didn't ask for it, ignore this email.",
        )


@dataclass(frozen=True)
class UseLoginLink:
    uow: UnitOfWorkFactory
    clock: Clock
    sign_in: SignIn

    async def execute(self, token: str) -> User:
        async with self.uow() as uow:
            link = await uow.login_links.get_by_hash(hash_token(token))
            if link is None:
                raise InvalidInput("link expired")
            link.use(self.clock.now())
            await uow.login_links.update(link)
            await uow.commit()
        return await self.sign_in.execute(link.email, "", "email_link")
