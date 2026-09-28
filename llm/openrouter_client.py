"""
OpenRouter LLM Client — works with 300+ models through one API.

Uses the OpenAI-compatible API, so we use the openai package.
Swap models by changing LLM_MODEL in .env.
"""
import time
import logging
from typing import Optional
from openai import OpenAI
from llm.base_client import BaseLLMClient
from config import llm_config

logger = logging.getLogger("llm.openrouter")

# Pricing per 1M tokens (approximate, varies by model)
# OpenRouter shows exact pricing on each model's page
MODEL_PRICING = {
    "meta-llama/llama-4-scout:free": {"input": 0, "output": 0},
    "qwen/qwen3-235b-a22b:free": {"input": 0, "output": 0},
    "google/gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "anthropic/claude-sonnet-4": {"input": 3.0, "output": 15.0},
    "openai/gpt-4o": {"input": 2.5, "output": 10.0},
}
DEFAULT_PRICING = {"input": 1.0, "output": 2.0}


class OpenRouterClient(BaseLLMClient):
    def __init__(self):
        print("Calling OpenRouterClient.__init__")
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=llm_config.api_key,
        )
        self.model_id = llm_config.model_id

    def invoke(
        self,
        messages: list[dict],
        system_prompt: str = "",
        tools: Optional[list[dict]] = None,
        session_id: str = "",
    ) -> dict:
        """Send a conversation to OpenRouter and return parsed response."""

        # Build messages list
        print("Calling OpenRouterClient.invoke")
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})

        # Convert messages to OpenAI format if needed
        for msg in messages:
            if "content" in msg and isinstance(msg["content"], list):
                # Bedrock format: [{"text": "..."}] → extract text
                text_parts = [
                    block["text"] for block in msg["content"]
                    if isinstance(block, dict) and "text" in block
                ]
                # Handle tool results
                tool_results = [
                    block for block in msg["content"]
                    if isinstance(block, dict) and "toolResult" in block
                ]

                if tool_results:
                    # Convert tool results to OpenAI format
                    for tr in tool_results:
                        tool_result = tr["toolResult"]
                        full_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_result["toolUseId"],
                            "content": tool_result["content"][0]["text"]
                            if tool_result.get("content") else "",
                        })
                elif text_parts:
                    full_messages.append({
                        "role": msg["role"],
                        "content": " ".join(text_parts),
                    })
            else:
                full_messages.append(msg)

        # Build API call kwargs
        kwargs = {
            "model": self.model_id,
            "messages": full_messages,
            "max_tokens": llm_config.max_tokens,
        }
        if tools:
            kwargs["tools"] = tools

        # Call OpenRouter
        start = time.time()
        response = self.client.chat.completions.create(**kwargs)
        latency_ms = (time.time() - start) * 1000

        # Extract usage
        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0

        # Estimate cost
        pricing = MODEL_PRICING.get(self.model_id, DEFAULT_PRICING)
        estimated_cost = (
            (input_tokens / 1_000_000) * pricing["input"]
            + (output_tokens / 1_000_000) * pricing["output"]
        )

        # Parse response
        choice = response.choices[0]
        message = choice.message

        reply_text = message.content
        tool_uses = None

        if message.tool_calls:
            import json
            tool_uses = []
            for tc in message.tool_calls:
                tool_uses.append({
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                    "id": tc.id,
                })

        stop_reason = "tool_calls" if message.tool_calls else "stop"

        logger.info(
            f"[LLM] model={self.model_id} session={session_id} "
            f"tokens={input_tokens}+{output_tokens} "
            f"cost=${estimated_cost:.6f} latency={latency_ms:.0f}ms"
        )

        return {
            "reply": reply_text,
            "tool_uses": tool_uses,
            "stop_reason": stop_reason,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost": round(estimated_cost, 6),
            "latency_ms": latency_ms,
            "model": self.model_id,
        }

def build_assistant_message(self, tool_uses):
    print("Calling build_assistant_message")
    return {
        "role": "assistant",
        "tool_calls": [
            {"id": tu["id"], "type": "function",
             "function": {"name": tu["name"], "arguments": json.dumps(tu["arguments"])}}
            for tu in tool_uses
        ],
    }

def build_tool_result_messages(self, tool_results):
    print("Calling build_tool_result_messages")
    return [
        {"role": "tool", "tool_call_id": tr["id"], "content": tr["result"]}
        for tr in tool_results
    ]