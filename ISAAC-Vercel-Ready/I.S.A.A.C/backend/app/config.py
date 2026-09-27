"""Application settings loaded from environment variables."""

from functools import lru_cache
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ISAAC API"
    app_env: str = "development"
    api_prefix: str = "/api"
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = ""
    mysql_password: str = ""
    mysql_database: str = "isaac"
    mysql_connect_timeout: int = 2

    # Apache Kafka Industrial Event Streaming (Phase 16)
    kafka_enabled: bool = False
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_telemetry: str = "industrial-sensor-telemetry"
    kafka_topic_predictions: str = "industrial-predictions-telemetry"
    kafka_consumer_group: str = "isaac-prediction-group"
    kafka_auto_offset_reset: str = "latest"
    kafka_client_id: str = "isaac-stream-worker"
    kafka_timeout_ms: int = 2000
    kafka_max_retries: int = 3
    kafka_retry_backoff_ms: int = 500

    # Security & Authentication (Phase 17)
    secret_key: str = "isaac-industrial-secret-key-change-in-production"
    auth_token_expire_minutes: int = 480
    auth_required: bool = False
    cors_allowed_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"
    cors_allow_credentials: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def mysql_url(self) -> str:
        """Return the configured database URL.

        Local development uses the project SQLite database. Vercel uses /tmp so
        the serverless filesystem remains writable; an external MySQL database
        can be supplied by setting MYSQL_* variables.
        """
        if not self.mysql_user or self.mysql_user.strip() == "":
            sqlite_path = os.getenv("SQLITE_DB_PATH")
            if not sqlite_path:
                sqlite_path = "/tmp/isaac.db" if os.getenv("VERCEL") else "./isaac.db"
            return f"sqlite:///{sqlite_path}"
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
        )

    @property
    def cors_origins_list(self) -> list[str]:
        """Return list of allowed CORS origins."""
        if not self.cors_allowed_origins or self.cors_allowed_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
