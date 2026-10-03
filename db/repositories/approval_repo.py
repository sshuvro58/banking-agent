"""
Approval Repository — manages human-in-the-loop approval requests.

High-risk actions (address change, chequebook, KYC) create a pending
approval instead of executing immediately. The action runs only after
a human (customer or bank employee) approves it.
"""
import uuid
import json
import logging
from db.connection import db

logger = logging.getLogger("repo.approval")


class ApprovalRepo:

    async def create_request(
        self,
        session_id: str,
        customer_id: str,
        action: str,
        agent: str,
        tool_name: str,
        tool_arguments: dict,
        expires_minutes: int = 15,
    ) -> dict:
        """Create a pending approval request."""
        approval_id = f"apr_{uuid.uuid4().hex[:8]}"

        row = await db.fetchrow(
            """
            INSERT INTO banking.approval_requests
                (approval_id, session_id, customer_id, action, agent,
                 tool_name, tool_arguments, expires_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7,
                    NOW() + make_interval(mins => $8))
            RETURNING approval_id, session_id, customer_id, action,
                      agent, tool_name, tool_arguments, status,
                      requested_at, expires_at
            """,
            approval_id, session_id, customer_id, action, agent,
            tool_name, json.dumps(tool_arguments), expires_minutes,
        )
        result = dict(row)
        result["requested_at"] = str(result["requested_at"])
        result["expires_at"] = str(result["expires_at"])
        if isinstance(result["tool_arguments"], str):
            result["tool_arguments"] = json.loads(result["tool_arguments"])
        logger.info(f"[APPROVAL] Created {approval_id}: {tool_name} for {customer_id}")
        return result

    async def get_pending(self, session_id: str) -> list[dict]:
        """Get all pending (non-expired) approvals for a session."""
        rows = await db.fetch(
            """
            SELECT approval_id, action, agent, tool_name, tool_arguments,
                   status, requested_at, expires_at
            FROM banking.approval_requests
            WHERE session_id = $1
              AND status = 'pending'
              AND expires_at > NOW()
            ORDER BY requested_at DESC
            """,
            session_id,
        )
        results = []
        for r in rows:
            d = dict(r)
            d["requested_at"] = str(d["requested_at"])
            d["expires_at"] = str(d["expires_at"])
            if isinstance(d["tool_arguments"], str):
                d["tool_arguments"] = json.loads(d["tool_arguments"])
            results.append(d)
        return results

    async def get_by_id(self, approval_id: str) -> dict | None:
        """Get a single approval request."""
        row = await db.fetchrow(
            """
            SELECT approval_id, session_id, customer_id, action, agent,
                   tool_name, tool_arguments, status, requested_at,
                   decided_at, decided_by, decision_note, expires_at
            FROM banking.approval_requests
            WHERE approval_id = $1
            """,
            approval_id,
        )
        if not row:
            return None
        result = dict(row)
        result["requested_at"] = str(result["requested_at"])
        result["expires_at"] = str(result["expires_at"])
        if result.get("decided_at"):
            result["decided_at"] = str(result["decided_at"])
        if isinstance(result["tool_arguments"], str):
            result["tool_arguments"] = json.loads(result["tool_arguments"])
        return result

    async def approve(
        self, approval_id: str, decided_by: str, note: str | None = None
    ) -> dict | None:
        """Mark an approval as approved."""
        row = await db.fetchrow(
            """
            UPDATE banking.approval_requests
            SET status = 'approved', decided_at = NOW(),
                decided_by = $2, decision_note = $3
            WHERE approval_id = $1 AND status = 'pending'
            RETURNING approval_id, tool_name, tool_arguments, status
            """,
            approval_id, decided_by, note,
        )
        if not row:
            return None
        result = dict(row)
        if isinstance(result["tool_arguments"], str):
            result["tool_arguments"] = json.loads(result["tool_arguments"])
        logger.info(f"[APPROVAL] Approved {approval_id} by {decided_by}")
        return result

    async def reject(
        self, approval_id: str, decided_by: str, note: str | None = None
    ) -> dict | None:
        """Mark an approval as rejected."""
        row = await db.fetchrow(
            """
            UPDATE banking.approval_requests
            SET status = 'rejected', decided_at = NOW(),
                decided_by = $2, decision_note = $3
            WHERE approval_id = $1 AND status = 'pending'
            RETURNING approval_id, tool_name, status
            """,
            approval_id, decided_by, note,
        )
        if row:
            logger.info(f"[APPROVAL] Rejected {approval_id} by {decided_by}")
        return dict(row) if row else None

    async def expire_stale(self) -> int:
        """Mark all expired pending requests. Call from a cron/scheduled task."""
        result = await db.execute(
            """
            UPDATE banking.approval_requests
            SET status = 'expired', decided_at = NOW(), decided_by = 'auto:timeout'
            WHERE status = 'pending' AND expires_at <= NOW()
            """
        )
        count = int(result.split(" ")[-1]) if result else 0
        if count > 0:
            logger.info(f"[APPROVAL] Expired {count} stale requests")
        return count


approval_repo = ApprovalRepo()