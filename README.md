# ledger-dary

Personal finance coach agent (LangGraph + Gemini) with per-thread state (Postgres checkpointer)
and long-term semantic memory (Postgres + pgvector), served by FastAPI. Finance tools run as a
separate MCP service.

## Run locally
```bash
cp .env.example .env        # fill in GOOGLE_API_KEY, JWT_SECRET, POSTGRES_PASSWORD
docker compose up --build
```

Mint a dev token (the API only trusts `sub` from a verified JWT):
```bash
python -c "import jwt,time;print(jwt.encode({'sub':'alice','exp':int(time.time())+3600},'<JWT_SECRET>','HS256'))"
```

```bash
curl -X POST localhost:8080/chat -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"thread_id":"t1","message":"I am saving $2400 for a laptop by March"}'
curl -X DELETE localhost:8080/me/memory -H "Authorization: Bearer $TOKEN"   # erase my data
```

## Endpoints
`GET /health`, `GET /ready`, `POST /chat`, `POST /chat/stream` (SSE), `DELETE /me/memory`.

## Develop
```bash
pip install -e ".[api,mcp,dev]"
ruff check . && pytest
```

## Before real production
- Replace `ddgs` in `app/mcp_server/server.py` with a real search API.
- Replace the in-process rate limiter with Redis if you run more than one replica.
- Swap the regex PII guard in `app/memory/guards.py` for Presidio or similar.
- Issue JWTs from your real identity provider; consider RS256/JWKS instead of a shared secret.
- Add LangSmith tracing, metrics and an eval suite (tool choice, injection, cross-user isolation).
