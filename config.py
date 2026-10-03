"""
Central configuration — all settings in one place.
Add new config classes here as you build more phases.
"""
import os
import logging
from dataclasses import dataclass
from dotenv import load_dotenv
import json

load_dotenv()

logger = logging.getLogger("config")


# ── App environment ───────────────────────────────────

@dataclass(frozen=True)
class AppConfig:
    environment: str  # "development" or "production"

    @property
    def is_dev(self) -> bool:
        return self.environment == "development"


def load_app_config() -> AppConfig:
    return AppConfig(
        environment=os.environ.get("APP_ENV", "development"),
    )


# config.py
@dataclass(frozen=True)
class GuardrailConfig:
    enabled: bool
    guardrail_id: str
    guardrail_version: str


def load_guardrail_config() -> GuardrailConfig:
    return GuardrailConfig(
        enabled=os.environ.get("GUARDRAIL_ENABLED", "false").lower() == "true",
        guardrail_id=os.environ.get("GUARDRAIL_ID", ""),
        guardrail_version=os.environ.get("GUARDRAIL_VERSION", ""),
    )


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
        logger.debug("Calling DatabaseConfig.dsn")
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


def load_db_config() -> DatabaseConfig:
    logger.debug("Calling load_db_config")
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
        logger.debug("Calling LLMConfig.display_name")
        return f"{self.provider}/{self.model_id}"


def load_llm_config() -> LLMConfig:
    logger.debug("Calling load_llm_config")
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


@dataclass(frozen=True)
class JWTConfig:
    secret_key: str
    algorithm: str
    expiry_minutes: int

def load_jwt_config() -> JWTConfig:
    return JWTConfig(
        secret_key=os.environ.get("JWT_SECRET_KEY", "dev-secret-change-in-prod"),
        algorithm=os.environ.get("JWT_ALGORITHM", "HS256"),
        expiry_minutes=int(os.environ.get("JWT_EXPIRY_MINUTES", "30")),
    )



"""
Human-in-the-Loop Configuration.
 
Defines which tool calls require approval before execution,
and who can approve them.
 
Add to your config.py or keep as a separate file.
"""
 
# Tools that require approval before execution.
# Key = tool name (from MCP server)
# Value = who approves ("customer" or "employee")
TOOLS_REQUIRING_APPROVAL = {
    "change_address": "customer",        # customer confirms in chat
    "request_chequebook": "customer",    # customer confirms in chat
    "update_kyc": "employee",            # bank employee approves via dashboard
}
 

# ── Singletons (import these across the project) ─────

app_config = load_app_config()
db_config = load_db_config()
llm_config = load_llm_config()
jwt_config = load_jwt_config()
guardrail_config = load_guardrail_config()
