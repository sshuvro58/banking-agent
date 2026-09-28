"""
Observability Repository — tracking for agent traces, token costs, and audit logs[cite: 1].
Used across coordinator and worker agents for system telemetry[cite: 1].
"""
import json
from db.connection import db


class ObservabilityRepo:

    async def record_trace(
        self,
        session_id: str,
        agent: str,
        action: str,
        tool_calls: list | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: float = 0.0,
        error: str | None = None,
    ) -> int:
        """Insert an agent trace event and return the generated trace_id[cite: 1]."""
        print("Calling ObservabilityRepo.record_trace")
        tool_calls_json = json.dumps(tool_calls or [])
        trace_id = await db.fetchval(
            """
            INSERT INTO banking.agent_traces (
                session_id, agent, action, tool_calls,
                input_tokens, output_tokens, latency_ms, error
            )
            VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8)
            RETURNING trace_id
            """,
            session_id,
            agent,
            action,
            tool_calls_json,
            input_tokens,
            output_tokens,
            latency_ms,
            error,
        )
        return int(trace_id)

    async def get_session_traces(self, session_id: str) -> list[dict]:
        """Fetch all traces for a specific session ordered chronologically[cite: 1]."""
        print("Calling ObservabilityRepo.get_session_traces")
        rows = await db.fetch(
            """
            SELECT trace_id, session_id, agent, action, tool_calls,
                   input_tokens, output_tokens, latency_ms, error, created_at
            FROM banking.agent_traces
            WHERE session_id = $1
            ORDER BY created_at ASC
            """,
            session_id,
        )
        results = []
        for r in rows:
            record = dict(r)
            if isinstance(record.get("tool_calls"), str):
                record["tool_calls"] = json.loads(record["tool_calls"])
            record["latency_ms"] = float(record["latency_ms"])
            record["created_at"] = str(record["created_at"])
            results.append(record)
        return results

    async def get_all_traces(self, limit: int = 100) -> list[dict]:
        """Fetch system-wide traces ordered by most recent first[cite: 1]."""
        print("Calling ObservabilityRepo.get_all_traces")
        rows = await db.fetch(
            """
            SELECT trace_id, session_id, agent, action, tool_calls,
                   input_tokens, output_tokens, latency_ms, error, created_at
            FROM banking.agent_traces
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )
        results = []
        for r in rows:
            record = dict(r)
            if isinstance(record.get("tool_calls"), str):
                record["tool_calls"] = json.loads(record["tool_calls"])
            record["latency_ms"] = float(record["latency_ms"])
            record["created_at"] = str(record["created_at"])
            results.append(record)
        return results

    async def record_cost(
        self,
        session_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        estimated_cost: float,
    ) -> int:
        """Insert a cost tracking record and return the cost_id[cite: 1]."""
        print("Calling ObservabilityRepo.record_cost")
        cost_id = await db.fetchval(
            """
            INSERT INTO banking.cost_records (
                session_id, model, input_tokens, output_tokens, estimated_cost
            )
            VALUES ($1, $2, $3, $4, $5)
            RETURNING cost_id
            """,
            session_id,
            model,
            input_tokens,
            output_tokens,
            estimated_cost,
        )
        return int(cost_id)

    async def get_session_cost(self, session_id: str) -> dict:
        """Aggregate token usage and monetary cost for a given session[cite: 1]."""
        print("Calling ObservabilityRepo.get_session_cost")
        row = await db.fetchrow(
            """
            SELECT
                COUNT(*) AS total_calls,
                COALESCE(SUM(input_tokens), 0) AS total_input_tokens,
                COALESCE(SUM(output_tokens), 0) AS total_output_tokens,
                COALESCE(SUM(estimated_cost), 0.0) AS total_cost_usd
            FROM banking.cost_records
            WHERE session_id = $1
            """,
            session_id,
        )
        return {
            "session_id": session_id,
            "total_calls": int(row["total_calls"]) if row else 0,
            "total_input_tokens": int(row["total_input_tokens"]) if row else 0,
            "total_output_tokens": int(row["total_output_tokens"]) if row else 0,
            "total_cost_usd": float(row["total_cost_usd"]) if row else 0.0,
        }

    async def get_total_cost(self) -> dict:
        """Aggregate token usage and overall cost across all recorded sessions[cite: 1]."""
        print("Calling ObservabilityRepo.get_total_cost")
        row = await db.fetchrow(
            """
            SELECT
                COUNT(*) AS total_calls,
                COALESCE(SUM(estimated_cost), 0.0) AS total_cost_usd
            FROM banking.cost_records
            """
        )
        return {
            "total_calls": int(row["total_calls"]) if row else 0,
            "total_cost_usd": float(row["total_cost_usd"]) if row else 0.0,
        }

    async def audit(
        self,
        action: str,
        customer_id: str | None = None,
        resource: str | None = None,
        details: dict | None = None,
        ip_address: str | None = None,
    ) -> None:
        """Write an entry to the system audit trail[cite: 1]."""
        print("Calling ObservabilityRepo.audit")
        details_json = json.dumps(details or {})
        await db.execute(
            """
            INSERT INTO banking.audit_log (
                customer_id, action, resource, details, ip_address
            )
            VALUES ($1, $2, $3, $4::jsonb, $5::inet)
            """,
            customer_id,
            action,
            resource,
            details_json,
            ip_address,
        )


# Singleton
observability_repo = ObservabilityRepo()