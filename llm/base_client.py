"""
Base LLM Client — the interface all providers must implement.

Every provider (OpenRouter, Bedrock, Ollama, etc.) implements this
same interface, so the agents don't care which provider is running.
"""
from abc import ABC, abstractmethod
from typing import Optional


class BaseLLMClient(ABC):

    @abstractmethod
    def invoke(
        self,
        messages: list[dict],
        system_prompt: str = "",
        tools: Optional[list[dict]] = None,
        session_id: str = "",
    ) -> dict:
        """
        Send a conversation to the LLM.

        Returns dict with:
            reply, tool_uses, stop_reason, input_tokens,
            output_tokens, estimated_cost, latency_ms, model
        """
        print("Calling BaseLLMClient.invoke")
        pass

    @abstractmethod
    def build_assistant_message(self, tool_uses: list[dict]) -> dict:
        """
        Build the assistant message that contains tool calls.

        After the LLM returns tool_uses, we need to add the assistant's
        message (with tool calls) back into the conversation before
        sending tool results. Each provider formats this differently.

        Parameters
        ----------
        tool_uses : list[dict]
            From invoke() response: [{"name": str, "arguments": dict, "id": str}]

        Returns
        -------
        dict — a message in the provider's format
        """
        print("Calling BaseLLMClient.build_assistant_message")
        pass

    @abstractmethod
    def build_tool_result_messages(self, tool_results: list[dict]) -> list[dict]:
        """
        Build messages containing tool execution results.

        After executing tools, we send results back to the LLM.
        Each provider formats this differently:
          - OpenAI/OpenRouter: one message per tool with role="tool"
          - Bedrock: one message with role="user" containing toolResult blocks

        Parameters
        ----------
        tool_results : list[dict]
            [{"id": str, "name": str, "result": str (JSON), "is_error": bool}]

        Returns
        -------
        list[dict] — messages in the provider's format
        """
        print("Calling BaseLLMClient.build_tool_result_messages")
        pass

    @staticmethod
    def build_tool_spec(name: str, description: str, parameters: dict) -> dict:
        """Build a tool definition in OpenAI function-calling format."""
        print("Calling BaseLLMClient.build_tool_spec")
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": parameters.get("properties", {}),
                    "required": parameters.get("required", []),
                },
            },
        }

    @abstractmethod
    def invoke(
        self,
        messages: list[dict],
        system_prompt: str = "",
        tools: Optional[list[dict]] = None,
        session_id: str = "",
    ) -> dict:
        """
        Send a conversation to the LLM.

        Returns dict with:
            reply, tool_uses, stop_reason, input_tokens,
            output_tokens, estimated_cost, latency_ms, model
        """
        print("Calling BaseLLMClient.invoke")
        pass

    @abstractmethod
    def build_assistant_message(self, tool_uses: list[dict]) -> dict:
        """
        Build the assistant message that contains tool calls.

        After the LLM returns tool_uses, we need to add the assistant's
        message (with tool calls) back into the conversation before
        sending tool results. Each provider formats this differently.

        Parameters
        ----------
        tool_uses : list[dict]
            From invoke() response: [{"name": str, "arguments": dict, "id": str}]

        Returns
        -------
        dict — a message in the provider's format
        """
        print("Calling BaseLLMClient.build_assistant_message")
        pass

    @abstractmethod
    def build_tool_result_messages(self, tool_results: list[dict]) -> list[dict]:
        """
        Build messages containing tool execution results.

        After executing tools, we send results back to the LLM.
        Each provider formats this differently:
          - OpenAI/OpenRouter: one message per tool with role="tool"
          - Bedrock: one message with role="user" containing toolResult blocks

        Parameters
        ----------
        tool_results : list[dict]
            [{"id": str, "name": str, "result": str (JSON), "is_error": bool}]

        Returns
        -------
        list[dict] — messages in the provider's format
        """
        print("Calling BaseLLMClient.build_tool_result_messages")
        pass

    @staticmethod
    def build_tool_spec(name: str, description: str, parameters: dict) -> dict:
        """Build a tool definition in OpenAI function-calling format."""
        print("Calling BaseLLMClient.build_tool_spec")
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": parameters.get("properties", {}),
                    "required": parameters.get("required", []),
                },
            },
        }