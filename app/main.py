import asyncio
import hashlib
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent import build_agent, build_embeddings, text_of, tool_calls_this_turn
from app.auth import SlidingWindowLimiter, get_user_id
from app.config import Settings, get_settings
from app.memory.tools import delete_user_memories, make_memory_tools

log = logging.getLogger("ledger_dary")


class ChatRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    reply: str
    tool_calls: list[str]


def _hash(user_id: str) -> str:
    return hashlib.sha256(user_id.encode()).hexdigest()[:12]


@asynccontextmanager
async def lifespan(app: FastAPI):
    from langchain_mcp_adapters.client import MultiServerMCPClient
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.store.postgres.aio import AsyncPostgresStore

    s = get_settings()
    index = {"dims": s.embed_dims, "embed": build_embeddings(s), "fields": ["content"]}
    async with (
        AsyncPostgresSaver.from_conn_string(s.database_url) as checkpointer,
        AsyncPostgresStore.from_conn_string(s.database_url, index=index) as store,
    ):
        await checkpointer.setup()
        await store.setup()
        mcp_client = MultiServerMCPClient(
            {"ledger-dary": {"transport": "streamable_http", "url": s.mcp_url}}
        )
        mcp_tools = await mcp_client.get_tools()
        memory_tools = make_memory_tools(s.memory_min_score, s.memory_max_chars)
        app.state.store = store
        app.state.agent = build_agent(s, mcp_tools + memory_tools, checkpointer, store)
        log.info("ready", extra={"tools": [t.name for t in mcp_tools + memory_tools]})
        yield


def create_app(use_lifespan: bool = True) -> FastAPI:
    app = FastAPI(title="ledger-dary", lifespan=lifespan if use_lifespan else None)
    limiter = SlidingWindowLimiter(get_settings().rate_limit_per_min)

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        log.info(
            "request",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "status": response.status_code,
                "ms": round((time.perf_counter() - start) * 1000),
            },
        )
        return response

    def limited_user(user_id: str = Depends(get_user_id)) -> str:
        if not limiter.allow(user_id):
            raise HTTPException(status_code=429, detail="Too many requests")
        return user_id

    def run_config(user_id: str, thread_id: str, s: Settings) -> dict:
        return {
            "configurable": {
                # thread ids are namespaced by user so one user can never read another's thread
                "thread_id": f"{user_id}:{thread_id}",
                "user_id": user_id,
            },
            "recursion_limit": s.recursion_limit,
        }

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/ready")
    async def ready(request: Request):
        if getattr(request.app.state, "agent", None) is None:
            raise HTTPException(status_code=503, detail="Agent not ready")
        return {"status": "ready"}

    @app.post("/chat", response_model=ChatResponse)
    async def chat(
        body: ChatRequest,
        request: Request,
        user_id: str = Depends(limited_user),
        s: Settings = Depends(get_settings),
    ):
        agent = request.app.state.agent
        payload = {"messages": [{"role": "user", "content": body.message}]}
        try:
            result = await asyncio.wait_for(
                agent.ainvoke(payload, run_config(user_id, body.thread_id, s)),
                timeout=s.request_timeout_s,
            )
        except TimeoutError:
            raise HTTPException(status_code=504, detail="Request timed out") from None
        except Exception:
            log.exception("agent_error", extra={"user": _hash(user_id)})
            raise HTTPException(status_code=502, detail="The assistant failed. Try again.") from None
        return ChatResponse(reply=text_of(result), tool_calls=tool_calls_this_turn(result))

    @app.post("/chat/stream")
    async def chat_stream(
        body: ChatRequest,
        request: Request,
        user_id: str = Depends(limited_user),
        s: Settings = Depends(get_settings),
    ):
        agent = request.app.state.agent
        payload = {"messages": [{"role": "user", "content": body.message}]}
        config = run_config(user_id, body.thread_id, s)

        async def events():
            try:
                async for chunk, _meta in agent.astream(payload, config, stream_mode="messages"):
                    if getattr(chunk, "type", "") != "AIMessageChunk":
                        continue
                    content = chunk.content
                    if isinstance(content, list):
                        content = "".join(b.get("text", "") for b in content if isinstance(b, dict))
                    if content:
                        yield f"data: {json.dumps({'text': content})}\n\n"
            except Exception:
                log.exception("stream_error", extra={"user": _hash(user_id)})
                yield f"event: error\ndata: {json.dumps({'detail': 'stream failed'})}\n\n"
            yield "event: done\ndata: {}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.delete("/me/memory")
    async def erase_my_memory(request: Request, user_id: str = Depends(limited_user)):
        removed = await delete_user_memories(request.app.state.store, user_id)
        log.info("memory_erased", extra={"user": _hash(user_id), "count": removed})
        return {"deleted": removed}

    return app


logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")
app = create_app()
