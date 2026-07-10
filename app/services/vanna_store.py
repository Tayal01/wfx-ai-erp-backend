"""Lightweight in-memory vector store for Vanna.

Implements Vanna's VannaBase storage interface (the same contract as
ChromaDB_VectorStore) with simple lexical retrieval instead of a neural
embedding database. With our small, curated training corpus (~26 rows of DDL,
business docs and example question->SQL pairs), token-overlap retrieval selects
the same examples a vector database would - without ChromaDB + onnxruntime,
which cost hundreds of MB of RAM and an 80 MB model download on constrained
hosts (Railway). Training is instant and happens in-process at startup.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd
from vanna.base import VannaBase


_WORD_RE = re.compile(r"[a-z0-9]+")

# Words that carry no signal for matching an ERP question to a training row.
_STOPWORDS = {
    "a", "an", "and", "are", "by", "for", "from", "how", "in", "is", "me",
    "of", "on", "or", "show", "the", "to", "was", "were", "what", "which",
    "who", "with",
}


def _tokens(text: str) -> set[str]:
    return {word for word in _WORD_RE.findall(text.lower()) if word not in _STOPWORDS}


def _overlap_score(question_tokens: set[str], candidate: str) -> float:
    candidate_tokens = _tokens(candidate)
    if not question_tokens or not candidate_tokens:
        return 0.0
    intersection = len(question_tokens & candidate_tokens)
    if intersection == 0:
        return 0.0
    # Overlap normalized by the smaller set so short questions still match
    # longer documentation entries.
    return intersection / min(len(question_tokens), len(candidate_tokens))


class InMemoryVectorStore(VannaBase):
    """VannaBase-compliant storage with lexical top-k retrieval."""

    def __init__(self, config: dict | None = None) -> None:
        VannaBase.__init__(self, config=config)
        settings = config or {}
        self.n_results_sql = settings.get("n_results_sql", 5)
        self.n_results_documentation = settings.get("n_results_documentation", 6)
        self.n_results_ddl = settings.get("n_results_ddl", 3)
        self._question_sql: list[dict[str, str]] = []
        self._ddl: list[str] = []
        self._documentation: list[str] = []

    # --- embeddings are unused by lexical retrieval, but the interface requires it
    def generate_embedding(self, data: str, **kwargs: Any) -> list[float]:
        return []

    # --- training data ingestion (vn.train(...) routes to these)
    def add_question_sql(self, question: str, sql: str, **kwargs: Any) -> str:
        self._question_sql.append({"question": question, "sql": sql})
        return f"sql-{len(self._question_sql) - 1}"

    def add_ddl(self, ddl: str, **kwargs: Any) -> str:
        self._ddl.append(ddl)
        return f"ddl-{len(self._ddl) - 1}"

    def add_documentation(self, documentation: str, **kwargs: Any) -> str:
        self._documentation.append(documentation)
        return f"doc-{len(self._documentation) - 1}"

    # --- retrieval (used by generate_sql to assemble the RAG prompt)
    def get_similar_question_sql(self, question: str, **kwargs: Any) -> list:
        question_tokens = _tokens(question)
        scored = sorted(
            self._question_sql,
            key=lambda item: _overlap_score(question_tokens, item["question"]),
            reverse=True,
        )
        return [dict(item) for item in scored[: self.n_results_sql]]

    def get_related_ddl(self, question: str, **kwargs: Any) -> list:
        # The schema is one curated document; always include it (plus any extras).
        return list(self._ddl[: self.n_results_ddl])

    def get_related_documentation(self, question: str, **kwargs: Any) -> list:
        question_tokens = _tokens(question)
        scored = sorted(
            self._documentation,
            key=lambda item: _overlap_score(question_tokens, item),
            reverse=True,
        )
        return list(scored[: self.n_results_documentation])

    # --- management/introspection
    def get_training_data(self, **kwargs: Any) -> pd.DataFrame:
        records: list[dict[str, Any]] = []
        for index, item in enumerate(self._question_sql):
            records.append(
                {
                    "id": f"sql-{index}",
                    "training_data_type": "sql",
                    "question": item["question"],
                    "content": item["sql"],
                }
            )
        for index, ddl in enumerate(self._ddl):
            records.append(
                {"id": f"ddl-{index}", "training_data_type": "ddl", "question": None, "content": ddl}
            )
        for index, doc in enumerate(self._documentation):
            records.append(
                {
                    "id": f"doc-{index}",
                    "training_data_type": "documentation",
                    "question": None,
                    "content": doc,
                }
            )
        return pd.DataFrame(records, columns=["id", "training_data_type", "question", "content"])

    def remove_training_data(self, id: str, **kwargs: Any) -> bool:  # noqa: A002 - vanna's signature
        kind, _, index_text = id.partition("-")
        try:
            index = int(index_text)
            if kind == "sql":
                self._question_sql.pop(index)
            elif kind == "ddl":
                self._ddl.pop(index)
            elif kind == "doc":
                self._documentation.pop(index)
            else:
                return False
        except (ValueError, IndexError):
            return False
        return True
