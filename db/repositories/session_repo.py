"""
Session Repository — operations for sessions, conversation history, context, and PII mappings[cite: 1].
Used by the Coordinator Agent and session persistence layer[cite: 1].
"""
import json
import uuid
from db.connection import db


class SessionRepo:

    async def create_session(self, customer_id: str) -> dict:
        """Create a new session record for a customer[cite: 1]."""
        print("Calling SessionRepo.create_session")
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        row = await db.fetchrow(
            """
            INSERT INTO banking.sessions (
                session_id, customer_id, shared_state, agent_context, is_active
            )
            VALUES ($1, $2, '{}'::jsonb, '{}'::jsonb, TRUE)
            RETURNING session_id, customer_id, shared_state, agent_context,
                      is_active, created_at, last_activity
            """,
            session_id,
            customer_id,
        )
        record = dict(row)
        if isinstance(record.get("shared_state"), str):
            record["shared_state"] = json.loads(record["shared_state"])
        if isinstance(record.get("agent_context"), str):
            record["agent_context"] = json.loads(record["agent_context"])
        record["created_at"] = str(record["created_at"])
        record["last_activity"] = str(record["last_activity"])
        return record

    async def get_session(self, session_id: str) -> dict | None:
        """Retrieve an existing session by its session ID[cite: 1]."""
        print("Calling SessionRepo.get_session")
        row = await db.fetchrow(
            """
            SELECT session_id, customer_id, shared_state, agent_context,
                   is_active, created_at, last_activity
            FROM banking.sessions
            WHERE session_id = $1
            """,
            session_id,
        )
        if not row:
            return None
        record = dict(row)
        if isinstance(record.get("shared_state"), str):
            record["shared_state"] = json.loads(record["shared_state"])
        if isinstance(record.get("agent_context"), str):
            record["agent_context"] = json.loads(record["agent_context"])
        record["created_at"] = str(record["created_at"])
        record["last_activity"] = str(record["last_activity"])
        return record

    async def touch_session(self, session_id: str) -> None:
        """Update session's last activity timestamp to the current time[cite: 1]."""
        print("Calling SessionRepo.touch_session")
        await db.execute(
            """
            UPDATE banking.sessions
            SET last_activity = NOW()
            WHERE session_id = $1
            """,
            session_id,
        )

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        agent_used: str | None = None,
    ) -> None:
        """Insert a conversation message and refresh the session timestamp[cite: 1]."""
        print("Calling SessionRepo.add_message")
        await db.execute(
            """
            INSERT INTO banking.conversation_messages (
                session_id, role, content, agent_used
            )
            VALUES ($1, $2, $3, $4)
            """,
            session_id,
            role,
            content,
            agent_used,
        )
        await self.touch_session(session_id)

    async def get_history(self, session_id: str, limit: int = 50) -> list[dict]:
        """Fetch conversation messages ordered chronologically[cite: 1]."""
        print("Calling SessionRepo.get_history")
        rows = await db.fetch(
            """
            SELECT message_id, session_id, role, content, agent_used, created_at
            FROM banking.conversation_messages
            WHERE session_id = $1
            ORDER BY created_at ASC
            LIMIT $2
            """,
            session_id,
            limit,
        )
        history = []
        for r in rows:
            d = dict(r)
            d["created_at"] = str(d["created_at"])
            history.append(d)
        return history

    async def set_shared_state(self, session_id: str, key: str, value: any) -> None:
        """Merge a key-value pair into the session shared_state JSONB field[cite: 1]."""
        print("Calling SessionRepo.set_shared_state")
        payload = json.dumps(value)
        await db.execute(
            """
            UPDATE banking.sessions
            SET shared_state = shared_state || jsonb_build_object($2::text, $3::jsonb)
            WHERE session_id = $1
            """,
            session_id,
            key,
            payload,
        )

    async def set_agent_context(self, session_id: str, agent: str, context: any) -> None:
        """Merge context data for a specific agent into agent_context JSONB[cite: 1]."""
        print("Calling SessionRepo.set_agent_context")
        payload = json.dumps(context)
        await db.execute(
            """
            UPDATE banking.sessions
            SET agent_context = agent_context || jsonb_build_object($2::text, $3::jsonb)
            WHERE session_id = $1
            """,
            session_id,
            agent,
            payload,
        )

    async def store_pii_mapping(
        self, session_id: str, placeholder: str, original: str, pii_type: str
    ) -> None:
        """Record a PII tokenization mapping for a session[cite: 1]."""
        print("Calling SessionRepo.store_pii_mapping")
        await db.execute(
            """
            INSERT INTO banking.pii_redaction_map (
                session_id, placeholder, original, pii_type
            )
            VALUES ($1, $2, $3, $4)
            """,
            session_id,
            placeholder,
            original,
            pii_type,
        )

    async def get_pii_mappings(self, session_id: str) -> dict[str, str]:
        """Retrieve all placeholder-to-original mappings for a session[cite: 1]."""
        print("Calling SessionRepo.get_pii_mappings")
        rows = await db.fetch(
            """
            SELECT placeholder, original
            FROM banking.pii_redaction_map
            WHERE session_id = $1
            """,
            session_id,
        )
        return {r["placeholder"]: r["original"] for r in rows}


# Singleton
session_repo = SessionRepo()