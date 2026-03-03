from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Ambiente: local | prod
    sumula_env: str = "local"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_max_tokens: int = 4096

    # Redis (por ambiente, mesmo prefixo SUMULA_*_LOCAL / SUMULA_*_PROD)
    sumula_redis_url_local: str = "redis://localhost:6379"
    sumula_redis_url_prod: str = ""
    sumula_upstash_redis_rest_url_local: str = ""
    sumula_upstash_redis_rest_url_prod: str = ""
    sumula_upstash_redis_rest_token_local: str = ""
    sumula_upstash_redis_rest_token_prod: str = ""

    @property
    def redis_url(self) -> str:
        """URL do Redis ativa conforme SUMULA_ENV."""
        if self.sumula_env == "prod":
            return self.sumula_redis_url_prod or "redis://localhost:6379"
        return self.sumula_redis_url_local

    @property
    def upstash_redis_rest_url(self) -> str:
        """URL REST Upstash ativa conforme SUMULA_ENV."""
        if self.sumula_env == "prod":
            return self.sumula_upstash_redis_rest_url_prod
        return self.sumula_upstash_redis_rest_url_local

    @property
    def upstash_redis_rest_token(self) -> str:
        """Token REST Upstash ativo conforme SUMULA_ENV."""
        if self.sumula_env == "prod":
            return self.sumula_upstash_redis_rest_token_prod
        return self.sumula_upstash_redis_rest_token_local

    # Postgres
    database_url: str = "postgresql+asyncpg://sumula:sumula@localhost:5432/sumula"

    # Upload limits
    max_upload_mb: int = 20
    max_files: int = 10

    # Working directory
    workdir_path: str = "/tmp/sumula_workdir"

    # Web of Science Starter API (optional — public scraper used if absent)
    wos_api_key: str = ""

    # Email (MailerSend SMTP)
    smtp_host: str = "smtp.mailersend.net"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    mail_default_sender: str = ""
    mail_default_sender_name: str = "Súmula FAPESP"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


settings = Settings()
