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
from app.services.vanna_training import VANNA_DOCUMENTATION, VANNA_EXAMPLES


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
OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
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


def _build_vanna():
    """Compose Vanna from our in-memory vector store (RAG) + OpenRouter as the LLM.

    The store implements Vanna's VannaBase interface with lexical retrieval sized
    to our small curated corpus - no ChromaDB/onnxruntime, so it stays within the
    memory budget of small hosts and has no cold-start model download.

    Imports are local so the rest of this module still loads if the optional
    Vanna extras are not installed in a given environment.
    """
    from openai import OpenAI
    from vanna.openai import OpenAI_Chat

    from app.services.vanna_store import InMemoryVectorStore

    settings = get_settings()

    class WFXVanna(InMemoryVectorStore, OpenAI_Chat):
        def __init__(self) -> None:
            InMemoryVectorStore.__init__(self, config={"n_results_sql": 5})
            OpenAI_Chat.__init__(
                self,
                client=OpenAI(base_url=OPENROUTER_API_BASE, api_key=settings.openrouter_api_key),
                config={"model": settings.openrouter_model, "temperature": 0.0},
            )

    return WFXVanna()


def _is_trained(vanna: Any) -> bool:
    try:
        existing = vanna.get_training_data()
    except Exception:  # noqa: BLE001 - treat any lookup failure as "not trained"
        return False
    return existing is not None and len(existing) > 0


def _train_vanna(vanna: Any) -> None:
    vanna.train(ddl=get_schema_context())
    for documentation in VANNA_DOCUMENTATION:
        vanna.train(documentation=documentation)
    for question, sql in VANNA_EXAMPLES:
        vanna.train(question=question, sql=sql)


@lru_cache
def get_vanna() -> Any:
    settings = get_settings()
    if not settings.openrouter_configured:
        raise RuntimeError("OPENROUTER_API_KEY is not configured.")

    vanna = _build_vanna()
    if not _is_trained(vanna):
        _train_vanna(vanna)
    return vanna


def generate_sql(question: str) -> str:
    """Generate SQL with Vanna: RAG over the trained schema + example queries,
    with OpenRouter as the underlying LLM."""
    vanna = get_vanna()
    sql = vanna.generate_sql(question=question, allow_llm_to_see_data=False)
    return str(sql or "")


def _summary_messages(question: str, sql: str, rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    preview = json.dumps(rows[:10], ensure_ascii=True, default=str)
    return [
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


def summarize_result(question: str, sql: str, rows: list[dict[str, Any]]) -> str:
    return _post_openrouter(_summary_messages(question, sql, rows), temperature=0.2)


def stream_summary(question: str, sql: str, rows: list[dict[str, Any]]):
    """Yield the business summary token-by-token using OpenRouter streaming."""
    from openai import OpenAI

    settings = get_settings()
    client = OpenAI(base_url=OPENROUTER_API_BASE, api_key=settings.openrouter_api_key)
    stream = client.chat.completions.create(
        model=settings.openrouter_model,
        messages=_summary_messages(question, sql, rows),
        temperature=0.2,
        stream=True,
    )
    for chunk in stream:
        try:
            delta = chunk.choices[0].delta.content
        except (AttributeError, IndexError, KeyError):
            delta = None
        if delta:
            yield delta


def stream_erp_answer(question: str):
    """Drive the full NL->SQL flow, yielding (event, data) tuples for SSE:
    status -> sql -> rows -> summary(deltas) -> done."""
    yield ("status", {"step": "generating_sql"})
    sql = generate_sql(question)
    result = execute_safe_sql(sql)  # validates (read-only) and runs

    yield ("sql", {"sql": result["sql"]})
    yield ("status", {"step": "running_query"})
    yield ("rows", {"rows": result["rows"], "row_count": result["row_count"]})

    yield ("status", {"step": "summarizing"})
    for delta in stream_summary(question, result["sql"], result["rows"]):
        yield ("summary", {"delta": delta})

    yield ("done", {"row_count": result["row_count"]})


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
