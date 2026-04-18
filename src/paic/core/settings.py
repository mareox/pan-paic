"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """PAIC runtime configuration."""

    model_config = SettingsConfigDict(env_prefix="PAIC_", case_sensitive=False)

    master_key: str
    database_url: str = "sqlite:///./paic.db"
    bind_host: str = "0.0.0.0"
    bind_port: int = 8080
    log_level: str = "INFO"
    prisma_base_url: str = "https://api.prod.datapath.prismaaccess.com"
