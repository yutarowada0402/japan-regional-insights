"""Fallback ingestion route: published Excel tables from stat.go.jp.

Uses 第3表 「都道府県、年齢(3区分)、男女別人口－総人口」 of the annual
population estimates (each year as of 1 October). The workbook layout was
verified against the real 2024 file: the 男女計 (both sexes) block holds
15歳未満 / 15～64歳 / 65歳以上 in thousands of persons, and each prefecture
row carries its 2-digit code next to its name. The parser locates the
header and rows structurally and refuses to guess when the layout differs.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import httpx
import openpyxl

from src.ingestion.sources import SOURCE_ID_FILE, StatFileTable

logger = logging.getLogger(__name__)

_CODE_RE = re.compile(r"^\d{2}$")
_EXPECTED_PREFECTURES = 47


def _clean_name(value: Any) -> str:
    return str(value).replace("　", "").replace(" ", "").strip()


def parse_age_group_table(path: Path, table: StatFileTable) -> list[dict[str, Any]]:
    """Parse one 第3表 workbook into Bronze rows (total + elderly)."""
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    sheet = workbook.active
    rows = [list(row) for row in sheet.iter_rows(values_only=True)]

    unit_ok = any(
        cell is not None and "千人" in str(cell) for row in rows[:6] for cell in row
    )
    if not unit_ok:
        raise ValueError(f"{path.name}: unit header (千人) not found; layout changed?")

    header_idx = None
    col_young = col_mid = col_elderly = None
    for idx, row in enumerate(rows[:15]):
        labels = [str(c).strip() if c is not None else "" for c in row]
        if "15歳未満" in labels and "65歳以上" in labels:
            header_idx = idx
            col_young = labels.index("15歳未満")
            col_elderly = labels.index("65歳以上")
            col_mid = labels.index("15～64歳") if "15～64歳" in labels else None
            break
    if header_idx is None or col_mid is None:
        raise ValueError(f"{path.name}: age-group header row not found")

    bronze: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows[header_idx + 1 :]:
        code_cell = None
        name = ""
        for pos, cell in enumerate(row):
            if cell is not None and _CODE_RE.match(str(cell).strip()):
                code_cell = str(cell).strip()
                if pos + 1 < len(row) and row[pos + 1] is not None:
                    name = _clean_name(row[pos + 1])
                break
        if code_cell is None or not name or name.startswith("全国"):
            continue
        try:
            young = float(row[col_young])
            mid = float(row[col_mid])
            elderly = float(row[col_elderly])
        except (TypeError, ValueError):
            raise ValueError(
                f"{path.name}: non-numeric population for prefecture {code_cell}"
            ) from None
        area_code = f"{code_cell}000"
        seen.add(code_cell)
        base = {
            "region_code_estat": area_code,
            "region_name": name,
            "year": table.year,
            "unit": "千人",
            "source_id": SOURCE_ID_FILE,
            "stats_data_id": Path(table.url).name,
            "source_url": table.url,
        }
        bronze.append(
            {**base, "age_group": "total", "value_thousands": young + mid + elderly}
        )
        bronze.append({**base, "age_group": "elderly_65plus", "value_thousands": elderly})

    if len(seen) != _EXPECTED_PREFECTURES:
        raise ValueError(
            f"{path.name}: expected {_EXPECTED_PREFECTURES} prefectures, got {len(seen)}"
        )
    logger.info("%s: parsed %d prefectures for %d", path.name, len(seen), table.year)
    return bronze


def download_table(table: StatFileTable, raw_dir: Path) -> Path:
    """Download one workbook into the Bronze raw directory."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / Path(table.url).name
    logger.info("Downloading %s", table.url)
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        response = client.get(table.url)
        response.raise_for_status()
        dest.write_bytes(response.content)
    return dest
