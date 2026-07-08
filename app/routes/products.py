from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.services.auth_service import get_current_user
from app.services.supabase_service import get_product_detail, list_products


router = APIRouter()


@router.get("/status")
def products_status() -> dict[str, str]:
    return {
        "service": "products",
        "status": "ready",
        "detail": "Product APIs are available from Supabase.",
    }


@router.get("")
def products_index(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
    category: Optional[str] = None,
    color: Optional[str] = None,
    fabric: Optional[str] = None,
    season: Optional[str] = None,
    supplier: Optional[str] = None,
    sort_by: str = Query(default="style_number"),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$"),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    try:
        return list_products(
            page=page,
            page_size=page_size,
            category=category,
            color=color,
            fabric=fabric,
            season=season,
            supplier=supplier,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to load products: {exc}") from exc


@router.get("/{style_number}")
def products_show(style_number: str, _current_user: dict = Depends(get_current_user)) -> dict:
    try:
        product = get_product_detail(style_number)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to load product: {exc}") from exc

    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    return product
