"""e-Stat API client (JSON API v3.0) for the population estimates.

The application ID is read from the ``ESTAT_APP_ID`` environment variable
(locally or from GitHub Secrets in Actions). It is never logged and never
written to disk. When the variable is absent, :func:`estat_client_from_env`
raises :class:`EstatNotConfigured` and the caller falls back to the
published-file route (see :mod:`src.ingestion.stat_file`).

Category positions differ between e-Stat tables, so classes are resolved
from each table's metadata by class *name* (男女別 / 年齢 / 人口), never by
assuming fixed cat01/cat02/cat03 positions.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

from src.ingestion.sources import ESTAT_API_BASE, SOURCE_ID_API, EstatTable
from src.processing.transforms import map_age_group, parse_year_from_time_name

logger = logging.getLogger(__name__)

ENV_APP_ID = "ESTAT_APP_ID"
_REQUEST_LIMIT = 100_000


class EstatNotConfigured(RuntimeError):
    """Raised when ESTAT_APP_ID is not available in the environment."""


class EstatApiError(RuntimeError):
    """Raised when the e-Stat API returns a non-zero status."""


@dataclass(frozen=True)
class ClassInfo:
    class_id: str
    name: str
    codes: dict[str, str]  # code -> label


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def parse_class_info(meta_json: dict[str, Any]) -> dict[str, ClassInfo]:
    """Parse getMetaInfo JSON into {class_id: ClassInfo}."""
    class_objs = (
        meta_json.get("GET_META_INFO", {})
        .get("METADATA_INF", {})
        .get("CLASS_INF", {})
        .get("CLASS_OBJ", [])
    )
    result: dict[str, ClassInfo] = {}
    for obj in _as_list(class_objs):
        codes = {
            str(c["@code"]): str(c.get("@name", ""))
            for c in _as_list(obj.get("CLASS"))
        }
        result[str(obj["@id"])] = ClassInfo(
            class_id=str(obj["@id"]), name=str(obj.get("@name", "")), codes=codes
        )
    return result


def resolve_class(classes: dict[str, ClassInfo], keyword: str) -> ClassInfo:
    """Find the class whose name contains ``keyword`` (e.g. '男女', '年齢')."""
    for info in classes.values():
        if keyword in info.name:
            return info
    raise EstatApiError(f"No class matching {keyword!r} in metadata")


def code_for_label(info: ClassInfo, label: str) -> str:
    for code, name in info.codes.items():
        if name == label:
            return code
    raise EstatApiError(f"Label {label!r} not found in class {info.class_id}")


class EstatClient:
    """Minimal client for getMetaInfo / getStatsData."""

    def __init__(self, app_id: str, timeout: float = 60.0) -> None:
        if not app_id:
            raise EstatNotConfigured(f"{ENV_APP_ID} is empty")
        self._app_id = app_id
        self._client = httpx.Client(timeout=timeout, follow_redirects=False)

    def _get(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        query = {"appId": self._app_id, **params}
        response = self._client.get(f"{ESTAT_API_BASE}/{endpoint}", params=query)
        response.raise_for_status()
        payload = response.json()
        root_key = {
            "getMetaInfo": "GET_META_INFO",
            "getStatsData": "GET_STATS_DATA",
        }[endpoint]
        result = payload.get(root_key, {}).get("RESULT", {})
        if result.get("STATUS") != 0:
            raise EstatApiError(
                f"e-Stat {endpoint} failed: STATUS={result.get('STATUS')} "
                f"{result.get('ERROR_MSG')}"
            )
        return payload

    def get_meta_info(self, stats_data_id: str) -> dict[str, ClassInfo]:
        payload = self._get("getMetaInfo", {"statsDataId": stats_data_id})
        return parse_class_info(payload)

    def fetch_table(self, table: EstatTable) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Fetch total & 65+ population (both sexes, total population).

        Returns (bronze rows, raw getStatsData JSON).
        """
        classes = self.get_meta_info(table.stats_data_id)
        sex = resolve_class(classes, "男女")
        age = resolve_class(classes, "年齢")
        population = resolve_class(classes, "人口")
        time_info = classes["time"]
        area_info = classes["area"]

        def cd(class_id: str) -> str:
            return "cd" + class_id.capitalize()

        params = {
            "statsDataId": table.stats_data_id,
            cd(sex.class_id): code_for_label(sex, "男女計"),
            cd(age.class_id): ",".join(
                [code_for_label(age, "総数"), code_for_label(age, "65歳以上")]
            ),
            cd(population.class_id): code_for_label(population, "総人口"),
            "limit": str(_REQUEST_LIMIT),
        }
        payload = self._get("getStatsData", params)
        values = _as_list(
            payload.get("GET_STATS_DATA", {})
            .get("STATISTICAL_DATA", {})
            .get("DATA_INF", {})
            .get("VALUE", [])
        )
        logger.info(
            "e-Stat table %s: %d values returned", table.stats_data_id, len(values)
        )
        rows: list[dict[str, Any]] = []
        for value in values:
            age_code = str(value[f"@{age.class_id}"])
            time_code = str(value["@time"])
            area_code = str(value["@area"])
            try:
                numeric = float(value["$"])
            except (TypeError, ValueError):
                # Missing/suppressed cells (e.g. '-') are skipped, never imputed.
                logger.warning(
                    "Skipping non-numeric value %r (area=%s time=%s)",
                    value.get("$"),
                    area_code,
                    time_code,
                )
                continue
            rows.append(
                {
                    "region_code_estat": area_code,
                    "region_name": area_info.codes.get(area_code, ""),
                    "year": parse_year_from_time_name(time_info.codes[time_code]),
                    "age_group": map_age_group(age.codes[age_code]),
                    "value_thousands": numeric,
                    "unit": str(value.get("@unit", "千人")),
                    "source_id": SOURCE_ID_API,
                    "stats_data_id": table.stats_data_id,
                    "source_url": f"{ESTAT_API_BASE}/getStatsData",
                }
            )
        return rows, payload


def estat_client_from_env() -> EstatClient:
    """Build a client from ESTAT_APP_ID; raise EstatNotConfigured if absent."""
    app_id = os.environ.get(ENV_APP_ID, "").strip()
    if not app_id:
        raise EstatNotConfigured(
            f"{ENV_APP_ID} is not set; e-Stat API route is unavailable"
        )
    return EstatClient(app_id=app_id)
