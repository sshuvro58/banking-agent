# Banking Agentic AI System

A multi-agent banking assistant: a single FastAPI service that authenticates a customer, strips PII
out of their message, asks an LLM which specialist should handle it, and lets that specialist call
PostgreSQL-backed tools to actually answer — balances, transactions, statements, address changes,
cheque book requests, KYC updates.

Everything funnels through one endpoint, `POST /api/chat`. Auth, routing, tool execution, and PII
handling all happen behind it.

## Architecture

```
                        ┌─────────────────────────────────────────────┐
                        │                 main.py                     │
                        │  FastAPI app · lifespan owns the DB pool     │
                        └───────────────────┬───────────────────────--┘
                                             │
                         EdgeLayerMiddleware │  IP blocklist, WAF body-pattern
                        (simulated WAF/edge) │  scan, security headers, logging
                                             ▼
                        ┌───────────────────────────────────────-────┐
                        │           api/routes.py  (/api/*)          │
                        │  /auth/login  /chat  /admin/*  /health     │
                        └───────────────────┬───────────────────────-┘
                                             │
                    POST /api/chat:         ▼
   1. verify_token (JWT, stateless)  ──►  security/authentication.py
   2. get-or-create session          ──►  db/repositories/session_repo.py
   3. store raw user message
   4. redact PII                     ──►  security/pii_redaction.py
   5. delegate ───────────────────────────────────────┐
   6. restore PII in the reply                         │
   7. store assistant response                          │
   8. return {reply, session_id, agent_used, cost}       │
                                                          ▼
                              ┌───────────────────────────────────────────┐
                              │        agents/coordinator.py               │
                              │  the ONLY agent the API route calls        │
                              │  • sticky "active agent" for follow-ups    │
                              │  • LLM classifies intent → agent + action  │
                              │  • RBAC check (fail-closed)                │
                              │  • builds context from Postgres            │
                              │  • loads conversation history              │
                              └───────────────────┬─────────────────────--┘
                                                   │ delegates to one of
                        ┌──────────────────────────┼──────────────────────────┐
                        ▼                          ▼                          ▼
              accounts_agent              transaction_agent              service_agent
             (agents/account_agent.py) (agents/transaction_agent.py) (agents/service_agent.py)
                        │                          │                          │
                        └──────────────┬───────────┴──────────────┬───────────┘
                                        ▼                                      ▼
                              agents/base_agent.py — shared async tool-use loop
                              (LLM ↔ tools, up to MAX_TOOL_ROUNDS)
                                        │
                        ┌───────────────┼───────────────┐
                        ▼               ▼               ▼
                 accounts_mcp    transactions_mcp    service_mcp
                (mcp/accounts_mcp) (mcp/transactions_mcp) (mcp/service_mcp)
                        │               │               │
                        └───────────────┼───────────────┘
                                        ▼
                        db/repositories/*.py  (account, transaction, service, ...)
                                        │
                                        ▼
                                  PostgreSQL (`banking` schema)
```

The LLM itself is behind a provider-agnostic interface (`llm/base_client.py`); which provider actually
runs — OpenRouter (default, 300+ models) or AWS Bedrock — is chosen once at process start from
`LLM_PROVIDER` in `.env`.

### Request flow: `POST /api/chat`

1. **Auth** — `verify_token` decodes the JWT (issued by `POST /api/auth/login`); stateless, no DB call.
2. **Session** — get or create a row in `sessions`.
3. **Store** the raw user message.
4. **Redact PII** — SSNs, card numbers, emails, phone numbers are swapped for placeholders
   (`[REDACTED_EMAIL_1]`, ...) before anything reaches the LLM. Mappings persist to Postgres so they
   survive a restart mid-session.
5. **Coordinator** decides who handles it:
   - If there's an active agent from a prior turn, a cheap LLM call classifies the message as
     "follow-up" or "new-topic" so short replies like "yes" don't get mis-routed.
   - Otherwise (or on topic change), an LLM call classifies intent into `accounts_agent`,
     `transaction_agent`, `service_agent`, or `general`.
   - The action is checked against the caller's roles (`security/authorization.py`, fail-closed —
     unknown actions are denied).
   - Context (customer profile, account IDs, prior agent hand-off data) and recent conversation
     history are assembled and handed to the sub-agent.
6. **Sub-agent** runs the tool-use loop (`agents/base_agent.py`): ask the LLM → it either replies or
   asks for a tool call → the tool call goes through the domain's MCP server, which invokes a
   repository method against Postgres → the result goes back to the LLM → repeat until there's a text
   reply or `MAX_TOOL_ROUNDS` is hit.
7. **Restore PII** in the reply before it's shown to the user (the stored history keeps the redacted
   version).
8. **Response**: `{reply, session_id, agent_used, cost}`.

Every LLM call, on every turn, writes a cost record and a trace record to Postgres
(`observability_repo`), so `/api/admin/*` can answer "what did this session cost" and "what happened."

## Tech stack

| Layer | Technology |
|---|---|
| API framework | FastAPI + Uvicorn |
| Database | PostgreSQL, accessed via raw SQL over `asyncpg` (no ORM) |
| LLM | OpenRouter (default, OpenAI-compatible API) or AWS Bedrock Converse API |
| Auth | JWT (`python-jose`), bcrypt password hashing |
| Agent orchestration | Hand-rolled coordinator + tool-use loop (no external agent framework) |
| Tool layer | Custom MCP-style tool registry (`mcp/`) — async handlers, structured errors, per-tool timeouts |

## Project structure

```
main.py                    FastAPI app, lifespan (DB pool), middleware, static frontend
config.py                  .env-backed config singletons: db_config, llm_config, jwt_config

api/
  routes.py                 /auth/login, /chat, /admin/*, /health
  middleware/edge_layer.py  simulated WAF/edge middleware

agents/
  coordinator.py             routing, authorization, context building, delegation
  base_agent.py               shared async tool-use loop
  account_agent.py            \
  transaction_agent.py         > system prompt + bound MCP server, one per domain
  service_agent.py            /

mcp/
  base.py                    BaseMCPServer, ToolResult, structured ToolErrorType
  accounts_mcp.py / transactions_mcp.py / service_mcp.py   tool registrations per domain

llm/
  base_client.py             provider-agnostic interface
  bedrock_client.py          AWS Bedrock Converse API
  openrouter_client.py       OpenRouter (OpenAI-compatible)

security/
  authentication.py          JWT issue/verify
  authorization.py           RBAC (ACTION_ROLE_MAP, fail-closed)
  pii_redaction.py           regex-based redact/restore, persisted to Postgres

db/
  connection.py               asyncpg pool singleton
  repositories/                one repo per domain: account, customer, transaction, service, session, observability

observability/
  logger.py                   console log format + system metrics (CPU/mem/disk)

frontend/index.html          single static page served at "/"
schema.sql                   authoritative schema + seed data
```

## Setup

Requires a running PostgreSQL instance and an LLM API key (OpenRouter by default).

```bash
python3 -m venv .banking-agent
source .banking-agent/bin/activate
pip install -r requirements.txt

cp .env_example .env   # fill in DB_*, OPENROUTER_API_KEY (or Bedrock settings)

psql "postgresql://USER:PASS@HOST:5432/banking" -f schema.sql   # creates the `banking` schema + seed data

uvicorn main:app --reload --port 8000
```

Then open `http://localhost:8000` for the demo frontend, or `http://localhost:8000/docs` for the
OpenAPI docs.

**Demo login:** seeded customers are `cust_001` (Alice, full access) and `cust_002` (Bob, no
service-request access), password `demo123` — or literally `demo`, which is accepted as a universal
bypass in this environment.

### Environment variables

| Variable | Required | Notes |
|---|---|---|
| `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME` | yes | Postgres connection |
| `LLM_PROVIDER` | no | `openrouter` (default) or `bedrock` |
| `OPENROUTER_API_KEY` | if provider is `openrouter` | |
| `LLM_MODEL` | no | defaults to a free OpenRouter model |
| `LLM_MAX_TOKENS` | no | default `2666` |
| `AWS_REGION`, AWS credentials | if provider is `bedrock` | standard boto3 credential resolution |
| `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_EXPIRY_MINUTES` | no | defaults exist; **the default secret key is not safe for real deployment** |

### Testing

There's no pytest suite — a handful of standalone async scripts, each requiring a live DB and live LLM
credentials:

```bash
python agents/test_agent.py         # BaseAgent + one MCP server
python agents/test_coordinator.py   # full routing + delegation chain
python security/test_security.py    # JWT auth, RBAC, PII redact/restore
```

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/auth/login` | Exchange `customer_id` + `password` for a JWT |
| `POST /api/chat` | The main endpoint — everything above happens here |
| `GET /api/admin/traces`, `/api/admin/traces/{session_id}` | Agent trace history |
| `GET /api/admin/costs`, `/api/admin/costs/{session_id}` | LLM spend |
| `GET /api/admin/metrics` | CPU/memory/disk snapshot |
| `GET /api/admin/history/{session_id}` | Conversation history |
| `GET /api/health` | Liveness check |

## Security notes

This is a demo/reference implementation, not a production banking system:

- PII detection is regex-based (SSN, credit card, email, phone) — it will miss anything that doesn't
  match those patterns.
- The edge-layer WAF is a simplified simulation, not a real one.
- `.env` is git-ignored; rotate any credentials before treating this as more than a local setup.
- Password verification has a `"demo"` universal bypass baked in for the seeded demo accounts.
