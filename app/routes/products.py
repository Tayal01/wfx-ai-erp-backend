from fastapi import APIRouter


router = APIRouter()


@router.get("/status")
def products_status() -> dict[str, str]:
    return {
        "service": "products",
        "status": "scaffolded",
        "detail": "Product APIs will be added after Supabase services.",
    }
