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
        response = llm_client.invoke(
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
        response = llm_client.invoke(
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
        response = llm_client.invoke(
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


# Singleton
coordinator = CoordinatorAgent()