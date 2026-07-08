from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.services.auth_service import get_current_user
from app.services.embedding_service import embed_image_bytes, embed_image_url, get_embedding_status
from app.services.typesense_service import (
    get_typesense_status,
    index_products,
    search_products,
    search_similar_products,
)


router = APIRouter()


class ProductSearchRequest(BaseModel):
    query: str = Field(default="", max_length=200)
    category: Optional[str] = None
    color: Optional[str] = None
    fabric: Optional[str] = None
    season: Optional[str] = None
    supplier: Optional[str] = None
    print_type: Optional[str] = Field(default=None, alias="print")
    buyer: Optional[str] = None
    gsm_min: Optional[str] = None
    gsm_max: Optional[str] = None
    limit: int = Field(default=12, ge=1, le=50)

    model_config = {"populate_by_name": True}


class ImageSearchRequest(BaseModel):
    image_url: Optional[str] = Field(default=None, max_length=500)
    limit: int = Field(default=12, ge=1, le=50)


class ReindexRequest(BaseModel):
    limit: int = Field(default=1500, ge=1, le=2000)
    include_embeddings: bool = True


@router.get("/status")
def search_status() -> dict[str, str]:
    typesense_status = get_typesense_status()
    embedding_status = get_embedding_status()
    detail = (
        "Typesense text and image search are configured."
        if typesense_status == "configured"
        else "Search will fall back to Supabase/Postgres when Typesense is unavailable."
    )
    return {
        "service": "search",
        "status": typesense_status if typesense_status == "configured" else "fallback",
        "embeddings": embedding_status,
        "detail": detail,
    }


@router.post("/products")
def product_search(
    payload: ProductSearchRequest,
    _current_user: dict = Depends(get_current_user),
) -> dict:
    try:
        return search_products(
            payload.query.strip(),
            category=payload.category,
            color=payload.color,
            fabric=payload.fabric,
            season=payload.season,
            supplier=payload.supplier,
            print_type=payload.print_type,
            buyer=payload.buyer,
            gsm_min=payload.gsm_min,
            gsm_max=payload.gsm_max,
            limit=payload.limit,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to search products: {exc}",
        ) from exc


@router.post("/image")
async def image_search(
    image: Optional[UploadFile] = File(default=None),
    image_url: Optional[str] = Form(default=None),
    limit: int = Form(default=12),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    try:
        if image is not None and image.filename:
            image_bytes = await image.read()
            if not image_bytes:
                raise ValueError("Uploaded image is empty.")
            embedding = embed_image_bytes(image_bytes)
        elif image_url:
            embedding = embed_image_url(image_url.strip())
        else:
            raise ValueError("Provide an uploaded image or image_url.")

        return search_similar_products(embedding, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to search by image: {exc}",
        ) from exc


@router.post("/image-url")
def image_search_json(
    payload: ImageSearchRequest,
    _current_user: dict = Depends(get_current_user),
) -> dict:
    if not payload.image_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="image_url is required.")

    try:
        embedding = embed_image_url(payload.image_url.strip())
        return search_similar_products(embedding, limit=payload.limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to search by image: {exc}",
        ) from exc


@router.post("/reindex")
def reindex_products(
    payload: ReindexRequest,
    _current_user: dict = Depends(get_current_user),
) -> dict:
    try:
        return index_products(limit=payload.limit, include_embeddings=payload.include_embeddings)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to rebuild product index: {exc}",
        ) from exc
