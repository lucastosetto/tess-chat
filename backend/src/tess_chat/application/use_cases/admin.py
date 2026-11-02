from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

from tess_chat.application.ports.clock import Clock
from tess_chat.application.ports.repositories import FailureStat, ToolStat, UserUsage
from tess_chat.application.ports.unit_of_work import UnitOfWorkFactory
from tess_chat.domain.errors import Forbidden
from tess_chat.domain.user import Role, User

TOP = 10


@dataclass(frozen=True)
class AdminUsage:
    days: int
    users: Sequence[UserUsage]
    total_spent: int
    tools: Sequence[ToolStat] = ()
    failures: Sequence[FailureStat] = ()


@dataclass(frozen=True)
class GetAdminUsage:
    uow: UnitOfWorkFactory
    clock: Clock

    async def execute(self, user: User, days: int = 30) -> AdminUsage:
        if user.role != Role.ADMIN:
            raise Forbidden("admins only")
        days = min(max(days, 1), 365)
        async with self.uow() as uow:
            since = self.clock.now() - timedelta(days=days)
            users = await uow.users.usage_overview(since)
            return AdminUsage(
                days,
                users,
                await uow.ledger.total_spent(),
                await uow.messages.tool_overview(since, TOP),
                await uow.messages.failure_overview(since, TOP),
            )
