from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "WFX AI ERP Assistant API"
    app_version: str = "0.1.0"
    environment: str = "development"
    api_prefix: str = "/api"

    frontend_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )

    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_anon_key: str = ""

    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"

    typesense_host: str = "localhost"
    typesense_port: int = 8108
    typesense_protocol: str = "http"
    typesense_api_key: str = ""
    typesense_products_collection: str = "wfx_products"

    embedding_model_name: str = "openai/clip-vit-base-patch32"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return self.frontend_origins

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

    @property
    def openrouter_configured(self) -> bool:
        return bool(self.openrouter_api_key)

    @property
    def typesense_configured(self) -> bool:
        return bool(self.typesense_host and self.typesense_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
