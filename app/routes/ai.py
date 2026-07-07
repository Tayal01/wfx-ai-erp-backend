from fastapi import APIRouter


router = APIRouter()


@router.get("/status")
def ai_status() -> dict[str, str]:
    return {
        "service": "ai",
        "status": "scaffolded",
        "detail": "Vanna and OpenRouter integration will be added later.",
    }
