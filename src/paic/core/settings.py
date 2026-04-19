"""Application settings loaded from environment variables.

PAIC v0.2 is stateless: no master key, no SMTP, no Prisma URL default
(callers pass an explicit ``prod`` selector or override).  The only DB use
remaining is profile persistence (settings only — no credentials).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """PAIC runtime configuration."""

    model_config = SettingsConfigDict(env_prefix="PAIC_", case_sensitive=False)

    database_url: str = "sqlite:///./paic.db"
    bind_host: str = "0.0.0.0"
    bind_port: int = 8080
    log_level: str = "INFO"
