"""A crowd must slow the server down, never freeze it."""
import asyncio

import httpx

from app.config import settings
from app.database import engine
from app.main import app


def _crowd(paths: list[str], headers: dict) -> list[int]:
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=25) as c:
            responses = await asyncio.gather(*(c.get(p, headers=headers) for p in paths))
        return [r.status_code for r in responses]
    return asyncio.run(run())


def test_pool_covers_every_admitted_request():
    assert engine.pool.size() >= settings.max_concurrent_requests


def test_crowd_far_above_the_pool_all_succeed(db, operator):
    """300 reads at once froze the server before the gate: threads waited on connections while
    connection holders waited on threads, until requests timed out after 30 seconds."""
    assert set(_crowd(["/api/op/overview"] * 300, operator)) == {200}


def test_writes_still_reach_connected_clients(client, operator):
    with client.websocket_connect(f"/api/ws?token={operator['Authorization'].split()[1]}") as ws:
        assert client.post("/api/op/groups/run", headers=operator).status_code == 200
        assert ws.receive_json() == {"type": "changed"}


def test_failed_writes_do_not_ping(client, operator):
    from app.routers.common import hub
    calls = []
    original = hub.broadcast

    async def spy():
        calls.append(1)
        await original()
    hub.broadcast = spy
    try:
        assert client.post("/api/op/telemetry/NOPE/resolve", json={"decision": "keep", "reason": "Nothing"},
                           headers=operator).status_code == 404
        assert client.get("/api/op/overview", headers=operator).status_code == 200
    finally:
        hub.broadcast = original
    assert calls == []
