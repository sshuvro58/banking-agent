# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

This is a brand-new FastAPI service (no git repo yet, no tests, `main.py` is currently empty). The
scaffolding present is just settings + database wiring:

- `config.py` — Pydantic `Settings` (loaded from `.env`) exposing `DB_USER`, `DB_PASSWORD`, `DB_HOST`,
  `DB_PORT`, `DB_NAME`, and a computed `database_url` (Postgres via `psycopg2`).
- `database.py` — SQLAlchemy `engine`/`SessionLocal` built from `settings.database_url`, a `Base` for
  models, and a `get_db()` generator meant to be used as a FastAPI dependency (`Depends(get_db)`).
- `main.py` — empty; the FastAPI `app` instance and routes have not been created yet.

There is no `requirements.txt`/`pyproject.toml` in the repo — dependencies only exist as already-installed
packages in the local venv (see below).

## Environment

- Python 3.12, virtualenv at `.banking_agent_api/` (created with `python3 -m venv .banking_agent_api`).
- Activate it with `source .banking_agent_api/bin/activate`.
- Key installed packages: `fastapi`, `uvicorn`, `sqlalchemy`, `psycopg2-binary`, `pydantic`,
  `pydantic-settings`, `python-dotenv`.
- Config is read from a `.env` file in this directory (via `pydantic-settings`'s `env_file=".env"`);
  `Settings()` will fail to instantiate if `DB_USER`, `DB_PASSWORD`, or `DB_NAME` aren't set.

## Commands

Since there's no dependency manifest yet, install packages directly into the venv as they're needed:

```bash
source .banking_agent_api/bin/activate
pip install fastapi uvicorn sqlalchemy psycopg2-binary pydantic-settings python-dotenv
```

Once `main.py` defines a FastAPI `app`, run the dev server with:

```bash
source .banking_agent_api/bin/activate
uvicorn main:app --reload
```

There is no lint config, test suite, or build step configured yet.
