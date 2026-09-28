"""
Central configuration — all settings in one place.
Add new config classes here as you build more phases.
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv
import json 

load_dotenv()


# ── Database ──────────────────────────────────────────

@dataclass(frozen=True)
class DatabaseConfig:
    user: str
    password: str
    host: str
    port: int
    name: str

    @property
    def dsn(self) -> str:
        print("Calling DatabaseConfig.dsn")
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


def load_db_config() -> DatabaseConfig:
    print("Calling load_db_config")
    required = ["DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    return DatabaseConfig(
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        name=os.environ["DB_NAME"],
    )


# ── LLM Provider ─────────────────────────────────────

@dataclass(frozen=True)
class LLMConfig:
    provider: str       # "openrouter" or "bedrock"
    model_id: str       # model string for the chosen provider
    api_key: str        # OpenRouter API key (empty for Bedrock)
    aws_region: str     # AWS region (only used by Bedrock)
    max_tokens: int     # cap on completion length (OpenRouter defaults to the model's full context otherwise)

    @property
    def display_name(self) -> str:
        print("Calling LLMConfig.display_name")
        return f"{self.provider}/{self.model_id}"


def load_llm_config() -> LLMConfig:
    print("Calling load_llm_config")
    provider = os.environ.get("LLM_PROVIDER", "openrouter")

    if provider == "openrouter" and not os.environ.get("OPENROUTER_API_KEY"):
        raise ValueError("OPENROUTER_API_KEY is required when LLM_PROVIDER=openrouter")

    return LLMConfig(
        provider=provider,
        model_id=os.environ.get("LLM_MODEL", "meta-llama/llama-4-scout:free"),
        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        aws_region=os.environ.get("AWS_REGION", "us-east-1"),
        max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "2666")),
    )


# ── Singletons (import these across the project) ─────

db_config = load_db_config()
llm_config = load_llm_config()