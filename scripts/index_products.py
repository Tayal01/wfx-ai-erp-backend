from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT_DIR))

from app.services.typesense_service import index_products


def main() -> None:
    parser = argparse.ArgumentParser(description="Index ERP products into Typesense and pgvector.")
    parser.add_argument("--limit", type=int, default=1500, help="Maximum products to index.")
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Skip CLIP embedding generation (text index only).",
    )
    args = parser.parse_args()

    result = index_products(limit=args.limit, include_embeddings=not args.skip_embeddings)
    print(
        f"Indexed {result['indexed_count']} products "
        f"(typesense={'yes' if result['typesense'] else 'no'}, "
        f"embeddings={'yes' if result['embeddings_generated'] else 'no'})."
    )


if __name__ == "__main__":
    main()
