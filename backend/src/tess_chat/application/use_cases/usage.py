from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from tess_chat.application.ports.clock import Clock
from tess_chat.application.ports.repositories import UsageRow
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


@dataclass(frozen=True)
class DayUsage:
    day: date
    replies: int = 0
    failed: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    credits: int = 0
    tool_calls: int = 0


@dataclass(frozen=True)
class ModelUsage:
    model: str
    replies: int
    credits: int


@dataclass(frozen=True)
class UsageReport:
    days: Sequence[DayUsage]
    models: Sequence[ModelUsage]
    balance: int


@dataclass(frozen=True)
class GetUsage:
    uow: UnitOfWorkFactory
    clock: Clock

    async def execute(self, user_id: UUID, days: int = 14) -> UsageReport:
        days = min(max(days, 1), 90)
        today = self.clock.now().date()
        first = today - timedelta(days=days - 1)
        since = self.clock.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
            days=days - 1
        )
        async with self.uow() as uow:
            rows = await uow.messages.usage_for_owner(user_id, since)
            balance = await uow.ledger.balance(user_id)
        return UsageReport(
            days=[_day(first + timedelta(days=i), rows) for i in range(days)],
            models=_models(rows),
            balance=balance,
        )


def _day(day: date, rows: Sequence[UsageRow]) -> DayUsage:
    same = [r for r in rows if r.day == day]
    return DayUsage(
        day=day,
        replies=sum(r.replies for r in same),
        failed=sum(r.failed for r in same),
        input_tokens=sum(r.input_tokens for r in same),
        output_tokens=sum(r.output_tokens for r in same),
        credits=sum(r.credits for r in same),
        tool_calls=sum(r.tool_calls for r in same),
    )


def _models(rows: Sequence[UsageRow]) -> list[ModelUsage]:
    totals: dict[str, ModelUsage] = {}
    for r in rows:
        prev = totals.get(r.model, ModelUsage(r.model, 0, 0))
        totals[r.model] = ModelUsage(r.model, prev.replies + r.replies, prev.credits + r.credits)
    used = [m for m in totals.values() if m.replies]
    return sorted(used, key=lambda m: m.credits, reverse=True)
