# Banking Agent — System Workflow

How a single chat turn actually flows through the system today, traced directly from the code
(not from `CLAUDE.md`'s description) as of 2026-10-02. There are two entry points:
`POST /api/auth/login` (once, to get a JWT) and `POST /api/chat` (every turn). This doc follows
`/chat`, since that's the entire product surface — everything else is plumbing or admin views.

## Overview diagram

```
Client
  │  POST /api/chat  {message, session_id?}  +  Authorization: Bearer <JWT>
  ▼
┌─────────────────────────────────────────────────────────────────────┐
│ EdgeLayerMiddleware (api/middleware/edge_layer.py)                  │
│   1. IP blocklist check            → 403 if blocked                 │
│   2. WAF regex body scan           → 403 if SQLi/XSS/traversal match│
└─────────────────────────────────────────────────────────────────────┘
  ▼
┌─────────────────────────────────────────────────────────────────────┐
│ TimeoutMiddleware — whole request aborted at 60s → 504               │
└─────────────────────────────────────────────────────────────────────┘
  ▼
verify_token()  (security/authentication.py)  — decode JWT, no DB call  → 401 if bad/expired
  ▼
session_repo.get_session() / create_session()   (db/repositories/session_repo.py)
  ▼
session_repo.add_message(role="user", <raw text>)        — stored BEFORE redaction
  ▼
pii_redactor.redact()   (security/pii_redaction.py)       — SSN/card/email/phone → [REDACTED_x_n]
  ▼
┌─────────────────────────────────────────────────────────────────────┐
│ CoordinatorAgent.handle_message()  (agents/coordinator.py)           │
│                                                                       │
│  shared_state.active_agent set? ──yes──► LLM: follow-up or new-topic?│
│        │no                                   │follow-up   │new-topic│
│        ▼                                     ▼            ▼         │
│   LLM routing call ◄─────────────────────────────── (re-route)      │
│   {agent, action}                        keep active_agent          │
│        │                                                             │
│        ├─ agent == "general" ──► one more LLM call, return (no DB    │
│        │                          tool access, no authz check)       │
│        │                                                             │
│        └─ agent == accounts/transaction/service:                    │
│             1. check_authorisation(roles, action) — fail-closed      │
│                  denied → audit log + refusal, STOP HERE             │
│             2. build context: customer profile + account_ids         │
│                  (db/repositories/customer_repo, account_repo)       │
│             3. load last 20 messages (session_repo.get_history)      │
│             4. delegate → sub-agent.run(...)                         │
└─────────────────────────────────────────────────────────────────────┘
  ▼  (inside the chosen sub-agent)
┌─────────────────────────────────────────────────────────────────────┐
│ BaseAgent.run()  (agents/base_agent.py) — tool-use loop, ≤5 rounds   │
│                                                                       │
│   loop:                                                              │
│     llm_client.invoke_with_retry(messages, system_prompt, tools)     │
│     record cost to observability_repo (every round, unconditional)   │
│     tool calls requested? ──yes──► mcp_server.call_tool() per tool   │
│                                      (10s timeout, Postgres-backed)   │
│                                      append results, loop again       │
│     no tool calls ──► final reply, record trace, return              │
└─────────────────────────────────────────────────────────────────────┘
  ▼
coordinator persists continuity: shared_state.active_agent/active_action,
agent_context[agent_name] = {last_action, tool_calls}         (session_repo)
  ▼
pii_redactor.restore()     — placeholders swapped back to real values
  ▼
session_repo.add_message(role="assistant", <restored reply>)
  ▼
Response: {reply, session_id, agent_used, cost}
  ▼
EdgeLayerMiddleware adds security headers + access log line
  ▼
Client
```

## Step by step

### 0. Edge layer (`api/middleware/edge_layer.py`)
Runs on *every* request, before routing:
1. **IP blocklist** — `client_ip in BLOCKED_IPS` (empty by default) → 403.
2. **WAF body scan** (POST/PUT/PATCH only) — lowercases the raw body, checks it against
   `BLOCKED_PATTERNS` (`<script>`, `DROP TABLE`, `'; --`, `../../../`, `UNION SELECT`,
   `javascript:`) → 403 `"Request blocked by WAF"` on a match.
3. Request proceeds (`call_next`).
4. **Response headers**: CSP (skipped on `/`, `/docs`, `/openapi.json`, `/redoc`),
   `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, HSTS, `Cache-Control: no-store`.
5. **Access log**: method, path, status, latency, client IP.

`TimeoutMiddleware` wraps everything downstream in a 60s `asyncio.wait_for` → 504 on timeout.

### 1. Auth (`security/authentication.py`)
`verify_token` is a **sync** dependency — decodes the JWT (`python-jose`), no DB round-trip.
Roles come from the token as-is (`user_claims["roles"]`), set once at `/auth/login` time; a 401
here means nothing downstream runs.

### 2. Session resolution (`api/routes.py`, `db/repositories/session_repo.py`)
Client-supplied `session_id` is reused if it resolves in `banking.sessions`; otherwise (missing or
unknown id) a new `sess_<12 hex>` row is created with empty `shared_state`/`agent_context` JSONB.
This row is what makes multi-turn memory possible (see "Cross-turn state" below).

### 3. Store the raw user message
`session_repo.add_message(session_id, "user", req.message)` — the **unredacted** text is what
lands in `banking.conversation_messages`. Redaction happens only for what gets sent to the LLM.

### 4. PII redaction (`security/pii_redaction.py`)
Loads existing placeholder↔original mappings for the session (so repeated values reuse the same
placeholder across turns), regex-matches SSN / credit card / email / phone, replaces each with
`[REDACTED_<TYPE>_<n>]`, and persists new mappings to `banking.pii_redaction_map`. From here on
the LLM never sees real PII.

### 5. Coordinator (`agents/coordinator.py::handle_message`)
This is the orchestration brain, and the only agent the route ever calls directly.

- **Continuity check** — if `shared_state.active_agent` is set, one cheap LLM call
  (`_is_topic_change`) classifies the new message as `follow-up` or `new-topic` against the
  *current* active agent. A follow-up skips routing entirely and reuses `active_agent`/
  `active_action` — this is what lets a bare "yes" or "20" stay with the agent already handling
  the conversation instead of bouncing to `general`.
- **Routing** (`_route_message`, only on new-topic or no active agent) — one LLM call with
  `ROUTING_PROMPT`, forced to return bare JSON `{"agent", "action", "summary"}`. Markdown fences
  are stripped defensively; a JSON parse failure silently falls back to `general`/`general`.
  Cost and a `routing` trace are recorded regardless of outcome.
- **`general`** branch — clears `active_agent`/`active_action`, makes one more LLM call with
  `GENERAL_PROMPT`, and returns directly. No authz check, no DB tool access, no sub-agent.
- **Real-agent branch** (`accounts_agent` / `transaction_agent` / `service_agent`):
  1. **Authorization** (`security/authorization.py`) — `ACTION_ROLE_MAP` lookup, fail-closed
     (unknown action ⇒ denied). Denied ⇒ `authz_denied:<action>` trace + `audit_log` entry +
     refusal string, and the turn ends **before** touching a sub-agent or the database tools.
  2. **Context build** — `customer_repo.get_profile_with_roles` + `account_repo.list_by_customer`
     → `{customer_id, customer_name, account_ids, previous_context}`, JSON-dumped straight into
     the sub-agent's system prompt.
  3. **History load** — last 20 messages, chronological.
  4. **Delegate** to the sub-agent's `run()` (step 6).
  5. **Persist continuity** — `shared_state.active_agent/active_action` and
     `agent_context[agent_name] = {last_action, tool_calls}` for the *next* turn to read back as
     `previous_context`.
  6. Records a `delegated:<agent>:<action>` trace and returns `{reply, agent_used, cost}` — cost is
     re-fetched fresh from `observability_repo`, not accumulated in memory.

### 6. Sub-agent tool-use loop (`agents/base_agent.py::BaseAgent.run`)
Every sub-agent is just a `BaseAgent(name, system_prompt, mcp_server)` — the behavior difference
between accounts/transaction/service is entirely the prompt and which MCP server (tool set) it's
bound to. Loop, capped at `MAX_TOOL_ROUNDS = 5`:
1. System prompt = agent prompt + JSON-dumped context. Messages seeded from history (minus the
   already-stored current turn) + the new user message.
2. `llm_client.invoke_with_retry(messages, system_prompt, tools=mcp_server.get_tool_specs())`.
3. Cost recorded to `observability_repo` after **every** round, unconditionally — a DB hiccup here
   fails the whole turn, not just telemetry.
4. **Tool calls requested** → append the assistant's tool-call message, run each tool via
   `mcp_server.call_tool()` (10s per-tool timeout, Postgres-backed, returns a typed `ToolResult`
   with `success`/`data`/`error`/`ToolErrorType`), fold results back into `messages`, loop again.
   This is how a request like "pay rent" can chain "find the account" → "check the balance" →
   "confirm" across multiple rounds.
5. **No tool calls** → that's the final reply; record a `complete` trace with full tool-call list,
   token totals, latency; return.
6. **5 rounds exhausted, still calling tools** → give up, record `max_rounds_exceeded`, return a
   canned "please rephrase" reply.

### 7–9. Back up the stack
- Reply flows back to the coordinator, then to `api/routes.py`.
- `pii_redactor.restore()` swaps placeholders back to real values — **only** in the outgoing
  string; the stored conversation history stays redacted forever.
- `session_repo.add_message(session_id, "assistant", reply, agent_used=...)`.
- Response: `{reply, session_id, agent_used, cost}` (`cost` = session running total, not just this
  turn).
- Response passes back out through `EdgeLayerMiddleware` for headers + access logging.

## Cross-turn state (what makes it a "conversation" and not isolated calls)

Two JSONB columns on `banking.sessions`, both merged in place with `||` (never overwritten
wholesale):
- `shared_state.active_agent` / `active_action` — read by the coordinator's follow-up/new-topic
  check at the start of every turn.
- `agent_context.<agent_name>` — free-form per-agent handoff notes (currently
  `{last_action, tool_calls}`), surfaced to whichever agent runs next turn as `previous_context`.

Plus two flat tables, both keyed by `session_id`, both outliving a server restart:
- `banking.conversation_messages` — full redacted history.
- `banking.pii_redaction_map` — placeholder ↔ real-value pairs.

## Known issues — the flow above cannot run as-is

These are uncommitted changes currently sitting in the working tree (`git status`: modified, not
committed) that break the chat path at different points:

1. **`agents/base_agent.py:34` — syntax error.**
   ```python
   def __init__(self, name: str, system_prompt: str, mcp_server: BaseMCPServer,, model_id: str | None = None):
   ```
   Double comma. Confirmed with `python3 -m py_compile agents/base_agent.py` → `SyntaxError`.
   Nothing that imports `BaseAgent` (the whole agent system) can load while this is in place.

2. **`llm_client.invoke_with_retry()` doesn't exist on the default provider.** Both
   `agents/coordinator.py` and `agents/base_agent.py` call `llm_client.invoke_with_retry(...)`.
   That method is only defined on `BedrockClient` (`llm/bedrock_client.py:37`). `OpenRouterClient`
   — the **default** (`LLM_PROVIDER` defaults to `"openrouter"` in `config.py`) — has no such
   method, so the very first LLM call of any turn raises `AttributeError` unless
   `LLM_PROVIDER=bedrock` is set.

3. **`llm/openrouter_client.py` — `build_assistant_message` / `build_tool_result_messages` are not
   class methods.** They're defined at column 0, after `OpenRouterClient.invoke`'s closing
   `return`, so they're accidentally module-level functions — `OpenRouterClient` doesn't actually
   implement `BaseLLMClient`'s abstract interface. They also reference `json.dumps` with no
   module-level `import json` (it's only imported locally inside `invoke`), so even calling them
   directly would `NameError`.

4. **`llm/base_client.py`** — `invoke`, `build_assistant_message`, `build_tool_result_messages`,
   and `build_tool_spec` are each defined twice (lines 14–89 duplicated verbatim at 92–167).
   Harmless at runtime (second definition wins), but indicates a double-paste mid-edit.

**Net effect:** today, `POST /api/chat` cannot produce a reply — the process may not even import
cleanly (issue #1), and even with that fixed, the first LLM call fails under the default provider
(issue #2). Fixing #1 and #2 is the minimum needed before any turn in the workflow above can
actually execute end-to-end.
