from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
import json
import re

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config.settings import get_settings


ALLOWED_TABLES = {
    "buyers",
    "suppliers",
    "finished_goods",
    "sales_orders",
    "sales_invoices",
    "tech_packs",
}
MAX_RESULT_ROWS = 100
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
SQL_BLOCKLIST = (
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "truncate",
    "create",
    "grant",
    "revoke",
    "comment",
    "vacuum",
    "analyze",
    "copy",
)


def get_vanna_status() -> str:
    settings = get_settings()
    if settings.openrouter_configured and settings.database_configured:
        return "configured"
    if settings.openrouter_configured:
        return "llm_only"
    return "not_configured"


@lru_cache
def get_schema_context() -> str:
    schema_path = Path(__file__).resolve().parents[2] / "database" / "schema.sql"
    return schema_path.read_text(encoding="utf-8")


@lru_cache
def get_sql_engine() -> Engine:
    settings = get_settings()
    if not settings.database_configured:
        raise RuntimeError("DATABASE_URL is not configured. Add the Supabase Postgres connection string to .env.")

    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        future=True,
    )


def _extract_sql(content: str) -> str:
    match = re.search(r"```sql\s*(.*?)```", content, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()

    fenced = re.search(r"```(.*?)```", content, flags=re.DOTALL)
    if fenced:
        return fenced.group(1).strip()

    return content.strip()


def _validate_sql(sql: str) -> str:
    candidate = _extract_sql(sql).strip().rstrip(";")
    normalized = re.sub(r"\s+", " ", candidate).strip().lower()

    if not normalized:
        raise ValueError("The model did not return SQL.")

    if not (normalized.startswith("select") or normalized.startswith("with")):
        raise ValueError("Only SELECT queries are allowed.")

    if ";" in candidate:
        raise ValueError("Multiple SQL statements are not allowed.")

    for keyword in SQL_BLOCKLIST:
        if re.search(rf"\b{keyword}\b", normalized):
            raise ValueError(f"Blocked SQL keyword detected: {keyword}.")

    referenced_tables = {
        table.lower()
        for table in re.findall(r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", normalized)
    }
    disallowed = referenced_tables - ALLOWED_TABLES
    if disallowed:
        raise ValueError(f"Query references disallowed tables: {', '.join(sorted(disallowed))}.")

    return candidate


def _apply_row_limit(sql: str, limit: int = MAX_RESULT_ROWS) -> str:
    return f"SELECT * FROM ({sql}) AS ai_query LIMIT {limit}"


def _normalize_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except TypeError:
            return str(value)
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="ignore")
    return value


def execute_safe_sql(sql: str) -> dict[str, Any]:
    validated_sql = _validate_sql(sql)
    limited_sql = _apply_row_limit(validated_sql)

    with get_sql_engine().connect() as connection:
        result = connection.execute(text(limited_sql))
        rows = [dict(row) for row in result.mappings().all()]

    normalized_rows = [
        {key: _normalize_value(value) for key, value in row.items()}
        for row in rows
    ]

    return {
        "sql": validated_sql,
        "rows": normalized_rows,
        "row_count": len(normalized_rows),
    }


def _post_openrouter(messages: list[dict[str, str]], temperature: float = 0.1) -> str:
    settings = get_settings()
    if not settings.openrouter_configured:
        raise RuntimeError("OPENROUTER_API_KEY is not configured.")

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.openrouter_model,
        "messages": messages,
        "temperature": temperature,
    }

    with httpx.Client(timeout=45.0) as client:
        response = client.post(OPENROUTER_URL, headers=headers, json=payload)
        response.raise_for_status()
        body = response.json()

    choices = body.get("choices", [])
    if not choices:
        raise RuntimeError("OpenRouter returned no choices.")

    return str(choices[0]["message"]["content"])


def generate_sql(question: str) -> str:
    schema = get_schema_context()
    prompt = [
        {
            "role": "system",
            "content": (
                "You are a senior SQL analyst for an apparel ERP. "
                "Return only one PostgreSQL SELECT query. "
                "Use only these tables: buyers, suppliers, finished_goods, sales_orders, sales_invoices, tech_packs. "
                "Do not write explanations, markdown, comments, or multiple statements."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Database schema:\n{schema}\n\n"
                f"Question:\n{question}\n\n"
                "Return SQL only."
            ),
        },
    ]
    return _post_openrouter(prompt, temperature=0.0)


def summarize_result(question: str, sql: str, rows: list[dict[str, Any]]) -> str:
    preview = json.dumps(rows[:10], ensure_ascii=True, default=str)
    prompt = [
        {
            "role": "system",
            "content": (
                "You are an ERP analyst. Summarize query results in 3-5 concise sentences for a business user. "
                "Mention important numbers and patterns only. Do not mention that you are an AI."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Question: {question}\n"
                f"SQL: {sql}\n"
                f"Result preview: {preview}\n"
                f"Returned rows: {len(rows)}"
            ),
        },
    ]
    return _post_openrouter(prompt, temperature=0.2)


def answer_erp_question(question: str) -> dict[str, Any]:
    sql = generate_sql(question)
    result = execute_safe_sql(sql)
    summary = summarize_result(question=question, sql=result["sql"], rows=result["rows"])

    return {
        "question": question,
        "sql": result["sql"],
        "row_count": result["row_count"],
        "rows": result["rows"],
        "summary": summary,
    }
