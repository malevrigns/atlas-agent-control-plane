"""Process-wide HTTP client.

LLM, embedding and similar outbound calls used to construct a fresh
``httpx.AsyncClient`` per request. That pays a TCP/TLS handshake on every
model turn and prevents connection reuse across the agent loop.

One shared client is enough: callers pass per-request timeouts, and the
application lifespan closes the client on shutdown.
"""

from __future__ import annotations

import httpx

_client: httpx.AsyncClient | None = None


def http_client() -> httpx.AsyncClient:
    """Return the shared AsyncClient, creating it on first use."""

    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
            timeout=httpx.Timeout(60.0, connect=10.0),
        )
    return _client


async def aclose_http_client() -> None:
    """Close the shared client. Safe to call when it was never created."""

    global _client
    client, _client = _client, None
    if client is not None and not client.is_closed:
        await client.aclose()
