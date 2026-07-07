from fastapi import APIRouter


router = APIRouter()


@router.get("/status")
def search_status() -> dict[str, str]:
    return {
        "service": "search",
        "status": "scaffolded",
        "detail": "Typesense text and image search will be added later.",
    }
