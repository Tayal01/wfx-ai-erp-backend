from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from supabase import Client, create_client

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT_DIR))

from app.config.settings import get_settings


DATA_DIR = ROOT_DIR.parent / "docs" / "data"


@dataclass(frozen=True)
class Dataset:
    table: str
    filename: str
    primary_key: str
    expected_rows: int
    numeric_fields: tuple[str, ...] = ()
    integer_fields: tuple[str, ...] = ()


DATASETS = (
    Dataset("buyers", "buyers.csv", "buyer_id", 12),
    Dataset(
        "suppliers",
        "suppliers.csv",
        "supplier_id",
        12,
        numeric_fields=("rating",),
        integer_fields=("lead_time_days",),
    ),
    Dataset(
        "finished_goods",
        "finished_goods.csv",
        "style_number",
        1000,
        numeric_fields=("cost", "selling_price"),
        integer_fields=("gsm",),
    ),
    Dataset(
        "sales_orders",
        "sales_orders.csv",
        "order_number",
        1500,
        numeric_fields=("unit_price",),
        integer_fields=("quantity",),
    ),
    Dataset(
        "sales_invoices",
        "sales_invoices.csv",
        "invoice_number",
        1206,
        numeric_fields=("amount",),
    ),
    Dataset("tech_packs", "tech_packs.csv", "tech_pack_id", 1000),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import WFX ERP CSV data into Supabase.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate CSV files and print counts without writing to Supabase.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Number of records to upsert per Supabase request.",
    )
    return parser.parse_args()


def load_rows(dataset: Dataset) -> list[dict[str, Any]]:
    csv_path = DATA_DIR / dataset.filename
    if not csv_path.exists():
        raise FileNotFoundError(f"Missing CSV file: {csv_path}")

    with csv_path.open(newline="", encoding="utf-8-sig") as file:
        rows = [normalize_row(row, dataset) for row in csv.DictReader(file)]

    if len(rows) != dataset.expected_rows:
        raise ValueError(
            f"{dataset.filename} expected {dataset.expected_rows} rows but found {len(rows)}"
        )

    return rows


def normalize_row(row: dict[str, str], dataset: Dataset) -> dict[str, Any]:
    normalized: dict[str, Any] = {}

    for key, value in row.items():
        clean_value = value.strip() if isinstance(value, str) else value
        if key in dataset.integer_fields:
            normalized[key] = int(clean_value)
        elif key in dataset.numeric_fields:
            normalized[key] = float(clean_value)
        else:
            normalized[key] = clean_value

    return normalized


def get_supabase_client() -> Client:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError(
            "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env before importing."
        )

    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def upsert_dataset(client: Client, dataset: Dataset, rows: list[dict[str, Any]], batch_size: int) -> None:
    for index in range(0, len(rows), batch_size):
        batch = rows[index : index + batch_size]
        client.table(dataset.table).upsert(batch, on_conflict=dataset.primary_key).execute()


def main() -> None:
    args = parse_args()
    loaded_data = [(dataset, load_rows(dataset)) for dataset in DATASETS]

    print("Validated ERP CSV files:")
    for dataset, rows in loaded_data:
        print(f"- {dataset.table}: {len(rows)} rows")

    if args.dry_run:
        print("Dry run complete. No data was written to Supabase.")
        return

    client = get_supabase_client()
    for dataset, rows in loaded_data:
        upsert_dataset(client, dataset, rows, args.batch_size)
        print(f"Imported {len(rows)} rows into {dataset.table}.")

    print("ERP data import complete.")


if __name__ == "__main__":
    main()
