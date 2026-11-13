"""Definitions of the public data sources used by this project.

Every entry here was verified against the live services on 2026-11-13:
the e-Stat table IDs come from getStatsList/getMetaInfo responses and the
Excel file URLs from the Statistics Bureau's population-estimates pages.
Do not add guessed IDs or URLs.

Primary statistics: 人口推計 (Population Estimates), Statistics Bureau,
Ministry of Internal Affairs and Communications (総務省統計局).
Government statistics code on e-Stat: 00200524.
Reference date for every annual figure: 1 October of the stated year.
Original unit of both routes: 千人 (thousands of persons).
"""

from __future__ import annotations

from dataclasses import dataclass

PROVIDER = "総務省統計局"
STATISTICS_NAME = "人口推計"
GOV_STATISTICS_CODE = "00200524"

SOURCE_ID_API = "estat_api"
SOURCE_ID_FILE = "stat_file"

ESTAT_API_BASE = "https://api.e-stat.go.jp/rest/3.0/app/json"


@dataclass(frozen=True)
class EstatTable:
    """One e-Stat table of the population estimates used for ingestion."""

    stats_data_id: str
    title: str
    years: tuple[int, ...]


# Multi-year tables of 都道府県・年齢(3区分)・男女別人口 (総人口).
# Category layouts differ between the two tables (the age/population class
# positions are swapped), so the client resolves classes from metadata by
# class name instead of assuming fixed cat01/cat02/cat03 positions.
ESTAT_TABLES: tuple[EstatTable, ...] = (
    EstatTable(
        stats_data_id="0004021110",
        title="都道府県，年齢（3区分），男女別人口－総人口，日本人人口（各年10月1日現在）",
        years=(2016, 2017, 2018, 2019, 2020),
    ),
    EstatTable(
        stats_data_id="0003448225",
        title="都道府県，年齢（3区分），男女別人口－総人口，日本人人口",
        years=(2021, 2022, 2023, 2024),
    ),
)

# Related table verified via getMetaInfo on 2026-11-13 (not used for the
# indicators, recorded for provenance): the 5-year age-group table
# 0003448237 (都道府県，年齢(5歳階級)，男女別人口, 2020-2024).


@dataclass(frozen=True)
class StatFileTable:
    """One published Excel table (第3表) on stat.go.jp used as fallback."""

    year: int
    url: str


# Fallback route: 人口推計 各年10月1日現在 第3表
# 「都道府県、年齢(3区分)、男女別人口－総人口」 (Excel, unit: 千人).
# URLs were taken from each year's result page, e.g.
# https://www.stat.go.jp/data/jinsui/2024np/index.html
STAT_FILE_TABLES: tuple[StatFileTable, ...] = (
    StatFileTable(
        year=2019,
        url="https://www.stat.go.jp/data/jinsui/2019np/zuhyou/05k01-3.xlsx",
    ),
    StatFileTable(
        year=2021,
        url="https://www.stat.go.jp/data/jinsui/2021np/zuhyou/05k2021-3.xlsx",
    ),
    StatFileTable(
        year=2022,
        url="https://www.stat.go.jp/data/jinsui/2022np/zuhyou/05k2022-3.xlsx",
    ),
    StatFileTable(
        year=2023,
        url="https://www.stat.go.jp/data/jinsui/2023np/zuhyou/05k2023-3.xlsx",
    ),
    StatFileTable(
        year=2024,
        url="https://www.stat.go.jp/data/jinsui/2024np/zuhyou/05k2024-3.xlsx",
    ),
)

BRONZE_COLUMNS: tuple[str, ...] = (
    "region_code_estat",
    "region_name",
    "year",
    "age_group",
    "value_thousands",
    "unit",
    "source_id",
    "stats_data_id",
    "source_url",
    "retrieved_at",
)
