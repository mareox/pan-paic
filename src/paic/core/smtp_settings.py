"""SMTP configuration loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class SmtpConfig(BaseSettings):
    """SMTP runtime configuration for diff alert emails."""

    model_config = SettingsConfigDict(
        env_prefix="PAIC_SMTP_",
        case_sensitive=False,
        populate_by_name=True,
    )

    host: str = "localhost"
    port: int = 587
    username: str = ""
    password: str = ""
    from_addr: str = "paic@localhost"
    use_tls: bool = False
    base_link: str = ""
