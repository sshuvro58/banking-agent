"""
Coordinator Agent — the orchestrator.

This is the ONLY agent the API route calls. It:
  1. Checks if there's an active agent for this session (ongoing conversation)
  2. If follow-up → skip routing, keep same agent
  3. If new topic → ask the LLM to classify intent (routing)
  4. Checks if the user is authorized for that action
  5. Builds context from PostgreSQL (customer profile, accounts)
  6. Loads conversation history for multi-turn memory
  7. Delegates to the right sub-agent
  8. Records traces and shares context between agents
"""
import json
import time
import logging
from llm import llm_client
from agents.account_agent import accounts_agent
from agents.transaction_agent import transaction_agent
from agents.service_agent import service_agent
from security.authorization import check_authorisation
from db.repositories.customer_repo import customer_repo
from db.repositories.account_repo import account_repo
from db.repositories.session_repo import session_repo
from db.repositories.observability_repo import observability_repo
from db.repositories.approval_repo import approval_repo

logger = logging.getLogger("coordinator")


# ── Routing prompt ────────────────────────────────────

ROUTING_PROMPT = """You are a routing coordinator for a banking assistant.
Your ONLY job is to decide which specialist agent should handle the user's request.

Available agents:
1. "accounts_agent" — balance enquiries, listing accounts, account details
2. "transaction_agent" — transaction history, spending categories, account statements
3. "service_agent" — address changes, cheque book requests, KYC document updates
4. "general" — greetings, general questions, anything that doesn't need a specialist

Respond with ONLY a JSON object. No markdown. No explanation. No backticks.
{"agent": "<agent_name>", "action": "<primary_action>", "summary": "<one-line summary>"}

Valid actions per agent:
- accounts_agent: "balance_enquiry" or "list_accounts"
- transaction_agent: "get_transactions" or "get_statement"
- service_agent: "change_address", "request_chequebook", or "update_kyc"
- general: "general"
"""

# ── General chat prompt ───────────────────────────────

GENERAL_PROMPT = """You are a friendly banking assistant. Respond to greetings
and help users understand what services are available:
- Check account balances
- View transaction history
- Get account statements
- Change address
- Request cheque books
- Update KYC documents

Be concise and welcoming. If the user asks something specific,
tell them you can help with that."""


class CoordinatorAgent:
    def __init__(self):
        self.agents = {
            "accounts_agent": accounts_agent,
            "transaction_agent": transaction_agent,
            "service_agent": service_agent,
        }

    async def handle_message(
        self,
        message: str,
        session_id: str,
        user_claims: dict,
    ) -> dict:
        """
        Main entry point. The API route calls this and nothing else.

        Parameters
        ----------
        message : str
            User's message (already PII-redacted).
        session_id : str
            Active session ID.
        user_claims : dict
            From JWT: {"sub": "cust_001", "name": "Alice", "roles": [...]}

        Returns
        -------
        dict with: reply, agent_used, cost
        """
        customer_id = user_claims["sub"]
        user_roles = user_claims.get("roles", [])
        start_time = time.time()

        # ── Step 0: Check for active agent ────────────
        # If a conversation is ongoing with a specific agent,
        # keep delegating to it unless the user changes topic.
        shared_state = await session_repo.get_shared_state(session_id)
        active_agent_name = shared_state.get("active_agent") if shared_state else None

        if active_agent_name and active_agent_name in self.agents:
            # Check if user is continuing or changing topic
            is_topic_change = await self._is_topic_change(
                message, active_agent_name, session_id
            )

            if not is_topic_change:
                # Follow-up — skip routing, keep same agent
                agent_name = active_agent_name
                action = shared_state.get("active_action", "general")
                logger.info(
                    f"[COORDINATOR] Continuing with {agent_name} (follow-up)"
                )
            else:
                # New topic — route normally
                routing = await self._route_message(message, session_id)
                agent_name = routing.get("agent", "general")
                action = routing.get("action", "general")
                logger.info(
                    f"[COORDINATOR] Topic change → routed to {agent_name}"
                )
        else:
            # No active agent — route normally
            routing = await self._route_message(message, session_id)
            agent_name = routing.get("agent", "general")
            action = routing.get("action", "general")

        logger.info(
            f"[COORDINATOR] → {agent_name} (action={action}) "
            f"session={session_id}"
        )

        # ── Step 1: General messages ──────────────────
        if agent_name == "general":
            # Clear active agent — general doesn't need continuity
            await session_repo.set_shared_state(
                session_id, "active_agent", None
            )
            await session_repo.set_shared_state(
                session_id, "active_action", None
            )
            return await self._handle_general(message, session_id)

        # ── Step 2: Authorization check ───────────────
        if not check_authorisation(user_roles, action):
            await observability_repo.record_trace(
                session_id=session_id,
                agent="coordinator",
                action=f"authz_denied:{action}",
            )
            await observability_repo.audit(
                action="authorization_denied",
                customer_id=customer_id,
                resource=action,
                details={"agent": agent_name, "roles": user_roles},
            )
            return {
                "reply": (
                    f"I'm sorry, but you don't have permission to perform "
                    f"this action ({action}). Please contact your bank "
                    f"to update your access level."
                ),
                "agent_used": "coordinator",
                "cost": await observability_repo.get_session_cost(session_id),
            }

        # ── Step 3: Build context from database ───────
        context = await self._build_agent_context(customer_id, session_id)

        # ── Step 4: Load conversation history ─────────
        history = await session_repo.get_history(session_id, limit=20)

        # ── Step 5: Delegate to sub-agent ─────────────
        agent = self.agents[agent_name]
        result = await agent.run(
            user_message=message,
            session_id=session_id,
            context=context,
            history=history,
        )

        # ── Step 6: Track active agent in session ─────
        await session_repo.set_shared_state(
            session_id, "active_agent", agent_name
        )
        await session_repo.set_shared_state(
            session_id, "active_action", action
        )

        # Store inter-agent context
        await session_repo.set_agent_context(
            session_id,
            agent_name,
            {
                "last_action": action,
                "tool_calls": result.get("tool_calls", []),
            },
        )

        # ── Step 7: Record coordinator trace ──────────
        total_time = (time.time() - start_time) * 1000
        await observability_repo.record_trace(
            session_id=session_id,
            agent="coordinator",
            action=f"delegated:{agent_name}:{action}",
            latency_ms=total_time,
        )

        return {
            "reply": result["reply"],
            "agent_used": agent_name,
            "cost": await observability_repo.get_session_cost(session_id),
        }

    # ── Private methods ───────────────────────────────

    async def _route_message(self, message: str, session_id: str) -> dict:
        """
        Ask the LLM to classify which agent should handle this message.
        Returns: {"agent": "...", "action": "...", "summary": "..."}
        """
        response = llm_client.invoke_with_retry(
            messages=[{"role": "user", "content": message}],
            system_prompt=ROUTING_PROMPT,
            session_id=session_id,
        )

        # Record routing cost + trace
        await observability_repo.record_cost(
            session_id=session_id,
            model=response["model"],
            input_tokens=response["input_tokens"],
            output_tokens=response["output_tokens"],
            estimated_cost=response["estimated_cost"],
        )
        await observability_repo.record_trace(
            session_id=session_id,
            agent="coordinator",
            action="routing",
            input_tokens=response["input_tokens"],
            output_tokens=response["output_tokens"],
            latency_ms=response["latency_ms"],
        )

        # Parse JSON response
        try:
            reply = (response["reply"] or "{}").strip()
            # Strip markdown fences if the LLM added them
            if reply.startswith("```"):
                reply = reply.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            if reply.startswith("json"):
                reply = reply[4:].strip()
            return json.loads(reply)
        except json.JSONDecodeError:
            logger.warning(
                f"[COORDINATOR] Failed to parse routing JSON: {response['reply']}"
            )
            return {"agent": "general", "action": "general"}

    async def _is_topic_change(
        self, message: str, current_agent: str, session_id: str
    ) -> bool:
        """
        Ask the LLM if the user's message is a follow-up to the current
        conversation or a completely new topic.

        This prevents short messages like "20" or "yes" from being
        routed away from the active agent.
        """
        response = llm_client.invoke_with_retry(
            messages=[{"role": "user", "content": message}],
            system_prompt=(
                f"The user is currently in a conversation handled by '{current_agent}'.\n"
                f"Agents: accounts_agent (balances), transaction_agent (transactions), "
                f"service_agent (address/chequebook/KYC).\n\n"
                f"Is the following message a follow-up to the {current_agent} conversation, "
                f"or is it a completely new topic that needs a different agent?\n\n"
                f"Respond with ONLY one word: 'follow-up' or 'new-topic'"
            ),
            session_id=session_id,
        )

        await observability_repo.record_cost(
            session_id=session_id,
            model=response["model"],
            input_tokens=response["input_tokens"],
            output_tokens=response["output_tokens"],
            estimated_cost=response["estimated_cost"],
        )

        reply = (response["reply"] or "").strip().lower()
        is_new = "new" in reply

        logger.info(
            f"[COORDINATOR] Topic check: '{message[:50]}' → "
            f"{'NEW TOPIC' if is_new else 'FOLLOW-UP'}"
        )
        return is_new

    async def _handle_general(self, message: str, session_id: str) -> dict:
        """Handle greetings and general questions without a sub-agent."""
        response = llm_client.invoke_with_retry(
            messages=[{"role": "user", "content": message}],
            system_prompt=GENERAL_PROMPT,
            session_id=session_id,
        )
        await observability_repo.record_cost(
            session_id=session_id,
            model=response["model"],
            input_tokens=response["input_tokens"],
            output_tokens=response["output_tokens"],
            estimated_cost=response["estimated_cost"],
        )
        return {
            "reply": response["reply"] or "Hello! How can I help you today?",
            "agent_used": "general",
            "cost": await observability_repo.get_session_cost(session_id),
        }

    async def _build_agent_context(
        self, customer_id: str, session_id: str
    ) -> dict:
        """
        Build context dict from PostgreSQL for the sub-agent.
        This gets injected into the sub-agent's system prompt.
        """
        # Customer profile
        profile = await customer_repo.get_profile_with_roles(customer_id)

        # Account IDs
        accounts = await account_repo.list_by_customer(customer_id)
        account_ids = [a["account_id"] for a in accounts]

        context = {
            "customer_id": customer_id,
            "customer_name": profile["name"] if profile else "Unknown",
            "account_ids": account_ids,
        }

        # Prior agent context from this session
        shared = await session_repo.get_shared_state(session_id)
        if shared:
            context["previous_context"] = shared

        return context



"""
HITL additions for coordinator.py

Add these methods to your existing CoordinatorAgent class,
and add the approval check at the START of handle_message().
"""

# ── Add this import at the top of coordinator.py ──────
# from db.repositories.approval_repo import approval_repo


# ── Add this block at the START of handle_message(), ──
# ── BEFORE the active agent check (Step 0) ────────────

async def handle_message(self, message, session_id, user_claims):
    customer_id = user_claims["sub"]
    user_roles = user_claims.get("roles", [])
    start_time = time.time()

    # ── Step -1: Check for pending approvals ──────
    pending = await approval_repo.get_pending(session_id)
    if pending:
        intent = await self._check_approval_intent(message, session_id)
        if intent == "approve":
            return await self._execute_approved(pending[0], session_id, user_claims)
        elif intent == "reject":
            return await self._reject_pending(pending[0], session_id)
        # else: user is asking something unrelated, continue normal routing

        # ── Step 0: Check for active agent ────────────



# ── Add these methods to CoordinatorAgent class ───────

async def _check_approval_intent(self, message: str, session_id: str) -> str:
    """
    Ask the LLM if the user's message is approving, rejecting,
    or something unrelated to the pending action.

    Returns: "approve", "reject", or "other"
    """
    response = llm_client.invoke(
        messages=[{"role": "user", "content": message}],
        system_prompt=(
            "The user has a pending action that requires their confirmation. "
            "Based on their message, determine if they are:\n"
            "- Approving/confirming the action (yes, confirm, approve, go ahead, do it, proceed, ok)\n"
            "- Rejecting/cancelling the action (no, cancel, reject, don't, stop, nevermind)\n"
            "- Asking something completely unrelated\n\n"
            "Respond with ONLY one word: 'approve', 'reject', or 'other'"
        ),
        session_id=session_id,
        model_override="anthropic.claude-3-haiku-20240307-v1:0",  # cheap for classification
    )

    await observability_repo.record_cost(
        session_id=session_id,
        model=response["model"],
        input_tokens=response["input_tokens"],
        output_tokens=response["output_tokens"],
        estimated_cost=response["estimated_cost"],
    )

    reply = (response["reply"] or "").strip().lower()
    if "approve" in reply or "confirm" in reply:
        return "approve"
    elif "reject" in reply or "cancel" in reply:
        return "reject"
    return "other"


async def _execute_approved(self, pending: dict, session_id: str, user_claims: dict) -> dict:
    """Execute a tool call that the user just approved."""
    approval_id = pending["approval_id"]
    tool_name = pending["tool_name"]
    tool_arguments = pending["tool_arguments"]
    agent_name = pending["agent"]
    customer_id = user_claims["sub"]

    # Mark as approved in DB
    await approval_repo.approve(approval_id, decided_by=f"customer:{customer_id}")

    # Audit trail
    await observability_repo.audit(
        action="approval_granted",
        customer_id=customer_id,
        resource=tool_name,
        details={"approval_id": approval_id, "tool_arguments": tool_arguments},
    )

    # Build context and execute
    context = await self._build_agent_context(customer_id, session_id)
    agent = self.agents.get(agent_name)

    if not agent:
        return {
            "reply": f"Sorry, I couldn't find the agent to execute your request.",
            "agent_used": "coordinator",
            "cost": await observability_repo.get_session_cost(session_id),
        }

    result = await agent.execute_approved_tool(
        tool_name=tool_name,
        tool_arguments=tool_arguments,
        session_id=session_id,
        context=context,
    )

    # Clear active agent so next message routes fresh
    await session_repo.set_shared_state(session_id, "active_agent", None)

    return {
        "reply": result["reply"],
        "agent_used": agent_name,
        "cost": await observability_repo.get_session_cost(session_id),
    }


async def _reject_pending(self, pending: dict, session_id: str) -> dict:
    """Reject a pending approval."""
    approval_id = pending["approval_id"]
    tool_name = pending["tool_name"]

    await approval_repo.reject(approval_id, decided_by="customer")

    await observability_repo.audit(
        action="approval_rejected",
        resource=tool_name,
        details={"approval_id": approval_id},
    )

    # Clear active agent
    await session_repo.set_shared_state(session_id, "active_agent", None)

    return {
        "reply": f"No problem — I've cancelled the {tool_name.replace('_', ' ')} request. Is there anything else I can help with?",
        "agent_used": "coordinator",
        "cost": await observability_repo.get_session_cost(session_id),
    }

# Singleton
coordinator = CoordinatorAgent()