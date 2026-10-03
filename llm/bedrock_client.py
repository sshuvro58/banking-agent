"""
AWS Bedrock LLM Client — wraps the Converse API.

Enable later by setting LLM_PROVIDER=bedrock in .env.
"""
import time
import json
import logging
from typing import Optional
import boto3
from llm.base_client import BaseLLMClient
from config import llm_config
from config import guardrail_config
logger = logging.getLogger("llm.bedrock")



MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]

MODEL_PRICING = {
    "anthropic.claude-3-sonnet-20240229-v1:0": {"input": 3.0, "output": 15.0},
    "anthropic.claude-3-haiku-20240307-v1:0": {"input": 0.25, "output": 1.25},
}
DEFAULT_PRICING = {"input": 3.0, "output": 15.0}


class BedrockClient(BaseLLMClient):
    def __init__(self):
        logger.debug("Calling BedrockClient.__init__")
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=llm_config.aws_region,
        )
        self.model_id = llm_config.model_id
 
    def invoke_with_retry(self, **kwargs):
        """Wrapper around invoke() with exponential backoff."""
        for attempt in range(MAX_RETRIES):
            try:
                return self.invoke(**kwargs)
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    raise
                logger.warning(f"[LLM] Retry {attempt+1}/{MAX_RETRIES}: {e}")
                _time.sleep(RETRY_DELAYS[attempt])


    def invoke(
        self,
        messages: list[dict],
        system_prompt: str = "",
        tools: Optional[list[dict]] = None,
        session_id: str = "",
        model_override: str | None = None
    ) -> dict:
        logger.debug("Calling BedrockClient.invoke")
        bedrock_messages = self._to_bedrock_messages(messages)
        model = model_override or self.model_id

        kwargs = {"modelId": model, "messages": bedrock_messages}
        if system_prompt:
            kwargs["system"] = [{"text": system_prompt}]
        if tools:
            bedrock_tools = self._to_bedrock_tools(tools)
            kwargs["toolConfig"] = {"tools": bedrock_tools}

        # ── Guardrail ─────────────────────────────
        if guardrail_config.enabled and guardrail_config.guardrail_id:
            kwargs["guardrailConfig"] = {
                "guardrailIdentifier": guardrail_config.guardrail_id,
                "guardrailVersion": guardrail_config.guardrail_version,  # ← was missing
            }

        start = time.time()
        response = self.client.converse(**kwargs)
        latency_ms = (time.time() - start) * 1000

        usage = response.get("usage", {})
        input_tokens = usage.get("inputTokens", 0)
        output_tokens = usage.get("outputTokens", 0)

        pricing = MODEL_PRICING.get(model, DEFAULT_PRICING)
        estimated_cost = (
            (input_tokens / 1_000_000) * pricing["input"]
            + (output_tokens / 1_000_000) * pricing["output"]
        )

        stop_reason = response.get("stopReason", "")

        # ── Guardrail blocked ─────────────────────
        if stop_reason == "guardrail":
            logger.warning(f"[LLM] Guardrail triggered: session={session_id}")
            message = response.get("output", {}).get("message", {})
            blocked_text = ""
            for block in message.get("content", []):
                if "text" in block:
                    blocked_text = block["text"]
            return {
                "reply": blocked_text or "I'm unable to help with that request.",
                "tool_uses": None,
                "stop_reason": "guardrail",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "estimated_cost": round(estimated_cost, 6),
                "latency_ms": latency_ms,
                "model": model,
            }

        # ── Normal response ───────────────────────
        message = response.get("output", {}).get("message", {})
        reply_text = None
        tool_uses = []

        for block in message.get("content", []):
            if "text" in block:
                reply_text = block["text"]
            elif "toolUse" in block:
                tool_uses.append({
                    "name": block["toolUse"]["name"],
                    "arguments": block["toolUse"]["input"],
                    "id": block["toolUse"]["toolUseId"],
                })

        final_stop = "tool_calls" if tool_uses else "stop"

        logger.info(
            f"[LLM] model={model} session={session_id} "
            f"tokens={input_tokens}+{output_tokens} cost=${estimated_cost:.6f} "
            f"latency={latency_ms:.0f}ms stop={final_stop}"
        )

        return {
            "reply": reply_text,
            "tool_uses": tool_uses if tool_uses else None,
            "stop_reason": final_stop,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost": round(estimated_cost, 6),
            "latency_ms": latency_ms,
            "model": model,
        }
    
    def build_assistant_message(self, tool_uses: list[dict]) -> dict:
        """
        Bedrock format: assistant message with toolUse content blocks.
 
        Input:  [{"name": "balance_enquiry", "arguments": {"account_id": "acc_1001"}, "id": "tooluse_abc"}]
        Output: {"role": "assistant", "content": [{"toolUse": {"toolUseId": "...", "name": "...", "input": {...}}}]}
        """
        logger.debug("Calling BedrockClient.build_assistant_message")
        content = []
        for tu in tool_uses:
            content.append({
                "toolUse": {
                    "toolUseId": tu["id"],
                    "name": tu["name"],
                    "input": tu["arguments"],
                }
            })
        return {"role": "assistant", "content": content}
 
    def build_tool_result_messages(self, tool_results: list[dict]) -> list[dict]:
        """
        Bedrock format: ONE user message with all toolResult blocks.
 
        Input:  [{"id": "tooluse_abc", "name": "balance_enquiry", "result": "{...}", "is_error": False}]
        Output: [{"role": "user", "content": [{"toolResult": {"toolUseId": "...", "content": [{"text": "..."}], "status": "success"}}]}]
        """
        logger.debug("Calling BedrockClient.build_tool_result_messages")
        content = []
        for tr in tool_results:
            content.append({
                "toolResult": {
                    "toolUseId": tr["id"],
                    "content": [{"text": tr["result"]}],
                    "status": "error" if tr["is_error"] else "success",
                }
            })
        return [{"role": "user", "content": content}]
 
    # ── Internal format converters ────────────────────
 
    def _to_bedrock_messages(self, messages: list[dict]) -> list[dict]:
        """Convert provider-agnostic messages to Bedrock Converse format."""
        logger.debug("Calling BedrockClient._to_bedrock_messages")
        bedrock_msgs = []
        for msg in messages:
            content = msg.get("content")
            role = msg.get("role")
 
            if isinstance(content, str):
                # Simple text message
                bedrock_msgs.append({
                    "role": role,
                    "content": [{"text": content}],
                })
            elif isinstance(content, list):
                # Already in Bedrock format (toolUse / toolResult blocks)
                bedrock_msgs.append(msg)
            else:
                bedrock_msgs.append(msg)
 
        return bedrock_msgs
 
    def _to_bedrock_tools(self, tools: list[dict]) -> list[dict]:
        """Convert OpenAI function-calling format to Bedrock toolSpec format."""
        logger.debug("Calling BedrockClient._to_bedrock_tools")
        bedrock_tools = []
        for tool in tools:
            func = tool["function"]
            bedrock_tools.append({
                "toolSpec": {
                    "name": func["name"],
                    "description": func["description"],
                    "inputSchema": {"json": func["parameters"]},
                }
            })
        return bedrock_tools
 