from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional
import json

import httpx
import typesense
from sqlalchemy import text

from app.config.settings import get_settings
from app.services.embedding_service import EMBEDDING_DIMENSION, get_product_embedding
from app.services.supabase_service import execute_query, list_records_selected
from app.services.vanna_service import get_sql_engine


PRODUCT_FIELDS = (
    "style_number",
    "style_name",
    "category",
    "fabric",
    "gsm",
    "color",
    "print",
    "season",
    "brand",
    "supplier",
    "cost",
    "selling_price",
    "image_url",
    "fabric_details",
    "construction",
    "search_text",
    "embedding",
)


def get_typesense_status() -> str:
    settings = get_settings()
    return "configured" if settings.typesense_configured else "not_configured"


@lru_cache
def get_typesense_client() -> typesense.Client:
    settings = get_settings()
    if not settings.typesense_configured:
        raise RuntimeError("Typesense is not configured. Set TYPESENSE_HOST and TYPESENSE_API_KEY.")

    return typesense.Client(
        {
            "nodes": [
                {
                    "host": settings.typesense_host,
                    "port": settings.typesense_port,
                    "protocol": settings.typesense_protocol,
                }
            ],
            "api_key": settings.typesense_api_key,
            "connection_timeout_seconds": 10,
        }
    )


def _collection_schema(collection_name: str) -> dict[str, Any]:
    return {
        "name": collection_name,
        "fields": [
            {"name": "style_number", "type": "string"},
            {"name": "style_name", "type": "string"},
            {"name": "category", "type": "string", "facet": True},
            {"name": "fabric", "type": "string", "facet": True},
            {"name": "gsm", "type": "int32", "facet": True},
            {"name": "color", "type": "string", "facet": True},
            {"name": "print", "type": "string", "facet": True},
            {"name": "season", "type": "string", "facet": True},
            {"name": "brand", "type": "string", "facet": True},
            {"name": "supplier", "type": "string", "facet": True},
            {"name": "buyers", "type": "string[]", "facet": True, "optional": True},
            {"name": "cost", "type": "float"},
            {"name": "selling_price", "type": "float"},
            {"name": "image_url", "type": "string", "optional": True},
            {"name": "fabric_details", "type": "string", "optional": True},
            {"name": "construction", "type": "string", "optional": True},
            {"name": "search_text", "type": "string"},
            {
                "name": "embedding",
                "type": "float[]",
                "num_dim": EMBEDDING_DIMENSION,
                "optional": True,
            },
        ],
        "default_sorting_field": "gsm",
    }


def ensure_collection() -> None:
    settings = get_settings()
    client = get_typesense_client()
    collection_name = settings.typesense_products_collection

    try:
        client.collections[collection_name].retrieve()
    except typesense.exceptions.ObjectNotFound:
        client.collections.create(_collection_schema(collection_name))


def _get_collection_field_names() -> set[str]:
    settings = get_settings()
    client = get_typesense_client()
    schema = client.collections[settings.typesense_products_collection].retrieve()
    return {field["name"] for field in schema.get("fields", [])}


def _build_search_text(product: dict[str, Any]) -> str:
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


def _fetch_image_bytes(image_url: Optional[str]) -> Optional[bytes]:
    if not image_url:
        return None

    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(image_url)
            response.raise_for_status()
            return response.content
    except Exception:
        return None


def _load_product_catalog(limit: int = 1500) -> list[dict[str, Any]]:
    products = list_records_selected(
        "finished_goods",
        "style_number,style_name,category,fabric,gsm,color,print,season,brand,supplier,cost,selling_price,image_url,embedding",
        limit,
    )

    tech_packs = list_records_selected("tech_packs", "style_number,fabric_details,construction", limit)
    tech_pack_map = {item["style_number"]: item for item in tech_packs}

    orders = list_records_selected("sales_orders", "style_number,buyer", limit * 2)
    buyers_by_style: dict[str, set[str]] = {}
    for order in orders:
        style_number = order["style_number"]
        buyers_by_style.setdefault(style_number, set()).add(order["buyer"])

    catalog: list[dict[str, Any]] = []
    for product in products:
        tech_pack = tech_pack_map.get(product["style_number"], {})
        buyers = sorted(buyers_by_style.get(product["style_number"], set()))
        enriched = {
            **product,
            "fabric_details": tech_pack.get("fabric_details"),
            "construction": tech_pack.get("construction"),
            "buyers": buyers,
        }
        enriched["search_text"] = _build_search_text(enriched)
        if buyers:
            enriched["search_text"] += " " + " ".join(buyers)
        catalog.append(enriched)

    return catalog


def _serialize_document(product: dict[str, Any], embedding: list[float]) -> dict[str, Any]:
    document = {
        "id": product["style_number"],
        "style_number": product["style_number"],
        "style_name": product["style_name"],
        "category": product["category"],
        "fabric": product["fabric"],
        "gsm": int(product["gsm"]),
        "color": product["color"],
        "print": product["print"],
        "season": product["season"],
        "brand": product["brand"],
        "supplier": product["supplier"],
        "cost": float(product["cost"]),
        "selling_price": float(product["selling_price"]),
        "search_text": product["search_text"],
        "embedding": embedding,
    }

    if product.get("image_url"):
        document["image_url"] = product["image_url"]
    if product.get("fabric_details"):
        document["fabric_details"] = product["fabric_details"]
    if product.get("construction"):
        document["construction"] = product["construction"]
    if product.get("buyers"):
        document["buyers"] = product["buyers"]

    return document


def _persist_embedding(style_number: str, embedding: list[float]) -> None:
    settings = get_settings()
    if not settings.database_configured:
        return

    vector_literal = "[" + ",".join(str(value) for value in embedding) + "]"
    sql = text(
        "UPDATE finished_goods SET embedding = CAST(:embedding AS vector) WHERE style_number = :style_number"
    )
    with get_sql_engine().begin() as connection:
        connection.execute(
            sql,
            {"embedding": vector_literal, "style_number": style_number},
        )


def index_products(limit: int = 1500, include_embeddings: bool = True) -> dict[str, Any]:
    settings = get_settings()
    catalog = _load_product_catalog(limit=limit)
    documents: list[dict[str, Any]] = []

    for product in catalog:
        embedding = product.get("embedding") or []
        if isinstance(embedding, str): # for backward compatibility 
            embedding = json.loads(embedding)

        if include_embeddings and not embedding:
            image_bytes = _fetch_image_bytes(product.get("image_url"))
            embedding = get_product_embedding(product, image_bytes=image_bytes)
            _persist_embedding(product["style_number"], embedding)

        documents.append(_serialize_document(product, embedding))

    if settings.typesense_configured:
        ensure_collection()
        client = get_typesense_client()
        collection = client.collections[settings.typesense_products_collection]

        for document in documents:
            collection.documents.upsert(document)

    return {
        "indexed_count": len(documents),
        "typesense": settings.typesense_configured,
        "embeddings_generated": include_embeddings,
    }
def _format_hit(hit: dict[str, Any]) -> dict[str, Any]:
    document = hit.get("document", {})
    score = hit.get("text_match_info", {}).get("score")
    vector_distance = hit.get("vector_distance")

    result = {field: document.get(field) for field in PRODUCT_FIELDS if field in document}
    if score is not None:
        result["score"] = float(score)
    if vector_distance is not None:
        similarity = max(0.0, min(1.0, 1.0 - float(vector_distance)))
        result["similarity"] = round(similarity, 4)
        result["similarity_percent"] = round(similarity * 100, 1)

    return result


def _with_match_percent(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scored_items = [item for item in items if item.get("score") is not None]
    max_score = max((float(item["score"]) for item in scored_items), default=0.0)

    for index, item in enumerate(items):
        if item.get("similarity_percent") is not None:
            item["match_percent"] = round(float(item["similarity_percent"]))
            item["match_basis"] = "visual similarity"
            continue

        if max_score > 0 and item.get("score") is not None:
            relative_score = float(item["score"]) / max_score
            item["match_percent"] = round(max(52, min(99, 50 + (relative_score * 49))))
            item["match_basis"] = "search relevance"
            continue

        item["match_percent"] = max(60, 92 - (index * 4))
        item["match_basis"] = "filter match"

    return items


def _build_filter_by(filters: dict[str, Optional[str]]) -> Optional[str]:
    clauses = []
    if filters.get("gsm_min"):
        clauses.append(f"gsm:>={int(filters['gsm_min'])}")
    if filters.get("gsm_max"):
        clauses.append(f"gsm:<={int(filters['gsm_max'])}")
    for field, value in filters.items():
        if not value or field in {"buyer", "gsm_min", "gsm_max"}:
            continue
        clauses.append(f"{field}:={value}")
    return " && ".join(clauses) if clauses else None


def search_products(
    query: str,
    *,
    category: Optional[str] = None,
    color: Optional[str] = None,
    fabric: Optional[str] = None,
    season: Optional[str] = None,
    supplier: Optional[str] = None,
    print_type: Optional[str] = None,
    buyer: Optional[str] = None,
    gsm_min: Optional[str] = None,
    gsm_max: Optional[str] = None,
    limit: int = 12,
) -> dict[str, Any]:
    settings = get_settings()
    filters = {
        "category": category,
        "color": color,
        "fabric": fabric,
        "season": season,
        "supplier": supplier,
        "print": print_type,
        "buyer": buyer,
        "gsm_min": gsm_min,
        "gsm_max": gsm_max,
    }

    if settings.typesense_configured:
        ensure_collection()
        client = get_typesense_client()
        search_query = query or "*"
        if buyer:
            search_query = f"{search_query} {buyer}".strip() if search_query != "*" else buyer
        searchable_fields = [
            "style_name",
            "search_text",
            "category",
            "fabric",
            "color",
            "print",
            "season",
            "brand",
            "supplier",
            "fabric_details",
            "construction",
            "buyers",
        ]
        collection_fields = _get_collection_field_names()
        query_by = ",".join(field for field in searchable_fields if field in collection_fields)
        search_params: dict[str, Any] = {
            "q": search_query,
            "query_by": query_by,
            "per_page": min(max(limit, 1), 50),
        }
        filter_clauses = {
            "category": category,
            "color": color,
            "fabric": fabric,
            "season": season,
            "supplier": supplier,
            "print": print_type,
            "gsm_min": gsm_min,
            "gsm_max": gsm_max,
        }
        filter_by = _build_filter_by(filter_clauses)
        if filter_by:
            search_params["filter_by"] = filter_by

        response = client.collections[settings.typesense_products_collection].documents.search(search_params)
        hits = [_format_hit(hit) for hit in response.get("hits", [])]
        return {"engine": "typesense", "query": query, "count": len(hits), "items": _with_match_percent(hits)}

    return _search_products_supabase(query=query, filters=filters, limit=limit)


def _search_products_supabase(
    query: str,
    filters: dict[str, Optional[str]],
    limit: int,
) -> dict[str, Any]:
    def build_query(client):
        request = client.table("finished_goods").select("*").limit(min(max(limit, 1), 50))
        if query:
            request = request.or_(
                ",".join(
                    [
                        f"style_name.ilike.%{query}%",
                        f"category.ilike.%{query}%",
                        f"fabric.ilike.%{query}%",
                        f"color.ilike.%{query}%",
                        f"print.ilike.%{query}%",
                        f"season.ilike.%{query}%",
                        f"brand.ilike.%{query}%",
                        f"supplier.ilike.%{query}%",
                    ]
                )
            )
        for field, value in filters.items():
            if not value:
                continue
            if field in {"gsm_min", "gsm_max", "buyer"}:
                continue
            request = request.ilike(field, f"%{value}%")
        if filters.get("gsm_min"):
            request = request.gte("gsm", int(filters["gsm_min"]))
        if filters.get("gsm_max"):
            request = request.lte("gsm", int(filters["gsm_max"]))
        return request.execute()

    response = execute_query(build_query)
    items = response.data or []

    if filters.get("buyer"):
        buyer_query = filters["buyer"].lower()
        style_numbers = {
            order["style_number"]
            for order in list_records_selected("sales_orders", "style_number,buyer", 3000)
            if buyer_query in str(order.get("buyer", "")).lower()
        }
        items = [item for item in items if item["style_number"] in style_numbers]

    return {
        "engine": "supabase",
        "query": query,
        "count": len(items),
        "items": _with_match_percent(items),
    }


# def search_similar_products(
#     embedding: list[float],
#     *,
#     limit: int = 12,
# ) -> dict[str, Any]:
#     settings = get_settings()
#     per_page = min(max(limit, 1), 50)

#     if settings.typesense_configured:
#         ensure_collection()
#         client = get_typesense_client()
#         vector_query = f"embedding:([{','.join(str(value) for value in embedding)}], k:{per_page})"
#         response = client.collections[settings.typesense_products_collection].documents.search(
#             {
#                 "q": "*",
#                 "vector_query": vector_query,
#                 "per_page": per_page,
#             }
#         )
#         hits = [_format_hit(hit) for hit in response.get("hits", [])]
#         return {"engine": "typesense", "count": len(hits), "items": hits}

#     return _search_similar_supabase(embedding=embedding, limit=per_page)

def search_similar_products(
    embedding: list[float],
    *,
    limit: int = 12,
) -> dict[str, Any]:
    settings = get_settings()
    per_page = min(max(limit, 1), 50)

    if settings.typesense_configured:
        ensure_collection()

        client = get_typesense_client()

        vector_query = (
            f"embedding:([{','.join(str(value) for value in embedding)}], "
            f"k:{per_page})"
        )

        response = client.multi_search.perform(
            {
                "searches": [
                    {
                        "collection": settings.typesense_products_collection,
                        "q": "*",
                        "vector_query": vector_query,
                        "per_page": per_page,
                    }
                ]
            },
            {},
        )

        result = response["results"][0]

        hits = [_format_hit(hit) for hit in result.get("hits", [])]

        return {
            "engine": "typesense",
            "count": len(hits),
            "items": _with_match_percent(hits),
        }

    return _search_similar_supabase(
        embedding=embedding,
        limit=per_page,
    )

def _search_similar_supabase(embedding: list[float], limit: int) -> dict[str, Any]:
    settings = get_settings()
    if not settings.database_configured:
        raise RuntimeError("Vector search requires Typesense or DATABASE_URL with pgvector embeddings.")

    vector_literal = "[" + ",".join(str(value) for value in embedding) + "]"
    sql = text(
        """
        SELECT
            style_number,
            style_name,
            category,
            fabric,
            gsm,
            color,
            print,
            season,
            brand,
            supplier,
            cost,
            selling_price,
            image_url,
            1 - (embedding <=> CAST(:query_embedding AS vector)) AS similarity
        FROM finished_goods
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:query_embedding AS vector)
        LIMIT :limit
        """
    )

    with get_sql_engine().connect() as connection:
        rows = connection.execute(
            sql,
            {"query_embedding": vector_literal, "limit": limit},
        ).mappings().all()

    items = []
    for row in rows:
        item = dict(row)
        similarity = float(item.pop("similarity", 0.0))
        item["similarity"] = round(similarity, 4)
        item["similarity_percent"] = round(similarity * 100, 1)
        items.append(item)

    return {"engine": "supabase", "count": len(items), "items": _with_match_percent(items)}
