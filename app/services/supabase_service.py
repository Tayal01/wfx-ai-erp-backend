from __future__ import annotations

"""Supabase data access service."""

from functools import lru_cache
from typing import Any

from supabase import Client, create_client

from app.config.settings import get_settings


def get_supabase_status() -> str:
    settings = get_settings()
    return "configured" if settings.supabase_configured else "not_configured"


@lru_cache
def get_supabase_client() -> Client:
    settings = get_settings()
    if not settings.supabase_configured:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")

    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def list_records(table: str, limit: int = 1000) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    page_size = 1000

    for start in range(0, limit, page_size):
        end = min(start + page_size - 1, limit - 1)
        response = get_supabase_client().table(table).select("*").range(start, end).execute()
        batch = response.data or []
        records.extend(batch)

        if len(batch) < page_size:
            break

    return records


def count_records(table: str) -> int:
    response = get_supabase_client().table(table).select("*", count="exact").limit(1).execute()
    return int(response.count or 0)


def get_dashboard_summary() -> dict[str, Any]:
    buyers = list_records("buyers", limit=200)
    suppliers = list_records("suppliers", limit=200)
    products = list_records("finished_goods", limit=1500)
    orders = list_records("sales_orders", limit=2500)
    invoices = list_records("sales_invoices", limit=2500)

    order_revenue = sum(float(order["quantity"]) * float(order["unit_price"]) for order in orders)
    invoice_amount = sum(float(invoice["amount"]) for invoice in invoices)
    pending_invoice_amount = sum(
        float(invoice["amount"])
        for invoice in invoices
        if invoice["payment_status"].lower() != "paid"
    )

    category_counts: dict[str, int] = {}
    for product in products:
        category = product["category"]
        category_counts[category] = category_counts.get(category, 0) + 1

    payment_status_counts: dict[str, int] = {}
    for invoice in invoices:
        status = invoice["payment_status"]
        payment_status_counts[status] = payment_status_counts.get(status, 0) + 1

    top_buyers: dict[str, float] = {}
    for order in orders:
        buyer = order["buyer"]
        revenue = float(order["quantity"]) * float(order["unit_price"])
        top_buyers[buyer] = top_buyers.get(buyer, 0) + revenue

    order_status_counts: dict[str, int] = {}
    for order in orders:
        status = order["status"]
        order_status_counts[status] = order_status_counts.get(status, 0) + 1

    return {
        "kpis": {
            "buyers": len(buyers),
            "suppliers": len(suppliers),
            "finished_goods": len(products),
            "sales_orders": len(orders),
            "sales_invoices": len(invoices),
            "estimated_order_revenue": round(order_revenue, 2),
            "invoice_amount": round(invoice_amount, 2),
            "pending_invoice_amount": round(pending_invoice_amount, 2),
        },
        "charts": {
            "product_categories": [
                {"category": category, "count": count}
                for category, count in sorted(category_counts.items(), key=lambda item: item[1], reverse=True)
            ],
            "payment_status": [
                {"status": status, "count": count}
                for status, count in sorted(payment_status_counts.items())
            ],
            "order_status": [
                {"status": status, "count": count}
                for status, count in sorted(order_status_counts.items())
            ],
            "top_buyers": [
                {"buyer": buyer, "revenue": round(revenue, 2)}
                for buyer, revenue in sorted(top_buyers.items(), key=lambda item: item[1], reverse=True)[:8]
            ],
        },
        "recent": {
            "orders": orders[:10],
            "products": products[:10],
        },
    }


def list_products(
    page: int = 1,
    page_size: int = 24,
    category: str | None = None,
    color: str | None = None,
    fabric: str | None = None,
    season: str | None = None,
    supplier: str | None = None,
) -> dict[str, Any]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    start = (page - 1) * page_size
    end = start + page_size - 1

    query = get_supabase_client().table("finished_goods").select("*", count="exact")
    filters = {
        "category": category,
        "color": color,
        "fabric": fabric,
        "season": season,
        "supplier": supplier,
    }

    for field, value in filters.items():
        if value:
            query = query.ilike(field, f"%{value}%")

    response = query.order("style_number").range(start, end).execute()

    return {
        "items": response.data or [],
        "page": page,
        "page_size": page_size,
        "total": int(response.count or 0),
    }


def get_product_detail(style_number: str) -> dict[str, Any] | None:
    product_response = (
        get_supabase_client()
        .table("finished_goods")
        .select("*")
        .eq("style_number", style_number)
        .limit(1)
        .execute()
    )
    products = product_response.data or []
    if not products:
        return None

    product = products[0]
    tech_pack = (
        get_supabase_client()
        .table("tech_packs")
        .select("*")
        .eq("style_number", style_number)
        .limit(1)
        .execute()
        .data
        or []
    )
    supplier = (
        get_supabase_client()
        .table("suppliers")
        .select("*")
        .eq("company_name", product["supplier"])
        .limit(1)
        .execute()
        .data
        or []
    )
    orders = (
        get_supabase_client()
        .table("sales_orders")
        .select("*")
        .eq("style_number", style_number)
        .order("shipment_date", desc=True)
        .limit(20)
        .execute()
        .data
        or []
    )
    order_numbers = [order["order_number"] for order in orders]
    invoices: list[dict[str, Any]] = []
    if order_numbers:
        invoices = (
            get_supabase_client()
            .table("sales_invoices")
            .select("*")
            .in_("sales_order", order_numbers)
            .limit(50)
            .execute()
            .data
            or []
        )

    return {
        "product": product,
        "tech_pack": tech_pack[0] if tech_pack else None,
        "supplier": supplier[0] if supplier else None,
        "orders": orders,
        "invoices": invoices,
    }
