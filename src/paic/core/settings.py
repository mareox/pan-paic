"""Application settings loaded from environment variables.

PAIC v0.2.1 is fully stateless on the credentials side and uses YAML files for
profile persistence — no SQL engine.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """PAIC runtime configuration."""

    model_config = SettingsConfigDict(env_prefix="PAIC_", case_sensitive=False)

    profiles_dir: Path = Path("./profiles")
    bind_host: str = "0.0.0.0"
    bind_port: int = 8080
    log_level: str = "INFO"
