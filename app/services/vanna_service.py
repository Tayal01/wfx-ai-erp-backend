"""Vanna AI service placeholder."""

from app.config.settings import get_settings


def get_vanna_status() -> str:
    settings = get_settings()
    return "configured" if settings.openrouter_configured else "not_configured"
