from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import get_settings
from app.routes import ai, dashboard, products, search
from app.services.embedding_service import get_embedding_status
from app.services.supabase_service import get_supabase_status
from app.services.typesense_service import get_typesense_status
from app.services.vanna_service import get_vanna_status

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="AI-native ERP APIs for apparel business data.",
    version=settings.app_version,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router, prefix=f"{settings.api_prefix}/dashboard", tags=["dashboard"])
app.include_router(products.router, prefix=f"{settings.api_prefix}/products", tags=["products"])
app.include_router(ai.router, prefix=f"{settings.api_prefix}/ai", tags=["ai"])
app.include_router(search.router, prefix=f"{settings.api_prefix}/search", tags=["search"])


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "status": "ready",
        "version": settings.app_version,
    }


@app.get("/health")
def health() -> dict[str, object]:
    integrations = {
        "supabase": get_supabase_status(),
        "vanna_openrouter": get_vanna_status(),
        "typesense": get_typesense_status(),
        "embeddings": get_embedding_status(),
    }

    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "integrations": integrations,
    }
