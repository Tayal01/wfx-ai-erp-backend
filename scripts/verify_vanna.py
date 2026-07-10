from __future__ import annotations

"""Prove the NL->SQL layer is genuinely Vanna (RAG), not a plain LLM prompt.

    .venv/bin/python scripts/verify_vanna.py "Who are my top three buyers?"

Shows the class hierarchy (must include Vanna's ChromaDB_VectorStore + OpenAI_Chat),
the training row count, the examples Vanna retrieves for the question (the RAG step),
and the SQL it generates.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT_DIR))

from app.services import vanna_service as vs


def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 else "Who are my top three buyers by total sales value?"

    vanna = vs.get_vanna()

    print("Class :", type(vanna).__name__)
    print("MRO   :", " <- ".join(c.__name__ for c in type(vanna).__mro__ if c.__name__ != "object"))
    print("Store :", "ChromaDB @", vs.VANNA_CHROMA_PATH)
    print("Trained rows:", len(vanna.get_training_data()))

    print(f"\nQuestion: {question}")
    print("Retrieved similar examples (RAG):")
    for item in vanna.get_similar_question_sql(question)[:3]:
        print("  -", item.get("question"))

    print("\nGenerated SQL:")
    print(" ", " ".join(vs.generate_sql(question).split()))


if __name__ == "__main__":
    main()
