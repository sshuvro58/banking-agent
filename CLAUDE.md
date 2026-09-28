# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Two independent apps in one repo

This repo contains two separate Python applications that share one PostgreSQL database (the
`banking` schema) but nothing else — no shared code, config, venv, or DB driver.

| | Root (`/`) | `api/` |
|---|---|---|
| Purpose | Agentic banking assistant runtime (repositories + Bedrock LLM client) | Generic CRUD REST service over the same tables |
| DB access | `asyncpg` (async), raw SQL | SQLAlchemy 2.0 ORM (sync, `psycopg2`) |
| Config | `config.py` — frozen dataclasses, `python-dotenv` | `api/config.py` — `pydantic-settings` |
| venv | `.banking-agent/` | `api/.banking_agent_api/` |
| Env file | `/.env` | `/api/.env` |
| Entrypoint | `main.py` (ad-hoc test script, **not** a server) | `uvicorn main:app` |

Imports in each app are relative to that app's directory: root modules do `from db.connection import db`
/ `from config import db_config` (run from repo root); `api/` modules do `from routes import routers` /
`from database import get_db` (run from inside `api/`).

`api/CLAUDE.md` exists but is stale (predates the current code — claims `main.py` is empty and there is
no git repo). Update or delete it if you touch `api/`.

## Commands

### Root app
```bash
source .banking-agent/bin/activate
# requirements.txt is incomplete — it omits boto3 and bcrypt, which the code imports:
pip install asyncpg python-dotenv boto3 bcrypt
psql "postgresql://USER:PASS@HOST:5432/banking" -f schema.sql   # (re)create schema + seed data
python main.py                                                  # runs the test phases
```
`main.py` is a hand-rolled integration harness, not pytest. `async def main()` calls `test_*`
functions in sequence; several are commented out. To run a subset, edit that call list — there is no
test selector. It needs a live database **and** live AWS Bedrock credentials.

### API service
```bash
cd api
source .banking_agent_api/bin/activate
uvicorn main:app --reload
```

There is no lint, formatter, type-checker, or CI configured in either app.

## Root app architecture

- **`config.py`** — reads `.env` at import time. `db_config` (raises `ValueError` if any of
  `DB_USER/DB_PASSWORD/DB_HOST/DB_PORT/DB_NAME` is unset) and `bedrock_config` (`AWS_REGION`,
  `BEDROCK_MODEL_ID`). Both are module-level singletons.
- **`db/connection.py`** — `Database` wraps a single `asyncpg` pool; exported as the singleton `db`.
  Call `await db.connect()` once before use and `await db.disconnect()` after. Helpers:
  `execute` / `fetch` / `fetchrow` / `fetchval`. **All tables are in the `banking` schema — every
  query must qualify names as `banking.<table>`.**
- **`db/repositories/*.py`** — one class per domain, each exported as a singleton
  (`account_repo`, `customer_repo`, `session_repo`, `transaction_repo`, `service_repo`,
  `observability_repo`). Repositories are the boundary that normalizes Postgres types for callers:
  `Decimal` → `float`, `date`/`timestamptz` → `str`, JSONB text → `dict`. Missing rows return
  `None` or `[]`. `UPDATE` methods check the status tag (`res == "UPDATE 1"`) to return a bool.
  These are written to back future MCP servers / agents (coordinator, accounts, transactions, etc.).
- **`llm/bedrock_client.py`** — `BedrockLLM` (singleton `bedrock_llm`) over the Bedrock **Converse
  API** via `boto3` `bedrock-runtime`. It is **synchronous**; async callers use
  `asyncio.to_thread`. `invoke(messages, system_prompt, tools, session_id)` returns a parsed dict
  (`reply`, `tool_uses`, `stop_reason`, `input_tokens`, `output_tokens`, `estimated_cost`,
  `latency_ms`, `raw_message`). `build_tool_spec(name, description, parameters)` is a static helper
  that wraps a JSON-schema fragment into Bedrock's `toolSpec` shape. `MODEL_PRICING` drives the
  cost estimate and only covers a few Claude 3 model IDs (`DEFAULT_PRICING` otherwise).
- **`schema.sql`** — authoritative schema. `DROP SCHEMA ... CASCADE` then recreate (dev only),
  RBAC (`roles` / `customer_roles`), infra tables (`sessions`, `conversation_messages`,
  `agent_traces`, `cost_records`, `pii_redaction_map`, `audit_log`), views (`v_customer_profile`,
  `v_account_summary`, `v_session_costs`), and seed data: customers `cust_001` (Alice, all roles)
  and `cust_002` (Bob, no `request_services`), both with password `demo123`.
  `customer_repo.verify_password` also accepts the literal `"demo"` as a universal bypass.

## API service architecture

`api/main.py` builds the app by iterating `routes.routers` (assembled in `api/routes/__init__.py`).
Per database table there is one file each under `api/models/` (SQLAlchemy, all with
`__table_args__ = {"schema": "banking"}`), `api/routes/` (CRUD router:
`/<entity>/get_all`, `/get/{id}`, `/create`, `/update/{id}`, `/delete/{id}`), and matching
Pydantic v2 schemas in the single `api/schemas.py`. `api/database.py` exposes `engine`,
`SessionLocal`, `Base`, and a `get_db()` FastAPI dependency. It runs no migrations — it expects
`schema.sql` to have been applied already.

## Security note

`/.env` currently contains real-looking AWS access keys committed to a working file (the file is
git-ignored, so not in history). Rotate those credentials and keep secrets out of tracked/shared
files.
