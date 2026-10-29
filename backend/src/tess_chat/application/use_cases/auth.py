from dataclasses import dataclass
from uuid import UUID

from tess_chat.application.ports.clock import Clock
from tess_chat.application.ports.unit_of_work import UnitOfWorkFactory
from tess_chat.domain import credits, events
from tess_chat.domain.errors import NotFound
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
