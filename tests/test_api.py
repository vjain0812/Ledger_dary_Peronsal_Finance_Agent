import time
from types import SimpleNamespace

import jwt
import pytest
from fastapi.testclient import TestClient
from langgraph.store.memory import InMemoryStore

from app.auth import SlidingWindowLimiter
from app.main import create_app
from app.memory.tools import save_memory_core

SECRET = "test-secret-test-secret-test-secret"


def token(sub="alice", exp_in=3600, secret=SECRET):
    return jwt.encode({"sub": sub, "exp": int(time.time()) + exp_in}, secret, "HS256")


class FakeAgent:
    def __init__(self):
        self.calls = []

    async def ainvoke(self, payload, config):
        self.calls.append((payload, config))
        return {
            "messages": [
                SimpleNamespace(type="human", content="hi", tool_calls=[]),
                SimpleNamespace(type="ai", content="", tool_calls=[{"name": "save_memory"}]),
                SimpleNamespace(type="ai", content=[{"text": "Hello "}, {"text": "Sam"}], tool_calls=[]),
            ]
        }


@pytest.fixture
def client():
    app = create_app(use_lifespan=False)
    app.state.agent = FakeAgent()
    app.state.store = InMemoryStore()
    return TestClient(app)


def headers(**kw):
    return {"Authorization": f"Bearer {token(**kw)}"}


def test_health_and_ready(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").status_code == 200


def test_chat_requires_valid_token(client):
    body = {"thread_id": "t1", "message": "hi"}
    assert client.post("/chat", json=body).status_code == 401
    assert client.post("/chat", json=body, headers=headers(secret="wrong" * 8)).status_code == 401
    assert client.post("/chat", json=body, headers=headers(exp_in=-10)).status_code == 401


def test_chat_ok_and_user_scoping(client):
    r = client.post("/chat", json={"thread_id": "t1", "message": "hi"}, headers=headers())
    assert r.status_code == 200
    assert r.json() == {"reply": "Hello Sam", "tool_calls": ["save_memory"]}
    _, config = client.app.state.agent.calls[0]
    assert config["configurable"] == {"thread_id": "alice:t1", "user_id": "alice"}
    assert config["recursion_limit"] > 0


def test_client_cannot_override_user_id(client):
    r = client.post(
        "/chat",
        json={"thread_id": "t1", "message": "hi", "user_id": "bob"},
        headers=headers(),
    )
    assert r.status_code == 200
    assert client.app.state.agent.calls[0][1]["configurable"]["user_id"] == "alice"


def test_input_validation(client):
    h = headers()
    assert client.post("/chat", json={"thread_id": "a b", "message": "hi"}, headers=h).status_code == 422
    assert client.post("/chat", json={"thread_id": "t", "message": ""}, headers=h).status_code == 422
    assert client.post("/chat", json={"thread_id": "t", "message": "x" * 2001}, headers=h).status_code == 422


def test_rate_limit(client):
    body = {"thread_id": "t1", "message": "hi"}
    codes = [client.post("/chat", json=body, headers=headers(sub="spammer")).status_code for _ in range(7)]
    assert codes[:5] == [200] * 5
    assert 429 in codes[5:]


async def _seed(store):
    await save_memory_core(store, "carol", "Dining budget is $350", "budget_facts", "dining")
    await save_memory_core(store, "dave", "Keep me", "profile", "p")


def test_erase_my_memory(client):
    import asyncio

    asyncio.run(_seed(client.app.state.store))
    r = client.delete("/me/memory", headers=headers(sub="carol"))
    assert r.json() == {"deleted": 1}
    assert len(asyncio.run(client.app.state.store.asearch(("ledger_dary", "dave")))) == 1


def test_limiter_window():
    lim = SlidingWindowLimiter(2, window_s=10)
    assert lim.allow("k", now=0) and lim.allow("k", now=1)
    assert not lim.allow("k", now=2)
    assert lim.allow("k", now=11)
