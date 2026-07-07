from fastapi import APIRouter


router = APIRouter()


@router.get("/status")
def dashboard_status() -> dict[str, str]:
    return {
        "service": "dashboard",
        "status": "scaffolded",
        "detail": "ERP dashboard metrics will be added after Supabase services.",
    }
