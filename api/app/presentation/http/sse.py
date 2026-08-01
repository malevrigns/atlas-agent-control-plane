from collections.abc import AsyncIterator
from json import dumps


def encode_sse(event: str, data: dict) -> str:
    payload = dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


async def iter_sse(events: list[tuple[str, dict]]) -> AsyncIterator[str]:
    for event, data in events:
        yield encode_sse(event, data)
