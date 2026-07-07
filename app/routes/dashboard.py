from fastapi import APIRouter, HTTPException

from app.services.supabase_service import get_dashboard_summary


router = APIRouter()


@router.get("/status")
def dashboard_status() -> dict[str, str]:
    return {
        "service": "dashboard",
        "status": "ready",
        "detail": "ERP dashboard metrics are available from Supabase.",
    }


@router.get("/summary")
def dashboard_summary() -> dict:
    try:
        return get_dashboard_summary()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to load dashboard summary: {exc}") from exc
