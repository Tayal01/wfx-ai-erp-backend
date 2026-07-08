from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from typing import Any, Optional

import httpx
from PIL import Image
from sentence_transformers import SentenceTransformer

from app.config.settings import get_settings

EMBEDDING_DIMENSION = 512


def get_embedding_status() -> str:
    settings = get_settings()
    return "configured" if settings.embedding_model_name else "not_configured"


@lru_cache
def get_embedding_model() -> SentenceTransformer:
    settings = get_settings()
    return SentenceTransformer(settings.embedding_model_name)


def _normalize_vector(values: list[float]) -> list[float]:
    return [float(value) for value in values]


def embed_text(text: str) -> list[float]:
    model = get_embedding_model()
    vector = model.encode(text or "", normalize_embeddings=True)
    return _normalize_vector(vector.tolist())


def embed_image_bytes(image_bytes: bytes) -> list[float]:
    model = get_embedding_model()
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    vector = model.encode(image, normalize_embeddings=True)
    return _normalize_vector(vector.tolist())


def embed_image_url(image_url: str) -> list[float]:
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(image_url)
        response.raise_for_status()
        return embed_image_bytes(response.content)


def build_product_embedding_text(product: dict[str, Any]) -> str:
    parts = [
        product.get("style_name"),
        product.get("category"),
        product.get("fabric"),
        product.get("color"),
        product.get("print"),
        product.get("season"),
        product.get("brand"),
        product.get("supplier"),
        product.get("fabric_details"),
        product.get("construction"),
    ]
    return " ".join(str(part) for part in parts if part)


def get_product_embedding(product: dict[str, Any], image_bytes: Optional[bytes] = None) -> list[float]:
    if image_bytes:
        return embed_image_bytes(image_bytes)

    image_url = product.get("image_url")
    if image_url:
        try:
            return embed_image_url(str(image_url))
        except Exception:
            pass

    return embed_text(build_product_embedding_text(product))
