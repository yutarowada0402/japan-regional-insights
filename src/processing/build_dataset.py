"""Build Silver/Gold datasets: run dbt, then export Parquet + CSV mirrors.

Usage (from the repository root):
    python -m src.processing.build_dataset [--bronze PATH] [--export-dir DIR]

The DuckDB database file and the Bronze CSV location are passed to dbt via
environment variables (JRI_DUCKDB_PATH / JRI_BRONZE_CSV), matching
dbt/profiles.yml and dbt/dbt_project.yml. Exports land in data/silver and
data/gold unless --export-dir redirects them (used by the data-update
workflow so a failed run never touches the published data).
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]

EXPORTS: dict[str, tuple[str, str]] = {
    # table -> (layer, file stem)
    "stg_population_by_age_group": ("silver", "population_by_age_group"),
    "fact_regional_indicator": ("gold", "fact_regional_indicator"),
    "gold_prefecture_year": ("gold", "prefecture_year"),
}


def run_dbt(bronze_csv: Path, duckdb_path: Path) -> None:
    env = {
        **os.environ,
        "JRI_BRONZE_CSV": str(bronze_csv),
        "JRI_DUCKDB_PATH": str(duckdb_path),
    }
    dbt_bin = Path(sys.executable).with_name("dbt")
    cmd = [
        str(dbt_bin),
        "build",
        "--project-dir",
        str(REPO_ROOT / "dbt"),
        "--profiles-dir",
        str(REPO_ROOT / "dbt"),
    ]
    logger.info("Running: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, env=env, cwd=REPO_ROOT)


def export_tables(duckdb_path: Path, data_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    con = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        for table, (layer, stem) in EXPORTS.items():
            out_dir = data_dir / layer
            out_dir.mkdir(parents=True, exist_ok=True)
            parquet_path = out_dir / f"{stem}.parquet"
            csv_path = out_dir / f"{stem}.csv"
            con.execute(
                f"COPY {table} TO '{parquet_path}' (FORMAT PARQUET)"
            )
            con.execute(f"COPY {table} TO '{csv_path}' (FORMAT CSV, HEADER)")
            counts[table] = con.execute(
                f"SELECT count(*) FROM {table}"
            ).fetchone()[0]
            logger.info("Exported %s: %d rows", table, counts[table])
    finally:
        con.close()
    return counts


def validate(counts: dict[str, int]) -> None:
    gold = counts["gold_prefecture_year"]
    if gold == 0 or gold % 47 != 0:
        raise RuntimeError(
            f"gold_prefecture_year row count {gold} is not a multiple of 47"
        )
    if counts["fact_regional_indicator"] != gold * 2:
        raise RuntimeError("fact/gold row-count mismatch")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--bronze", type=Path, default=None)
    parser.add_argument("--duckdb-path", type=Path, default=None)
    parser.add_argument(
        "--export-dir",
        type=Path,
        default=None,
        help="Export under this directory instead of --data-dir",
    )
    args = parser.parse_args()

    bronze_csv = (
        args.bronze or args.data_dir / "bronze" / "population_by_age_group.csv"
    ).resolve()
    if not bronze_csv.exists():
        raise FileNotFoundError(
            f"Bronze CSV not found: {bronze_csv} (run src.ingestion.download first)"
        )
    duckdb_path = (args.duckdb_path or args.data_dir / "jri.duckdb").resolve()
    duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    if duckdb_path.exists():
        duckdb_path.unlink()  # rebuild from scratch: Bronze is the source of truth

    run_dbt(bronze_csv, duckdb_path)
    counts = export_tables(duckdb_path, args.export_dir or args.data_dir)
    validate(counts)
    logger.info("Dataset build complete: %s", counts)


if __name__ == "__main__":
    main()
