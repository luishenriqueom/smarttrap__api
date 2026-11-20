from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://smarttrap:smarttrap@localhost:5433/smarttrap"
    jwt_secret: str = "dev-jwt-secret-change-me"
    access_token_expire_hours: int = 24
    admin_name: str = "SuperAdmin"
    admin_email: str = "admin@smarttrap.local"
    admin_password: str = "admin123"
    user_name: str = "Usuário comum"
    user_email: str = "usuario@smarttrap.local"
    user_password: str = "usuario123"
    demo_name: str = "Conta demonstração"
    demo_email: str = "demo@smarttrap.local"
    gateway_api_key: str = "dev-gateway-key"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    captures_dir: Path = Path("data/captures")
    firmware_dir: Path = Path("data/firmware")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
