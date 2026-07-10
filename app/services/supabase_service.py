from __future__ import annotations

"""Supabase data access service."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from functools import lru_cache
import time
from typing import Any, Optional

from sqlalchemy import text
from supabase import Client, create_client

from app.config.settings import get_settings
from app.services.vanna_service import get_sql_engine


DASHBOARD_SUMMARY_TTL_SECONDS = 120
PRODUCT_DETAIL_TTL_SECONDS = 120
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


def _monthly_skeleton(months: int = MONTHLY_TREND_MONTHS) -> dict[str, dict[str, Any]]:
    """Ordered YYYY-MM buckets for the last `months` months, seeded with zeros."""
    today = date.today()
    base_index = today.year * 12 + (today.month - 1)
    start_index = base_index - (months - 1)

    skeleton: dict[str, dict[str, Any]] = {}
    for offset in range(months):
        idx = start_index + offset
        year, month = idx // 12, idx % 12 + 1
        key = f"{year:04d}-{month:02d}"
        skeleton[key] = {
            "month": key,
            "label": date(year, month, 1).strftime("%b %y"),
            "orders": 0,
            "revenue": 0.0,
        }
    return skeleton


def _fetch_rows(connection, sql: str) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(text(sql)).mappings().all()]


def _normalize_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except TypeError:
            return str(value)
    if isinstance(value, Decimal):
        return float(value)
    return value


def _normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: _normalize_value(value) for key, value in row.items()} for row in rows]


def get_dashboard_summary() -> dict[str, Any]:
    """Aggregate the whole dashboard in SQL (GROUP BY / SUM) so the API never pulls
    thousands of rows into memory. Cached briefly to absorb repeat loads."""
    now = time.time()
    cached_value = _dashboard_summary_cache["value"]
    cached_timestamp = _dashboard_summary_cache["timestamp"]

    if cached_value and (now - cached_timestamp) < DASHBOARD_SUMMARY_TTL_SECONDS:
        return cached_value

    with get_sql_engine().connect() as connection:
        kpis = connection.execute(
            text(
                """
                SELECT
                    (SELECT COUNT(*) FROM buyers) AS buyers,
                    (SELECT COUNT(*) FROM suppliers) AS suppliers,
                    (SELECT COUNT(*) FROM finished_goods) AS finished_goods,
                    (SELECT COUNT(*) FROM sales_orders) AS sales_orders,
                    (SELECT COUNT(*) FROM sales_invoices) AS sales_invoices,
                    (SELECT COALESCE(SUM(quantity * unit_price), 0) FROM sales_orders) AS order_revenue,
                    (SELECT COALESCE(SUM(amount), 0) FROM sales_invoices) AS invoice_amount,
                    (SELECT COALESCE(SUM(amount), 0) FROM sales_invoices
                        WHERE lower(payment_status) <> 'paid') AS pending_invoice_amount
                """
            )
        ).mappings().one()

        categories = _fetch_rows(
            connection,
            "SELECT category, COUNT(*) AS count FROM finished_goods "
            "GROUP BY category ORDER BY count DESC",
        )
        payment_status = _fetch_rows(
            connection,
            "SELECT payment_status AS status, COUNT(*) AS count FROM sales_invoices "
            "GROUP BY payment_status ORDER BY payment_status",
        )
        order_status = _fetch_rows(
            connection,
            "SELECT status, COUNT(*) AS count FROM sales_orders "
            "GROUP BY status ORDER BY status",
        )
        top_buyers = _fetch_rows(
            connection,
            "SELECT buyer, SUM(quantity * unit_price) AS revenue FROM sales_orders "
            "GROUP BY buyer ORDER BY revenue DESC LIMIT 8",
        )
        monthly = _fetch_rows(
            connection,
            "SELECT to_char(date_trunc('month', shipment_date), 'YYYY-MM') AS month, "
            "COUNT(*) AS orders, COALESCE(SUM(quantity * unit_price), 0) AS revenue "
            "FROM sales_orders "
            "WHERE shipment_date >= (date_trunc('month', CURRENT_DATE) - INTERVAL '11 months') "
            "GROUP BY 1",
        )
        recent_orders = _fetch_rows(
            connection,
            "SELECT order_number, buyer, style_number, quantity, status, shipment_date "
            "FROM sales_orders ORDER BY shipment_date DESC LIMIT 10",
        )
        recent_products = _fetch_rows(
            connection,
            "SELECT style_number, style_name, category, color, fabric, season, supplier "
            "FROM finished_goods ORDER BY created_at DESC LIMIT 10",
        )

    skeleton = _monthly_skeleton()
    for row in monthly:
        bucket = skeleton.get(row["month"])
        if bucket is not None:
            bucket["orders"] = int(row["orders"] or 0)
            bucket["revenue"] = round(float(row["revenue"] or 0), 2)
    monthly_trend = list(skeleton.values())

    summary = {
        "kpis": {
            "buyers": int(kpis["buyers"] or 0),
            "suppliers": int(kpis["suppliers"] or 0),
            "finished_goods": int(kpis["finished_goods"] or 0),
            "sales_orders": int(kpis["sales_orders"] or 0),
            "sales_invoices": int(kpis["sales_invoices"] or 0),
            "estimated_order_revenue": round(float(kpis["order_revenue"] or 0), 2),
            "invoice_amount": round(float(kpis["invoice_amount"] or 0), 2),
            "pending_invoice_amount": round(float(kpis["pending_invoice_amount"] or 0), 2),
        },
        "charts": {
            "product_categories": [
                {"category": row["category"], "count": int(row["count"])} for row in categories
            ],
            "payment_status": [
                {"status": row["status"], "count": int(row["count"])} for row in payment_status
            ],
            "order_status": [
                {"status": row["status"], "count": int(row["count"])} for row in order_status
            ],
            "top_buyers": [
                {"buyer": row["buyer"], "revenue": round(float(row["revenue"] or 0), 2)}
                for row in top_buyers
            ],
            "monthly_trend": monthly_trend,
        },
        "recent": {
            "orders": _normalize_rows(recent_orders),
            "products": _normalize_rows(recent_products),
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
