"""Typesense service placeholder."""

from app.config.settings import get_settings


def get_typesense_status() -> str:
    settings = get_settings()
    return "configured" if settings.typesense_configured else "not_configured"
