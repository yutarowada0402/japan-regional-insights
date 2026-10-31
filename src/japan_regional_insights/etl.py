"""Download e-Stat observations and materialize Bronze/Silver/Gold in DuckDB."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import requests

API_URL = "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData"
SOURCE = "e-Stat API (Statistics Bureau of Japan)"


def fetch_table(stats_data_id: str, app_id: str) -> dict[str, Any]:
    """Fetch a full table using e-Stat API v3.0 JSON endpoint."""
    response = requests.get(API_URL, params={"appId": app_id, "statsDataId": stats_data_id}, timeout=90)
    response.raise_for_status()
    payload = response.json()
    result = payload.get("GET_STATS_DATA", {}).get("RESULT", {})
    if result.get("STATUS") != 0:
        raise RuntimeError(f"e-Stat API error: {result.get('ERROR_MSG', result)}")
    return payload


def _records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload["GET_STATS_DATA"]["STATISTICAL_DATA"]
    values = data.get("DATA_INF", {}).get("VALUE", [])
    if isinstance(values, dict):
        values = [values]
    return values


def _flatten(payload: dict[str, Any], indicator: str) -> list[dict[str, Any]]:
    root = payload["GET_STATS_DATA"]["STATISTICAL_DATA"]
    class_map: dict[str, dict[str, str]] = {}
    class_names: dict[str, dict[str, str]] = {}
    for category in root.get("CLASS_INF", {}).get("CLASS_OBJ", []):
        classes = category.get("CLASS", [])
        if isinstance(classes, dict):
            classes = [classes]
        class_map[category["@id"]] = {item["@code"]: item.get("@name", item["@code"]) for item in classes}
        class_names[category["@id"]] = {item.get("@code", ""): item.get("@name", "") for item in classes}
    rows = []
    population: dict[tuple[str, int], dict[str, Any]] = {}
    table = root.get("TABLE_INF", {})
    source_updated_date = str(table.get("UPDATED_DATE", ""))
    for value in _records(payload):
        area_code = str(value.get("@area", ""))
        area = class_map.get("area", {}).get(area_code, "")
        # e-Stat's area codes use five digits; exclude the national aggregate.
        if len(area_code) != 5 or not area_code.isdigit() or area_code == "00000":
            continue
        time_code = str(value.get("@time", ""))
        time_name = class_names.get("time", {}).get(time_code, "")
        year_text = re.search(r"\d{4}", time_name)
        if not year_text:
            continue
        year = int(year_text.group())
        # Table 0003448225 publishes population by sex, age group and population type.
        # Use total sex (000), total population (001), and the total age group (000).
        if value.get("@cat01") != "000" or value.get("@cat03") != "001":
            continue
        raw = value.get("$", "")
        try:
            number = float(raw.replace(",", ""))
        except (ValueError, AttributeError):
            number = None
        row = {
            "prefecture_code": area_code,
            "prefecture": area,
            "year": year,
            "value": number,
            "unit": value.get("@unit", ""),
            "source": SOURCE,
            "stats_data_id": payload["GET_STATS_DATA"].get("PARAMETER", {}).get("STATS_DATA_ID", ""),
            "source_updated_date": source_updated_date,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        age_code = str(value.get("@cat02", ""))
        key = (area_code, year)
        if age_code == "000":
            prior = population.get(key, {})
            population[key] = {**prior, **row, "indicator": "population"}
        elif age_code == "003":
            population.setdefault(key, {})["elderly"] = row
    for values in population.values():
        total = values.get("value")
        elderly = values.get("elderly")
        if total is not None:
            rows.append({key: value for key, value in values.items() if key != "elderly"})
        if elderly and elderly.get("value") is not None and total:
            rows.append({
                **{key: elderly[key] for key in ("prefecture_code", "prefecture", "year", "source", "stats_data_id", "updated_at")},
                "indicator": "aging_rate",
                "value": elderly["value"] / total * 100,
                "unit": "%",
            })
    return rows


def ingest(app_id: str | None = None, database: str | Path = "data/regional_insights.duckdb") -> int:
    """Fetch configured e-Stat tables and build the analytical mart."""
    app_id = app_id or os.getenv("ESTAT_APP_ID")
    if not app_id:
        raise ValueError("Set ESTAT_APP_ID (register an application in the e-Stat API portal).")
    db = Path(database)
    db.parent.mkdir(parents=True, exist_ok=True)
    bronze = db.parent / "bronze"
    bronze.mkdir(parents=True, exist_ok=True)
    # This table contains total population and 65+ population, so both metrics
    # are derived together from verified dimensions and use one source record.
    configs = [("population", os.getenv("ESTAT_POPULATION_STATS_ID", "0003448225"))]
    rows: list[dict[str, Any]] = []
    for indicator, stats_id in configs:
        payload = fetch_table(stats_id, app_id)
        path = bronze / f"{indicator}_{stats_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        rows.extend(_flatten(payload, indicator))
    if not rows:
        raise RuntimeError("e-Stat returned no prefectural observations. Check table ID and metadata.")
    con = duckdb.connect(str(db))
    con.register("incoming", pd.DataFrame(rows))
    con.execute("CREATE OR REPLACE TABLE bronze_observations AS SELECT * FROM incoming")
    con.execute("""CREATE OR REPLACE TABLE silver_observations AS
        SELECT DISTINCT * FROM bronze_observations
        WHERE prefecture_code IS NOT NULL AND prefecture <> '' AND year IS NOT NULL AND value IS NOT NULL""")
    con.execute("""CREATE OR REPLACE TABLE gold_regional_metrics AS
        SELECT prefecture_code, prefecture, year,
          MAX(value) FILTER (WHERE indicator='population') AS population,
          MAX(value) FILTER (WHERE indicator='aging_rate') AS aging_rate,
          MAX(unit) FILTER (WHERE indicator='population') AS population_unit,
          MAX(unit) FILTER (WHERE indicator='aging_rate') AS aging_rate_unit,
          MAX(source) AS source, MAX(stats_data_id) AS stats_data_id,
          MAX(source_updated_date) AS source_updated_date,
          MAX(updated_at) AS updated_at
        FROM silver_observations GROUP BY prefecture_code, prefecture, year""")
    count = con.execute("SELECT count(*) FROM gold_regional_metrics").fetchone()[0]
    con.close()
    return count


if __name__ == "__main__":
    print(f"Loaded {ingest()} prefecture-year rows")
