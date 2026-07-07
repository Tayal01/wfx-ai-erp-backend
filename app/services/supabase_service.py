"""Supabase service placeholder."""

from app.config.settings import get_settings


def get_supabase_status() -> str:
    settings = get_settings()
    return "configured" if settings.supabase_configured else "not_configured"
