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
"""
Base Agent — async tool-use loop WITH human-in-the-loop support.

Changes from the original:
  - Before executing a tool, checks if it needs approval
  - If yes: creates an approval_request, tells the LLM it's pending
  - The LLM then asks the user to confirm
  - On the next turn, coordinator detects the approval and executes
"""
import json
import logging
from llm import llm_client
from mcp.base import BaseMCPServer
from db.repositories.observability_repo import observability_repo
from db.repositories.approval_repo import approval_repo
from agents.hilt_config import needs_approval, get_approver_type


logger = logging.getLogger("agent")

MAX_TOOL_ROUNDS = 5


class BaseAgent:
    def __init__(self, name: str, system_prompt: str, mcp_server: BaseMCPServer, model_id: str | None = None):
        self.name = name
        self.system_prompt = system_prompt
        self.mcp_server = mcp_server
        self.model_id = model_id

    async def run(
        self,
        user_message: str,
        session_id: str,
        context: dict | None = None,
        history: list[dict] | None = None,
    ) -> dict:
        system = self.system_prompt
        if context:
            system += f"\n\nContext:\n{json.dumps(context, indent=2, default=str)}"

        # Build messages from history
        messages = []
        if history:
            for msg in history[:-1]:
                if msg["role"] in ("user", "assistant"):
                    messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_message})

        tools = self.mcp_server.get_tool_specs()

        all_tool_calls = []
        total_input = 0
        total_output = 0
        total_latency = 0
        total_cost = 0

        for round_num in range(MAX_TOOL_ROUNDS):
            logger.info(f"[{self.name}] Round {round_num + 1}/{MAX_TOOL_ROUNDS}")

            response = llm_client.invoke(
                messages=messages,
                system_prompt=system,
                tools=tools if tools else None,
                session_id=session_id,
                model_override=self.model_id,
            )

            total_input += response["input_tokens"]
            total_output += response["output_tokens"]
            total_latency += response["latency_ms"]
            total_cost += response["estimated_cost"]

            await observability_repo.record_cost(
                session_id=session_id,
                model=response["model"],
                input_tokens=response["input_tokens"],
                output_tokens=response["output_tokens"],
                estimated_cost=response["estimated_cost"],
            )

            # ── Guardrail blocked ─────────────────────
            if response["stop_reason"] == "guardrail":
                return {
                    "reply": response["reply"],
                    "tool_calls": all_tool_calls,
                    "total_input_tokens": total_input,
                    "total_output_tokens": total_output,
                    "total_latency_ms": total_latency,
                    "total_cost": total_cost,
                }

            # ── Tool use ────────needs_approval──────────────────────
            if response["tool_uses"]:
                logger.info(
                    f"[{self.name}] LLM requested {len(response['tool_uses'])} tool(s): "
                    f"{[tu['name'] for tu in response['tool_uses']]}"
                )

                assistant_msg = llm_client.build_assistant_message(response["tool_uses"])
                messages.append(assistant_msg)

                tool_results = []
                approval_created = False

                for tool_use in response["tool_uses"]:
                    tool_name = tool_use["name"]
                    tool_args = tool_use["arguments"]
                    tool_id = tool_use["id"]

                    # ── HITL CHECK ────────────────────
                    if needs_approval(tool_name):
                        approver = get_approver_type(tool_name)
                        customer_id = (context or {}).get("customer_id", "unknown")

                        # Create pending approval
                        approval = await approval_repo.create_request(
                            session_id=session_id,
                            customer_id=customer_id,
                            action=tool_name,
                            agent=self.name,
                            tool_name=tool_name,
                            tool_arguments=tool_args,
                        )

                        all_tool_calls.append({
                            "tool": tool_name,
                            "input": tool_args,
                            "success": False,
                            "status": "pending_approval",
                            "approval_id": approval["approval_id"],
                            "approver": approver,
                            "round": round_num,
                        })

                        # Tell the LLM the action is pending approval
                        if approver == "customer":
                            pending_msg = (
                                f"Action '{tool_name}' requires customer confirmation before execution. "
                                f"Approval ID: {approval['approval_id']}. "
                                f"Please ask the customer to confirm they want to proceed with: "
                                f"{json.dumps(tool_args, default=str)}. "
                                f"Do NOT execute the action — just ask for confirmation."
                            )
                        else:
                            pending_msg = (
                                f"Action '{tool_name}' requires approval from a bank employee. "
                                f"Approval ID: {approval['approval_id']}. "
                                f"Tell the customer their request has been submitted for review "
                                f"and they will be notified once approved."
                            )

                        tool_results.append({
                            "id": tool_id,
                            "name": tool_name,
                            "result": json.dumps({
                                "status": "pending_approval",
                                "approval_id": approval["approval_id"],
                                "message": pending_msg,
                            }),
                            "is_error": False,
                        })
                        approval_created = True
                        logger.info(
                            f"[{self.name}] HITL: {tool_name} needs {approver} approval "
                            f"(approval_id={approval['approval_id']})"
                        )

                    else:
                        # ── Normal execution (no approval needed) ──
                        logger.info(f"[{self.name}] Executing: {tool_name}")
                        result = await self.mcp_server.call_tool(tool_name, tool_args)

                        all_tool_calls.append({
                            "tool": tool_name,
                            "input": tool_args,
                            "success": result.success,
                            "error_type": result.error_type.value if result.error_type else None,
                            "execution_ms": result.execution_ms,
                            "round": round_num,
                        })

                        result_str = json.dumps(
                            result.data if result.success else {"error": result.error},
                            default=str,
                        )
                        tool_results.append({
                            "id": tool_id,
                            "name": tool_name,
                            "result": result_str,
                            "is_error": not result.success,
                        })

                result_messages = llm_client.build_tool_result_messages(tool_results)
                messages.extend(result_messages)

                # If we created an approval, let the LLM generate the
                # confirmation message and return — don't loop again
                if approval_created:
                    confirm_response = llm_client.invoke(
                        messages=messages,
                        system_prompt=system,
                        tools=tools,        
                        session_id=session_id,
                        model_override=self.model_id,
                    )
                    total_input += confirm_response["input_tokens"]
                    total_output += confirm_response["output_tokens"]
                    total_latency += confirm_response["latency_ms"]
                    total_cost += confirm_response["estimated_cost"]

                    await observability_repo.record_trace(
                        session_id=session_id,
                        agent=self.name,
                        action="pending_approval",
                        tool_calls=all_tool_calls,
                        input_tokens=total_input,
                        output_tokens=total_output,
                        latency_ms=total_latency,
                    )

                    return {
                        "reply": confirm_response["reply"] or "Your request needs confirmation. Please approve or reject.",
                        "tool_calls": all_tool_calls,
                        "total_input_tokens": total_input,
                        "total_output_tokens": total_output,
                        "total_latency_ms": total_latency,
                        "total_cost": total_cost,
                        "pending_approval": True,
                    }

                continue

            # ── Final text reply ──────────────────────
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

        return {
            "reply": "I've reached the maximum number of steps. Please try rephrasing.",
            "tool_calls": all_tool_calls,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_latency_ms": total_latency,
            "total_cost": total_cost,
        }

    async def execute_approved_tool(
        self,
        tool_name: str,
        tool_arguments: dict,
        session_id: str,
        context: dict | None = None,
    ) -> dict:
        """
        Execute a previously approved tool call.
        Called by the coordinator after the user approves.
        """
        logger.info(f"[{self.name}] Executing approved tool: {tool_name}")

        result = await self.mcp_server.call_tool(tool_name, tool_arguments)

        await observability_repo.record_trace(
            session_id=session_id,
            agent=self.name,
            action=f"executed_approved:{tool_name}",
            tool_calls=[{
                "tool": tool_name,
                "input": tool_arguments,
                "success": result.success,
            }],
        )

        if result.success:
            # Ask LLM to format the result nicely
            system = self.system_prompt
            if context:
                system += f"\n\nContext:\n{json.dumps(context, indent=2, default=str)}"

            response = llm_client.invoke(
                messages=[{
                    "role": "user",
                    "content": (
                        f"The customer approved the action '{tool_name}' and it has been executed. "
                        f"Here is the result:\n{json.dumps(result.data, default=str)}\n\n"
                        f"Summarize what was done and provide the request ID and next steps."
                    ),
                }],
                system_prompt=system,
                session_id=session_id,
                model_override=self.model_id,
            )
            return {
                "reply": response["reply"],
                "success": True,
            }
        else:
            return {
                "reply": f"Sorry, the action failed: {result.error}",
                "success": False,
            }