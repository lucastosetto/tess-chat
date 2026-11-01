from collections.abc import Sequence
from dataclasses import dataclass

from tess_chat.domain.credits import estimate_tokens
from tess_chat.domain.message import Message

IMAGE_TOKEN_ESTIMATE = 1_000


def message_tokens(message: Message) -> int:
    chars = len(message.content) + sum(len(t.output) + len(t.arguments) for t in message.tool_calls)
    chars += sum(len(a.text or "") for a in message.attachments)
    images = sum(1 for a in message.attachments if a.is_image)
    return estimate_tokens(chars) + images * IMAGE_TOKEN_ESTIMATE


@dataclass(frozen=True)
class CompactionPolicy:
    threshold_tokens: int
    keep_recent: int

    def split(self, messages: Sequence[Message]) -> tuple[list[Message], list[Message]] | None:
        if len(messages) <= self.keep_recent:
            return None
        if sum(message_tokens(m) for m in messages) <= self.threshold_tokens:
            return None
        cut = len(messages) - self.keep_recent
        return list(messages[:cut]), list(messages[cut:])
