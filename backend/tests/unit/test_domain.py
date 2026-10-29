from datetime import UTC, datetime
from uuid import uuid4

import pytest

from tess_chat.domain import credits
from tess_chat.domain.conversation import DEFAULT_TITLE, Conversation
from tess_chat.domain.credits import ModelPrice, TokenUsage
from tess_chat.domain.errors import InsufficientCredits, InvalidInput, NotFound
from tess_chat.domain.message import Message
from tess_chat.domain.user import User

NOW = datetime(2026, 10, 29, tzinfo=UTC)
PRICE = ModelPrice(
    model="m", input_per_mtok=1_000_000, output_per_mtok=4_000_000, cached_input_per_mtok=100_000
)


def test_price_cost_splits_cached_input_and_rounds_up() -> None:
    usage = TokenUsage(input_tokens=1000, output_tokens=10, cached_input_tokens=400)
    assert PRICE.cost(usage) == 600 + 40 + 40
    assert PRICE.cost(TokenUsage(input_tokens=1)) == 1


def test_reserve_settle_and_release_keep_balance_consistent() -> None:
    user_id = uuid4()
    entries = [credits.grant(user_id, 1000, NOW)]
    reservation = credits.reserve(user_id, credits.balance(entries), 300, NOW, 0, 10_000)
    entries.append(reservation)
    assert credits.balance(entries) == 700
    released, settled = credits.settle(reservation, 120, NOW, uuid4(), "m", TokenUsage(1, 1))
    entries += [released, settled]
    assert credits.balance(entries) == 880


def test_reserve_refuses_when_user_or_global_cap_is_exceeded() -> None:
    user_id = uuid4()
    with pytest.raises(InsufficientCredits):
        credits.reserve(user_id, 100, 101, NOW, 0, 10_000)
    with pytest.raises(InsufficientCredits):
        credits.reserve(user_id, 1000, 10, NOW, 9_995, 10_000)


def test_release_reverses_reservation() -> None:
    reservation = credits.reserve(uuid4(), 100, 40, NOW, 0, 1000)
    assert credits.release(reservation, NOW).amount == 40


def test_conversation_visibility_and_rename() -> None:
    owner = uuid4()
    conversation = Conversation.start(owner, NOW)
    assert conversation.title == DEFAULT_TITLE
    conversation.rename("  Trip   plans ", NOW)
    assert conversation.title == "Trip plans"
    with pytest.raises(NotFound):
        conversation.ensure_visible_to(uuid4())
    conversation.delete(NOW)
    with pytest.raises(NotFound):
        conversation.ensure_visible_to(owner)


def test_message_validation() -> None:
    with pytest.raises(InvalidInput):
        Message.from_user(uuid4(), "   ", NOW)
    assert Message.from_user(uuid4(), " hi ", NOW).content == "hi"


def test_user_email_is_normalized() -> None:
    user = User.register(" Ana@Example.COM ", "", NOW)
    assert user.email == "ana@example.com"
    assert user.name == "ana"
    with pytest.raises(InvalidInput):
        User.register("nope", "", NOW)
