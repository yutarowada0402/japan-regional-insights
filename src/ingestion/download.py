"""Ingestion entry point: build the Bronze CSV from public sources.

Route selection (``--route auto``, default):
1. If ``ESTAT_APP_ID`` is set, use the e-Stat API (primary route).
2. Otherwise, download the published Excel tables from stat.go.jp.

Outputs (under ``--data-dir``, default ``data/``):
- ``bronze/population_by_age_group.csv`` - normalised Bronze rows
- ``bronze/raw/`` - untouched downloads / API responses (git-ignored)

The Bronze CSV keeps original values (in thousands) plus provenance
columns; all modelling decisions happen downstream in dbt.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.ingestion.estat_client import EstatNotConfigured, estat_client_from_env
from src.ingestion.sources import (
    BRONZE_COLUMNS,
    ESTAT_TABLES,
    SOURCE_ID_API,
    STAT_FILE_TABLES,
)
from src.ingestion.stat_file import download_table, parse_age_group_table

logger = logging.getLogger(__name__)
JST = ZoneInfo("Asia/Tokyo")


def fetch_via_api(raw_dir: Path) -> list[dict[str, Any]]:
    client = estat_client_from_env()
    rows: list[dict[str, Any]] = []
    raw_dir.mkdir(parents=True, exist_ok=True)
    for table in ESTAT_TABLES:
        table_rows, raw_json = client.fetch_table(table)
        raw_path = raw_dir / f"estat_{table.stats_data_id}.json"
        raw_path.write_text(
            json.dumps(raw_json, ensure_ascii=False), encoding="utf-8"
        )
        rows.extend(table_rows)
    return rows


def fetch_via_files(raw_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for table in STAT_FILE_TABLES:
        path = download_table(table, raw_dir)
        rows.extend(parse_age_group_table(path, table))
    return rows


def write_bronze_csv(rows: list[dict[str, Any]], dest: Path) -> None:
    retrieved_at = datetime.now(JST).isoformat(timespec="seconds")
    dest.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(
        rows,
        key=lambda r: (int(r["year"]), str(r["region_code_estat"]), str(r["age_group"])),
    )
    with dest.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(BRONZE_COLUMNS))
        writer.writeheader()
        for row in ordered:
            writer.writerow({**row, "retrieved_at": retrieved_at})


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data", type=Path)
    parser.add_argument(
        "--route", choices=("auto", "api", "file"), default="auto"
    )
    args = parser.parse_args()

    bronze_dir = args.data_dir / "bronze"
    raw_dir = bronze_dir / "raw"

    rows: list[dict[str, Any]] | None = None
    if args.route in ("auto", "api"):
        try:
            rows = fetch_via_api(raw_dir)
            logger.info("Route: e-Stat API (%s)", SOURCE_ID_API)
        except EstatNotConfigured:
            if args.route == "api":
                raise
            logger.info("ESTAT_APP_ID not set; falling back to published files")
    if rows is None:
        rows = fetch_via_files(raw_dir)
        logger.info("Route: published Excel files from stat.go.jp")

    dest = bronze_dir / "population_by_age_group.csv"
    write_bronze_csv(rows, dest)
    years = sorted({int(r["year"]) for r in rows})
    logger.info("Wrote %d bronze rows (%s) to %s", len(rows), years, dest)


if __name__ == "__main__":
    main()
