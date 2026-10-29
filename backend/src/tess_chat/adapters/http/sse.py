import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

HEARTBEAT_SECONDS = 15.0


def format_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


async def with_heartbeat(source: AsyncIterator[str]) -> AsyncIterator[str]:
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def pump() -> None:
        try:
            async for item in source:
                await queue.put(item)
        finally:
            await queue.put(None)

    task = asyncio.create_task(pump())
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), HEARTBEAT_SECONDS)
            except TimeoutError:
                yield ": ping\n\n"
                continue
            if item is None:
                break
            yield item
        await task
    finally:
        if not task.done():
            task.cancel()
