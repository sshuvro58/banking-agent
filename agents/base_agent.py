"""
Base Agent — the async tool-use loop.

This is THE core pattern of the entire agentic system.

The loop:
  1. Send user message + tool definitions to LLM
  2. LLM responds with either:
     a) Text reply → we're done, return it
     b) Tool calls → execute them, send results back, go to step 1
  3. Repeat until text reply or max rounds hit

Production concerns:
  - Max rounds limit (prevent infinite loops)
  - Cost tracking per LLM call (written to PostgreSQL)
  - Trace recording (written to PostgreSQL)
  - Structured error handling from MCP tools
  - Context injection via system prompt
"""
import json
import logging

from botocore import history
from llm import llm_client
from mcp.base import BaseMCPServer
from db.repositories.observability_repo import observability_repo

logger = logging.getLogger("agent")

MAX_TOOL_ROUNDS = 5  # Safety limit — prevent runaway loops


class BaseAgent:
    def __init__(self, name: str, system_prompt: str, mcp_server: BaseMCPServer):
        print("Calling BaseAgent.__init__")
        self.name = name
        self.system_prompt = system_prompt
        self.mcp_server = mcp_server

    async def run(
        self,
        user_message: str,
        session_id: str,
        context: dict | None = None,
        history: list[dict] | None = None,
    ) -> dict:
        """
        Execute the agent with full async tool-use loop.

        Parameters
        ----------
        user_message : str
            What the user asked (already PII-redacted).
        session_id : str
            For cost tracking and trace attribution.
        context : dict | None
            Injected into the system prompt. Contains customer_id,
            account_ids, and any prior agent context.

        Returns
        -------
        dict with: reply, tool_calls, total_input_tokens,
                   total_output_tokens, total_latency_ms
        """
        # Build system prompt with context
        print("Calling BaseAgent.run")
        system = self.system_prompt
        if context:
            system += f"\n\nContext:\n{json.dumps(context, indent=2, default=str)}"

        # Start the conversation
        messages = []
        if history:
            for msg in history[:-1]:           # exclude the current message (already in history)
                if msg["role"] in ("user", "assistant"):
                    messages.append({
                        "role": msg["role"],
                        "content": msg["content"],
                    })

        # Add the current message
        messages.append({"role": "user", "content": user_message})

        tools = self.mcp_server.get_tool_specs()

        # Accumulators
        all_tool_calls = []
        total_input = 0
        total_output = 0
        total_latency = 0
        total_cost = 0

        for round_num in range(MAX_TOOL_ROUNDS):
            logger.info(f"[{self.name}] Round {round_num + 1}/{MAX_TOOL_ROUNDS}")

            # ── Step 1: Call the LLM ──────────────────
            response = llm_client.invoke(
                messages=messages,
                system_prompt=system,
                tools=tools if tools else None,
                session_id=session_id,
            )

            total_input += response["input_tokens"]
            total_output += response["output_tokens"]
            total_latency += response["latency_ms"]
            total_cost += response["estimated_cost"]

            # Record cost to database
            await observability_repo.record_cost(
                session_id=session_id,
                model=response["model"],
                input_tokens=response["input_tokens"],
                output_tokens=response["output_tokens"],
                estimated_cost=response["estimated_cost"],
            )

            # ── Step 2a: LLM wants to use tools ──────
            if response["tool_uses"]:
                logger.info(
                    f"[{self.name}] LLM requested {len(response['tool_uses'])} tool(s): "
                    f"{[tu['name'] for tu in response['tool_uses']]}"
                )

                # Add assistant's tool-call message to conversation
                assistant_msg = llm_client.build_assistant_message(response["tool_uses"])
                messages.append(assistant_msg)

                # Execute each tool and collect results
                tool_results = []
                for tool_use in response["tool_uses"]:
                    tool_name = tool_use["name"]
                    tool_args = tool_use["arguments"]
                    tool_id = tool_use["id"]

                    logger.info(f"[{self.name}] Executing: {tool_name}({json.dumps(tool_args)})")

                    # Call the MCP tool (async — queries PostgreSQL)
                    result = await self.mcp_server.call_tool(tool_name, tool_args)

                    # Track for response metadata
                    all_tool_calls.append({
                        "tool": tool_name,
                        "input": tool_args,
                        "success": result.success,
                        "error_type": result.error_type.value if result.error_type else None,
                        "execution_ms": result.execution_ms,
                        "round": round_num,
                    })

                    # Build the result string for the LLM
                    if result.success:
                        result_str = json.dumps(result.data, default=str)
                    else:
                        result_str = json.dumps({
                            "error": result.error,
                            "error_type": result.error_type.value if result.error_type else "unknown",
                        })

                    tool_results.append({
                        "id": tool_id,
                        "name": tool_name,
                        "result": result_str,
                        "is_error": not result.success,
                    })

                # Add tool results to conversation
                result_messages = llm_client.build_tool_result_messages(tool_results)
                messages.extend(result_messages)

                # Go back to step 1 — let LLM process the results
                continue

            # ── Step 2b: LLM gave a final text reply ─
            logger.info(f"[{self.name}] Complete — {len(all_tool_calls)} tool call(s) total")

            # Record trace to database
            await observability_repo.record_trace(
                session_id=session_id,
                agent=self.name,
                action="complete",
                tool_calls=all_tool_calls,
                input_tokens=total_input,
                output_tokens=total_output,
                latency_ms=total_latency,
            )

            return {
                "reply": response["reply"] or "I wasn't able to generate a response.",
                "tool_calls": all_tool_calls,
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_latency_ms": total_latency,
                "total_cost": total_cost,
            }

        # ── Hit max rounds ────────────────────────────
        logger.warning(f"[{self.name}] Hit max rounds ({MAX_TOOL_ROUNDS})")

        await observability_repo.record_trace(
            session_id=session_id,
            agent=self.name,
            action="max_rounds_exceeded",
            tool_calls=all_tool_calls,
            input_tokens=total_input,
            output_tokens=total_output,
            latency_ms=total_latency,
            error=f"Exceeded {MAX_TOOL_ROUNDS} tool rounds",
        )

        return {
            "reply": "I've reached the maximum number of steps. Please try rephrasing your request.",
            "tool_calls": all_tool_calls,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_latency_ms": total_latency,
            "total_cost": total_cost,
        }