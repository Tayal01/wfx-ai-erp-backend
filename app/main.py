from contextlib import asynccontextmanager
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import get_settings
from app.routes import ai, auth, dashboard, products, search
from app.services.embedding_service import get_embedding_status
from app.services.supabase_service import get_supabase_status
from app.services.typesense_service import get_typesense_status
from app.services.vanna_service import get_vanna_status

settings = get_settings()


def _warmup_models() -> None:
    """Load heavy models once at boot so the first user request is fast.

    Runs in a background thread so startup (and the platform health check) is not
    blocked by the ~600MB CLIP model load / first-time download.
    """
    try:
        from app.services.embedding_service import get_embedding_model

        get_embedding_model()  # CLIP for image search — the slow one to cold-load
    except Exception:  # noqa: BLE001 - warmup is best-effort; never crash boot
        pass
    try:
        from app.services.vanna_service import get_vanna

        get_vanna()  # trains the in-memory NL->SQL store (instant, no download)
    except Exception:  # noqa: BLE001
        pass


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.warmup_models_on_startup:
        threading.Thread(target=_warmup_models, name="model-warmup", daemon=True).start()
    yield


app = FastAPI(
    title=settings.app_name,
    description="AI-native ERP APIs for apparel business data.",
    version=settings.app_version,
    lifespan=lifespan,
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
app.include_router(auth.router, prefix=f"{settings.api_prefix}/auth", tags=["auth"])


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
        "auth": "configured" if settings.auth_configured else "not_configured",
    }

    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "integrations": integrations,
    }
