import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class DatabaseConfig:
    user: str
    password: str
    host: str
    port: int
    name: str

    @property
    def dsn(self) -> str:
        """Constructs a PostgreSQL DSN for asyncpg."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


def load_config() -> DatabaseConfig:
    required_vars = ["DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME"]
    missing = [var for var in required_vars if not os.getenv(var)]

    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    return DatabaseConfig(
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        name=os.environ["DB_NAME"],
    )


# Singleton instance for import across modules
db_config = load_config()


@dataclass(frozen=True)
class BedrockConfig:
    region: str
    model_id: str

bedrock_config = BedrockConfig(
    region=os.environ.get("AWS_REGION", "us-east-1"),
    model_id=os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0"),
)