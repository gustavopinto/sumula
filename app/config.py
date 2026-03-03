from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_max_tokens: int = 4096

    # Redis
    redis_url: str = "redis://localhost:6379"

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
