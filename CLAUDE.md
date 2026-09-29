# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single FastAPI service implementing a multi-agent banking assistant: JWT auth → PII redaction →
LLM-based intent routing → a specialist sub-agent that calls PostgreSQL-backed tools → PII restoration.
One PostgreSQL database (schema `banking`), one venv, one `.env`, one entry point (`main.py`).

There used to be a second, independent FastAPI CRUD service under `api/` (its own venv, SQLAlchemy
models, per-table routes, own `.env`). That's gone — `api/main.py`, `api/models/`, `api/routes/`,
`api/config.py`, `api/database.py`, and `api/schemas.py` were deleted. `api/` is now just two library
modules (`routes.py`, `middleware/edge_layer.py`) imported directly by the root `main.py` and run inside
the root venv. If you see references to a standalone `api/` service in old notes or PRs, they're stale.

## Commands

```bash
source .banking-agent/bin/activate
pip install -r requirements.txt
psql "postgresql://USER:PASS@HOST:5432/banking" -f schema.sql   # (re)create schema + seed data
uvicorn main:app --reload --port 8000
```

Needs a live Postgres (`DB_*` in `.env`) and a live LLM provider (`OPENROUTER_API_KEY` by default, or
AWS Bedrock credentials — see Configuration below). `main.py`'s `lifespan` opens the asyncpg pool on
startup and blocks there if the DB host isn't reachable.

**Run the venv's own `uvicorn`, not a system one.** If `uvicorn` isn't installed inside
`.banking-agent/`, `uvicorn main:app` silently falls through to whatever `uvicorn` is on `$PATH` (e.g.
a system/apt install), which runs under a *different* Python with none of this project's packages —
it dies immediately on `from fastapi import FastAPI`. Confirm with `which uvicorn` after activating.

There's no pytest suite. Testing is a handful of standalone async scripts, each a docstring-documented
`Run: python <file>.py`, each requiring both a live DB and live LLM credentials:

```bash
python agents/test_agent.py         # BaseAgent + one MCP server, tool-use loop
python agents/test_coordinator.py   # full routing + delegation chain through the coordinator
python security/test_security.py   # JWT auth, RBAC, PII redact/restore
```

These live in subdirectories but are meant to be run directly (`python agents/test_agent.py` or `cd
agents && python test_agent.py`), so each starts with a `sys.path.insert(0, repo_root)` shim — Python
would otherwise only see the script's own directory and fail to import `db`/`agents`/`security`/etc.
Follow that same pattern in any new script meant to be run standalone from a subdirectory.

There is no lint, formatter, or CI configured.

## Request flow

Almost everything funnels through one endpoint. `api/routes.py` defines only: `POST /auth/login`,
`POST /chat` (the one user-facing endpoint), a handful of `GET /admin/*` observability views, and
`GET /health`. `POST /chat`:

1. `verify_token` (JWT dependency, `security/authentication.py`) — stateless, no DB call
2. get-or-create the session (`db/repositories/session_repo.py`)
3. store the raw user message
4. `pii_redactor.redact()` — strip PII before it reaches the LLM (`security/pii_redaction.py`)
5. `coordinator.handle_message()` — the entire agent system, see below
6. `pii_redactor.restore()` — put real values back into the reply
7. store the assistant response
8. return `{reply, session_id, agent_used, cost}`

Every request also passes through `EdgeLayerMiddleware` (`api/middleware/edge_layer.py`) first: IP
blocklist, a regex WAF body scan for obvious SQLi/XSS/path-traversal patterns on POST/PUT/PATCH, then
security headers on the way out. It's a simulated edge/WAF layer, not a real one.

## Agent architecture

- **`agents/coordinator.py`** (`CoordinatorAgent`, singleton `coordinator`) — the only agent the API
  route calls. Per message: checks `sessions.shared_state.active_agent` for an ongoing conversation;
  if one exists, asks the LLM a cheap classification ("follow-up" vs "new-topic") before deciding
  whether to re-route, so short replies like "yes" or "20" don't get bounced to a different agent. For
  a new/changed topic it asks the LLM to classify intent into `accounts_agent` / `transaction_agent` /
  `service_agent` / `general` (JSON-only routing prompt), checks RBAC via `security/authorization.py`
  (fail-closed — unknown actions are denied), builds context from `customer_repo`/`account_repo`,
  loads recent conversation history, and delegates. Records cost/trace for every LLM call it makes
  itself (routing, topic-check, general chat) in addition to what the sub-agent records.
- **`agents/base_agent.py`** (`BaseAgent`) — the shared async tool-use loop every sub-agent runs:
  send messages + tool specs to the LLM → either a text reply (done) or tool calls (execute via the
  bound `mcp_server`, feed results back, loop) → up to `MAX_TOOL_ROUNDS` (5). Records cost to
  `observability_repo` after *every* LLM round and a trace at the end — this is unconditional, so a
  DB hiccup here fails the whole turn, not just the telemetry.
- **`agents/{account,transaction,service}_agent.py`** — each is just a `BaseAgent(name, system_prompt,
  mcp_server)` singleton; all the actual behavior difference between sub-agents is the system prompt
  and which MCP server (i.e. which tools) it's bound to.
- **`mcp/`** — one `BaseMCPServer` per domain (`accounts_mcp`, `transactions_mcp`, `service_mcp`),
  each just registering async tool handlers backed by a repository. `call_tool()` enforces a per-tool
  timeout and returns a typed `ToolResult` (`success`, `data`/`error`, `ToolErrorType` enum) — handlers
  raise plain `ValueError` for expected failures (not found, bad input) and that's mapped to
  `ToolErrorType.VALIDATION` automatically; anything else becomes `INTERNAL` with the real exception
  swallowed (logged, not surfaced to the LLM).

Session continuity and inter-agent handoff both live in the `sessions` table as two JSONB columns,
merged in place with `||` (`db/repositories/session_repo.py`): `shared_state` (sticky
`active_agent`/`active_action` for the coordinator's follow-up detection) and `agent_context`
(per-agent data a sub-agent leaves for whoever handles the next turn).

## LLM provider

`llm/base_client.py` defines the provider-agnostic `BaseLLMClient` interface (`invoke`,
`build_assistant_message`, `build_tool_result_messages`, `build_tool_spec`). `llm/__init__.py` reads
`LLM_PROVIDER` from `config.llm_config` **once, at import time**, and constructs a single module-level
`llm_client` singleton (`OpenRouterClient` or `BedrockClient`) — switching providers means restarting
the process, not just changing `.env` at runtime. **OpenRouter is the default** (`LLM_MODEL` defaults
to a free Llama model); Bedrock is opt-in via `LLM_PROVIDER=bedrock`. Every `invoke()` returns the same
shape regardless of provider: `reply, tool_uses, stop_reason, input_tokens, output_tokens,
estimated_cost, latency_ms, model`.

## Data layer

- **`db/connection.py`** — `Database` wraps one `asyncpg` pool, singleton `db`. `await db.connect()` /
  `db.disconnect()` once (done by `main.py`'s lifespan); `execute`/`fetch`/`fetchrow`/`fetchval`
  helpers. **Every query must qualify tables as `banking.<table>`.**
- **`db/repositories/*.py`** — one singleton class per domain (`account_repo`, `customer_repo`,
  `session_repo`, `transaction_repo`, `service_repo`, `observability_repo`). This is the boundary that
  normalizes Postgres types: `Decimal`→`float`, `date`/`timestamptz`→`str`, JSONB text→`dict`. Missing
  rows return `None`/`[]`. `observability_repo` also backs `/admin/*` and writes `audit_log` entries.
  Both `db/__init__.py` and `db/repositories/__init__.py` re-export every singleton, so
  `from db import account_repo` and `from db.repositories.account_repo import account_repo` both work.
- **`schema.sql`** — authoritative schema; `DROP SCHEMA ... CASCADE` then recreate (dev only). Seed
  data: `cust_001` (Alice, all 3 roles) and `cust_002` (Bob, no `request_services`), both bcrypt-hashed
  `demo123`. `customer_repo.verify_password` also accepts the literal string `"demo"` as a universal
  bypass — don't rely on real password checking in this environment.

## Security layer (`security/`)

- **`authentication.py`** — `create_token()` verifies against `customer_repo` (exists, active,
  password) and signs a JWT (`python-jose`) with `sub`/`name`/`roles`/`exp`. `verify_token()` is a sync
  FastAPI dependency that only decodes the JWT — no DB call, roles are baked into the token at login.
- **`authorization.py`** — `ACTION_ROLE_MAP` maps each agent action to one required role; unknown
  actions are denied by default.
- **`pii_redaction.py`** — regex-based (SSN/credit card/email/phone) redact-before-LLM,
  restore-before-user. Mappings persist to `pii_redaction_map` so they survive a restart mid-session,
  and repeated values within a session reuse the same placeholder.

## Configuration (`config.py`)

Reads `.env` at import time via three frozen dataclass singletons, all constructed eagerly at module
load (so a missing required var fails on `import config`, not on first use): `db_config` (`DB_USER/
DB_PASSWORD/DB_HOST/DB_PORT/DB_NAME`, all required), `llm_config` (`LLM_PROVIDER`, `LLM_MODEL`,
`OPENROUTER_API_KEY` required only when provider is `openrouter`, `AWS_REGION`, `LLM_MAX_TOKENS`), and
`jwt_config` (`JWT_SECRET_KEY` — defaults to an insecure dev value, `JWT_ALGORITHM`,
`JWT_EXPIRY_MINUTES`).

`.env` currently contains real-looking AWS keys and an RDS hostname; it's git-ignored (not in history).
Rotate real credentials before treating this as anything beyond a local/dev setup.

## Misc

- `observability/logger.py` configures console logging format and exposes `get_system_metrics()`
  (CPU/memory/disk via `psutil`) for `GET /admin/metrics`. This is separate from `observability_repo`,
  which is the DB-backed trace/cost/audit trail.
- `frontend/index.html` is a single static file served at `/` (and `/static/*`) directly by `main.py`
  — no build step, no framework.
- You'll see `print("Calling <Class>.<method>")` as the first line of most methods across the codebase.
  That's intentional call tracing added on request, not debug leftovers — don't "clean it up" unless
  asked to.
