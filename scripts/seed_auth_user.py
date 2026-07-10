from __future__ import annotations

"""Create (or update) the seeded demo user in Supabase Auth.

Run once after configuring SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env:

    python scripts/seed_auth_user.py

The credentials come from DEMO_USER_* in .env. Document them in the README so an
evaluator can sign in; the app itself never exposes them.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT_DIR))

from supabase import create_client

from app.config.settings import get_settings


def main() -> None:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise SystemExit("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env first.")

    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    email = settings.demo_user_email
    metadata = {"name": settings.demo_user_name, "role": settings.demo_user_role}

    try:
        client.auth.admin.create_user(
            {
                "email": email,
                "password": settings.demo_user_password,
                "email_confirm": True,
                "user_metadata": metadata,
            }
        )
        print(f"Created demo user: {email}")
        return
    except Exception as exc:  # noqa: BLE001
        message = str(exc).lower()
        if "already" not in message and "registered" not in message and "exists" not in message:
            raise

    # Already exists -> reset the password and refresh metadata so the seed is idempotent.
    listed = client.auth.admin.list_users()
    users = listed if isinstance(listed, list) else getattr(listed, "users", [])
    match = next((u for u in users if getattr(u, "email", None) == email), None)
    if match is None:
        print(f"Demo user {email} exists but could not be located to update.")
        return

    client.auth.admin.update_user_by_id(
        match.id,
        {"password": settings.demo_user_password, "user_metadata": metadata, "email_confirm": True},
    )
    print(f"Updated existing demo user: {email}")


if __name__ == "__main__":
    main()
