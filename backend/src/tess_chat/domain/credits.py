import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from tess_chat.domain.errors import InsufficientCredits

TOKENS_PER_PRICE_UNIT = 1_000_000


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cached_input_tokens + other.cached_input_tokens,
        )


@dataclass(frozen=True, kw_only=True)
class ModelPrice:
    model: str
    input_per_mtok: int
    output_per_mtok: int
    cached_input_per_mtok: int

    def cost(self, usage: TokenUsage) -> int:
        uncached = max(usage.input_tokens - usage.cached_input_tokens, 0)
        raw = (
            uncached * self.input_per_mtok
            + usage.cached_input_tokens * self.cached_input_per_mtok
            + usage.output_tokens * self.output_per_mtok
        )
        return math.ceil(raw / TOKENS_PER_PRICE_UNIT)


class EntryKind(StrEnum):
    GRANT = "grant"
    RESERVE = "reserve"
    RELEASE = "release"
    SETTLE = "settle"


@dataclass(frozen=True, kw_only=True)
class LedgerEntry:
    id: UUID
    user_id: UUID
    kind: EntryKind
    amount: int
    created_at: datetime
    reservation_id: UUID | None = None
    message_id: UUID | None = None
    model: str | None = None
    usage: TokenUsage | None = None


def balance(entries: Iterable[LedgerEntry]) -> int:
    return sum(entry.amount for entry in entries)


def grant(user_id: UUID, amount: int, now: datetime) -> LedgerEntry:
    return LedgerEntry(
        id=uuid4(), user_id=user_id, kind=EntryKind.GRANT, amount=amount, created_at=now
    )


def reserve(
    user_id: UUID,
    current_balance: int,
    amount: int,
    now: datetime,
    global_spent: int,
    global_cap: int,
) -> LedgerEntry:
    if amount <= 0:
        amount = 1
    if global_spent + amount > global_cap:
        raise InsufficientCredits("global credit cap reached")
    if current_balance < amount:
        raise InsufficientCredits("not enough credits")
    entry_id = uuid4()
    return LedgerEntry(
        id=entry_id,
        user_id=user_id,
        kind=EntryKind.RESERVE,
        amount=-amount,
        created_at=now,
        reservation_id=entry_id,
    )


def release(reservation: LedgerEntry, now: datetime) -> LedgerEntry:
    return LedgerEntry(
        id=uuid4(),
        user_id=reservation.user_id,
        kind=EntryKind.RELEASE,
        amount=-reservation.amount,
        created_at=now,
        reservation_id=reservation.id,
    )


def settle(
    reservation: LedgerEntry,
    actual_cost: int,
    now: datetime,
    message_id: UUID,
    model: str,
    usage: TokenUsage,
) -> tuple[LedgerEntry, LedgerEntry]:
    return (
        release(reservation, now),
        LedgerEntry(
            id=uuid4(),
            user_id=reservation.user_id,
            kind=EntryKind.SETTLE,
            amount=-actual_cost,
            created_at=now,
            reservation_id=reservation.id,
            message_id=message_id,
            model=model,
            usage=usage,
        ),
    )


def estimate_tokens(text_chars: int) -> int:
    return math.ceil(text_chars / 4)
