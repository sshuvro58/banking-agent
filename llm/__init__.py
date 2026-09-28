"""
LLM Factory — creates the right client based on LLM_PROVIDER in .env.

Usage:
    from llm import llm_client

    response = llm_client.invoke(
        messages=[{"role": "user", "content": "Hello"}],
        system_prompt="You are helpful.",
        session_id="test",
    )

Change provider by editing .env:
    LLM_PROVIDER=openrouter  → OpenRouter (default)
    LLM_PROVIDER=bedrock     → AWS Bedrock
"""
from config import llm_config
from llm.base_client import BaseLLMClient


def create_llm_client() -> BaseLLMClient:
    """Factory: reads LLM_PROVIDER from config and returns the right client."""

    print("Calling create_llm_client")
    provider = llm_config.provider

    if provider == "openrouter":
        from llm.openrouter_client import OpenRouterClient
        return OpenRouterClient()

    elif provider == "bedrock":
        from llm.bedrock_client import BedrockClient
        return BedrockClient()

    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER: '{provider}'. "
            f"Supported: openrouter, bedrock"
        )


# Singleton — every module imports this
llm_client = create_llm_client()