from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "WFX AI ERP Assistant API"
    app_version: str = "0.1.0"
    environment: str = "development"
    api_prefix: str = "/api"

    demo_user_email: str = "merchandiser@wfx.com"
    demo_user_password: str = "demo1234"
    demo_user_name: str = "WFX Merchandiser"
    demo_user_role: str = "Merchandiser"

    frontend_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5174",
            "http://127.0.0.1:5174",
        ]
    )

    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_anon_key: str = ""
    database_url: str = ""

    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"

    typesense_host: str = "localhost"
    typesense_port: int = 8108
    typesense_protocol: str = "http"
    typesense_api_key: str = ""
    typesense_products_collection: str = "wfx_products"

    embedding_model_name: str = "clip-ViT-B-32"

    # Preload CLIP + the NL->SQL store at boot so the first image/AI request is fast.
    # Set false to trade a slow first request for lower idle memory.
    warmup_models_on_startup: bool = True

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

    @property
    def auth_configured(self) -> bool:
        # Auth is handled by Supabase; verifying tokens needs a configured Supabase client.
        return self.supabase_configured

    @property
    def database_configured(self) -> bool:
        return bool(self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
