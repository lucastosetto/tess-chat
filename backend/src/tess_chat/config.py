from functools import lru_cache
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_SSL_PARAMS = {"sslmode", "channel_binding"}


def normalize_database_url(url: str) -> tuple[str, bool]:
    parts = urlsplit(url)
    scheme = "postgresql+asyncpg" if parts.scheme in {"postgres", "postgresql"} else parts.scheme
    query = dict(parse_qsl(parts.query))
    ssl = query.get("sslmode", "disable") not in {"disable", "allow", "prefer"}
    kept = {k: v for k, v in query.items() if k not in _SSL_PARAMS}
    return urlunsplit((scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment)), ssl


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    port: int = 8000
    log_level: str = "INFO"
    log_json: bool = True

    database_url: str = "postgresql://tess:tess@localhost:5433/tess"
    database_ssl: bool = False

    session_secret: SecretStr = SecretStr("dev-insecure-session-secret-change-me")
    secrets_key: SecretStr | None = None
    session_ttl_seconds: int = 60 * 60 * 24 * 7
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: SecretStr | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    email_from: str | None = None
    admin_emails: list[str] = Field(default_factory=list)

    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.5-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    groq_api_key: SecretStr | None = None
    groq_model: str = "openai/gpt-oss-120b"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    llm_timeout_seconds: float = 120.0
    llm_read_timeout_seconds: float = 20.0
    max_output_tokens: int = 4096

    default_credit_grant: int = 2_000_000
    global_credit_cap: int = 50_000_000
    tavily_api_key: str = ""
    gcp_project_id: str = ""
    trace_exporter: Literal["none", "console", "gcp"] = "none"
    storage_backend: Literal["local", "gcs"] = "local"
    gcs_bucket: str = ""
    local_storage_dir: str = ".data/attachments"
    compaction_threshold_tokens: int = 24_000
    compaction_keep_recent: int = 6

    rate_limit_chat_per_minute: int = 20
    rate_limit_upload_per_minute: int = 30
    rate_limit_write_per_minute: int = 60
    rate_limit_public_per_minute: int = 120

    static_dir: str | None = None
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @property
    def async_database_url(self) -> str:
        return normalize_database_url(self.database_url)[0]

    @property
    def database_requires_ssl(self) -> bool:
        return self.database_ssl or normalize_database_url(self.database_url)[1]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
