"""Image embedding service placeholder."""

from app.config.settings import get_settings


def get_embedding_status() -> str:
    settings = get_settings()
    return "configured" if settings.embedding_model_name else "not_configured"
