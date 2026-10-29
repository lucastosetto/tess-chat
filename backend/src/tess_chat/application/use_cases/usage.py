from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from tess_chat.application.ports.unit_of_work import UnitOfWorkFactory
from tess_chat.domain.audit import AuditEvent


@dataclass(frozen=True)
class GetBalance:
    uow: UnitOfWorkFactory

    async def execute(self, user_id: UUID) -> int:
        async with self.uow() as uow:
            return await uow.ledger.balance(user_id)


@dataclass(frozen=True)
class ListActivity:
    uow: UnitOfWorkFactory

    async def execute(self, user_id: UUID, limit: int = 100) -> Sequence[AuditEvent]:
        async with self.uow() as uow:
            return await uow.audit.list_for_actor(user_id, min(max(limit, 1), 500))
