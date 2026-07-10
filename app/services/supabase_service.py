from __future__ import annotations

"""Supabase data access service."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from functools import lru_cache
import time
from typing import Any, Optional

from supabase import Client, create_client

from app.config.settings import get_settings


DASHBOARD_SUMMARY_TTL_SECONDS = 30
PRODUCT_DETAIL_TTL_SECONDS = 120
SUMMARY_QUERY_WORKERS = 6
_dashboard_summary_cache: dict[str, Any] = {
    "value": None,
    "timestamp": 0.0,
}
_product_detail_cache: dict[str, dict[str, Any]] = {}


def get_supabase_status() -> str:
    settings = get_settings()
    return "configured" if settings.supabase_configured else "not_configured"


@lru_cache
def get_supabase_client() -> Client:
    settings = get_settings()
    if not settings.supabase_configured:
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")

    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def is_transient_supabase_error(error: Exception) -> bool:
    message = str(error).lower()
    if "resource temporarily unavailable" in message:
        return True
    if "temporary failure" in message:
        return True
    if "connection reset" in message:
        return True
    if "connection aborted" in message:
        return True
    if "timed out" in message:
        return True
    if "network" in message and "error" in message:
        return True
    return isinstance(error, OSError)


def execute_query(query_factory, retries: int = 3):
    last_error: Optional[Exception] = None

    for attempt in range(retries):
        try:
            return query_factory(get_supabase_client())
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if not is_transient_supabase_error(exc) or attempt == retries - 1:
                raise

            get_supabase_client.cache_clear()
            time.sleep(0.25 * (attempt + 1))

    raise last_error or RuntimeError("Supabase query failed.")


def list_records(table: str, limit: int = 1000) -> list[dict[str, Any]]:
    return list_records_selected(table=table, columns="*", limit=limit)


def list_records_selected(table: str, columns: str, limit: int = 1000) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    page_size = 1000

    for start in range(0, limit, page_size):
        end = min(start + page_size - 1, limit - 1)
        response = execute_query(
            lambda client: client.table(table).select(columns).range(start, end).execute()
        )
        batch = response.data or []
        records.extend(batch)

        if len(batch) < page_size:
            break

    return records


def count_records(table: str) -> int:
    response = execute_query(
        lambda client: client.table(table).select("*", count="exact").limit(1).execute()
    )
    return int(response.count or 0)


def fetch_records(
    table: str,
    columns: str = "*",
    limit: int = 10,
    order_by: Optional[str] = None,
    descending: bool = False,
) -> list[dict[str, Any]]:
    def build_query(client: Client):
        query = client.table(table).select(columns).limit(limit)
        if order_by:
            query = query.order(order_by, desc=descending)
        return query.execute()

    response = execute_query(build_query)
    return response.data or []


MONTHLY_TREND_MONTHS = 12


def _shipment_month_key(raw: Any) -> str | None:
    """Normalize a shipment_date to a 'YYYY-MM' bucket key. Tolerates ISO
    dates, ISO datetimes ('...T..+00:00'/'Z'), None, empty, and garbage."""
    if not raw:
        return None
    text = str(raw)[:10]  # 'YYYY-MM-DD' prefix works for date or datetime
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return None
    return f"{parsed.year:04d}-{parsed.month:02d}"


def build_monthly_trend(
    orders: list[dict[str, Any]],
    months: int = MONTHLY_TREND_MONTHS,
) -> list[dict[str, Any]]:
    """Fold already-fetched sales orders into the last `months` calendar months
    by shipment_date. Gaps pre-seeded with zeros. Oldest -> newest:
    [{ "month": "YYYY-MM", "label": "Mon YY", "orders": int, "revenue": float }]"""
    today = date.today()
    base_index = today.year * 12 + (today.month - 1)
    start_index = base_index - (months - 1)

    buckets: dict[str, dict[str, Any]] = {}
    for offset in range(months):
        idx = start_index + offset
        year, month = idx // 12, idx % 12 + 1
        key = f"{year:04d}-{month:02d}"
        buckets[key] = {
            "month": key,
            "label": date(year, month, 1).strftime("%b %y"),
            "orders": 0,
            "revenue": 0.0,
        }

    for order in orders:
        key = _shipment_month_key(order.get("shipment_date"))
        if key is None:
            continue
        bucket = buckets.get(key)
        if bucket is None:
            continue
        try:
            qty = float(order.get("quantity") or 0)
            price = float(order.get("unit_price") or 0)
        except (TypeError, ValueError):
            continue
        bucket["orders"] += 1
        bucket["revenue"] += qty * price

    trend = list(buckets.values())  # dict preserves insertion order (oldest->newest)
    for bucket in trend:
        bucket["revenue"] = round(bucket["revenue"], 2)
    return trend


def get_dashboard_summary() -> dict[str, Any]:
    now = time.time()
    cached_value = _dashboard_summary_cache["value"]
    cached_timestamp = _dashboard_summary_cache["timestamp"]

    if cached_value and (now - cached_timestamp) < DASHBOARD_SUMMARY_TTL_SECONDS:
        return cached_value

    with ThreadPoolExecutor(max_workers=SUMMARY_QUERY_WORKERS) as executor:
        buyers_count_future = executor.submit(count_records, "buyers")
        suppliers_count_future = executor.submit(count_records, "suppliers")
        products_count_future = executor.submit(count_records, "finished_goods")
        orders_count_future = executor.submit(count_records, "sales_orders")
        invoices_count_future = executor.submit(count_records, "sales_invoices")
        products_future = executor.submit(
            list_records_selected,
            "finished_goods",
            "style_number,style_name,category",
            1500,
        )
        orders_future = executor.submit(
            list_records_selected,
            "sales_orders",
            "order_number,buyer,style_number,quantity,unit_price,status,shipment_date",
            2500,
        )
        invoices_future = executor.submit(
            list_records_selected,
            "sales_invoices",
            "amount,payment_status",
            2500,
        )
        recent_orders_future = executor.submit(
            fetch_records,
            "sales_orders",
            "order_number,buyer,style_number,quantity,status,shipment_date",
            10,
            "shipment_date",
            True,
        )
        recent_products_future = executor.submit(
            fetch_records,
            "finished_goods",
            "style_number,style_name,category,color,fabric,season,supplier",
            10,
            "created_at",
            True,
        )

        buyers_count = buyers_count_future.result()
        suppliers_count = suppliers_count_future.result()
        products_count = products_count_future.result()
        orders_count = orders_count_future.result()
        invoices_count = invoices_count_future.result()
        products = products_future.result()
        orders = orders_future.result()
        invoices = invoices_future.result()
        recent_orders = recent_orders_future.result()
        recent_products = recent_products_future.result()

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

    monthly_trend = build_monthly_trend(orders)

    summary = {
        "kpis": {
            "buyers": buyers_count,
            "suppliers": suppliers_count,
            "finished_goods": products_count,
            "sales_orders": orders_count,
            "sales_invoices": invoices_count,
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
            "monthly_trend": monthly_trend,
        },
        "recent": {
            "orders": recent_orders,
            "products": recent_products,
        },
    }

    _dashboard_summary_cache["value"] = summary
    _dashboard_summary_cache["timestamp"] = now

    return summary


def list_products(
    page: int = 1,
    page_size: int = 24,
    category: str | None = None,
    color: str | None = None,
    fabric: str | None = None,
    season: str | None = None,
    supplier: str | None = None,
    sort_by: str = "style_number",
    sort_order: str = "asc",
) -> dict[str, Any]:
    allowed_sort_fields = {
        "style_number",
        "style_name",
        "selling_price",
        "cost",
        "gsm",
        "season",
        "category",
    }
    sort_field = sort_by if sort_by in allowed_sort_fields else "style_number"
    descending = sort_order.lower() == "desc"

    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    start = (page - 1) * page_size
    end = start + page_size - 1

    filters = {
        "category": category,
        "color": color,
        "fabric": fabric,
        "season": season,
        "supplier": supplier,
    }

    def build_query(client: Client):
        query = client.table("finished_goods").select("*", count="exact")
        for field, value in filters.items():
            if value:
                query = query.ilike(field, f"%{value}%")
        return query.order(sort_field, desc=descending).range(start, end).execute()

    response = execute_query(build_query)

    return {
        "items": response.data or [],
        "page": page,
        "page_size": page_size,
        "total": int(response.count or 0),
        "sort_by": sort_field,
        "sort_order": "desc" if descending else "asc",
    }


def get_product_detail(style_number: str) -> dict[str, Any] | None:
    now = time.time()
    cached_entry = _product_detail_cache.get(style_number)
    if cached_entry and (now - cached_entry["timestamp"]) < PRODUCT_DETAIL_TTL_SECONDS:
        return cached_entry["value"]

    product_response = execute_query(
        lambda client: client.table("finished_goods")
        .select("*")
        .eq("style_number", style_number)
        .limit(1)
        .execute()
    )
    products = product_response.data or []
    if not products:
        return None

    product = products[0]
    with ThreadPoolExecutor(max_workers=3) as executor:
        tech_pack_future = executor.submit(
            execute_query,
            lambda client: client.table("tech_packs")
            .select("*")
            .eq("style_number", style_number)
            .limit(1)
            .execute(),
        )
        supplier_future = executor.submit(
            execute_query,
            lambda client: client.table("suppliers")
            .select("*")
            .eq("company_name", product["supplier"])
            .limit(1)
            .execute(),
        )
        orders_future = executor.submit(
            execute_query,
            lambda client: client.table("sales_orders")
            .select("*")
            .eq("style_number", style_number)
            .order("shipment_date", desc=True)
            .limit(20)
            .execute(),
        )

        tech_pack = tech_pack_future.result().data or []
        supplier = supplier_future.result().data or []
        orders = orders_future.result().data or []

    order_numbers = [order["order_number"] for order in orders]
    invoices: list[dict[str, Any]] = []
    if order_numbers:
        invoices_response = execute_query(
            lambda client: client.table("sales_invoices")
            .select("*")
            .in_("sales_order", order_numbers)
            .limit(50)
            .execute()
        )
        invoices = invoices_response.data or []

    detail = {
        "product": product,
        "tech_pack": tech_pack[0] if tech_pack else None,
        "supplier": supplier[0] if supplier else None,
        "orders": orders,
        "invoices": invoices,
    }

    _product_detail_cache[style_number] = {
        "value": detail,
        "timestamp": now,
    }

    return detail
