"""
AWS Bedrock client — wraps the Converse API.
Handles tool-use, token counting, and cost estimation.

Usage:
    from llm.bedrock_client import bedrock_llm

    response = bedrock_llm.invoke(
        messages=[{"role": "user", "content": [{"text": "Hello"}]}],
        system_prompt="You are helpful.",
        session_id="test",
    )
    print(response["reply"])
"""
import time
import boto3
import logging
from typing import Optional
from config import bedrock_config

logger = logging.getLogger("bedrock")

# Pricing per 1K tokens (approximate, varies by model)
MODEL_PRICING = {
    "anthropic.claude-3-sonnet-20240229-v1:0": {"input": 0.003, "output": 0.015},
    "anthropic.claude-3-haiku-20240307-v1:0": {"input": 0.00025, "output": 0.00125},
    "anthropic.claude-3-5-sonnet-20240620-v1:0": {"input": 0.003, "output": 0.015},
}
DEFAULT_PRICING = {"input": 0.003, "output": 0.015}


class BedrockLLM:
    def __init__(self):
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=bedrock_config.region,
        )
        self.model_id = bedrock_config.model_id

    def invoke(
        self,
        messages: list[dict],
        system_prompt: str = "",
        tools: Optional[list[dict]] = None,
        session_id: str = "",
    ) -> dict:
        """
        Send a conversation to Bedrock and return the parsed response.

        Parameters
        ----------
        messages : list[dict]
            Conversation in Bedrock Converse format:
            [{"role": "user", "content": [{"text": "..."}]}]
        system_prompt : str
            System-level instruction for the model.
        tools : list[dict] | None
            Tool definitions in Bedrock toolConfig format.
        session_id : str
            For logging — not sent to Bedrock.

        Returns
        -------
        dict with keys:
            reply          — text response (None if tool_use)
            tool_uses      — list of tool_use blocks (None if text)
            stop_reason    — "end_turn" or "tool_use"
            input_tokens   — from response.usage
            output_tokens  — from response.usage
            estimated_cost — dollar estimate
            latency_ms     — round-trip time
            raw_message    — full message content (needed for tool loop)
        """
        # Build the request
        kwargs = {
            "modelId": self.model_id,
            "messages": messages,
        }
        if system_prompt:
            kwargs["system"] = [{"text": system_prompt}]
        if tools:
            kwargs["toolConfig"] = {"tools": tools}

        # Call Bedrock
        start = time.time()
        response = self.client.converse(**kwargs)
        latency_ms = (time.time() - start) * 1000

        # Extract token usage
        usage = response.get("usage", {})
        input_tokens = usage.get("inputTokens", 0)
        output_tokens = usage.get("outputTokens", 0)

        # Estimate cost
        pricing = MODEL_PRICING.get(self.model_id, DEFAULT_PRICING)
        estimated_cost = (
            (input_tokens / 1000) * pricing["input"]
            + (output_tokens / 1000) * pricing["output"]
        )

        # Parse the response message
        message = response.get("output", {}).get("message", {})
        stop_reason = response.get("stopReason", "")

        reply_text = None
        tool_uses = []

        for block in message.get("content", []):
            if "text" in block:
                reply_text = block["text"]
            elif "toolUse" in block:
                tool_uses.append(block["toolUse"])

        logger.info(
            f"[LLM] session={session_id} tokens={input_tokens}+{output_tokens} "
            f"cost=${estimated_cost:.6f} latency={latency_ms:.0f}ms "
            f"stop={stop_reason}"
        )

        return {
            "reply": reply_text,
            "tool_uses": tool_uses if tool_uses else None,
            "stop_reason": stop_reason,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost": round(estimated_cost, 6),
            "latency_ms": latency_ms,
            "raw_message": message,
        }

    @staticmethod
    def build_tool_spec(name: str, description: str, parameters: dict) -> dict:
        """
        Convert a simple tool definition into Bedrock's toolSpec format.

        Example input:
            name = "balance_enquiry"
            description = "Get account balance"
            parameters = {
                "properties": {
                    "account_id": {"type": "string", "description": "The account ID"}
                },
                "required": ["account_id"]
            }

        Example output:
            {"toolSpec": {"name": "...", "description": "...", "inputSchema": {"json": {...}}}}
        """
        return {
            "toolSpec": {
                "name": name,
                "description": description,
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": parameters.get("properties", {}),
                        "required": parameters.get("required", []),
                    }
                },
            }
        }


# Singleton
bedrock_llm = BedrockLLM()