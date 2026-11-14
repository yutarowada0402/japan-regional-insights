"""Ingestion parsing tests using synthetic fixtures only.

The fixtures mimic the *verified* layouts of the real sources:
- e-Stat getMetaInfo JSON, including the two tables whose age/population
  class positions are swapped (0004021110 vs 0003448225).
- The stat.go.jp 第3表 workbook layout (header rows + code/name rows).
Real data is never fabricated here; values below are arbitrary test numbers.
"""

from pathlib import Path

import openpyxl
import pytest

from src.ingestion.estat_client import (
    code_for_label,
    parse_class_info,
    resolve_class,
)
from src.ingestion.sources import StatFileTable
from src.ingestion.stat_file import parse_age_group_table


def _meta(class_objs: list[dict]) -> dict:
    return {"GET_META_INFO": {"METADATA_INF": {"CLASS_INF": {"CLASS_OBJ": class_objs}}}}


def _class(cid: str, name: str, pairs: list[tuple[str, str]]) -> dict:
    return {
        "@id": cid,
        "@name": name,
        "CLASS": [{"@code": c, "@name": n} for c, n in pairs],
    }


AGE = [("000", "総数"), ("008", "15歳未満"), ("002", "15～64歳"), ("003", "65歳以上")]
SEX = [("000", "男女計"), ("001", "男"), ("002", "女")]
POP = [("001", "総人口"), ("002", "日本人人口")]


@pytest.mark.parametrize(
    "class_objs",
    [
        # Layout of table 0003448225: cat02=年齢, cat03=人口
        [_class("cat01", "男女別", SEX), _class("cat02", "年齢3区分", AGE), _class("cat03", "人口", POP)],
        # Layout of table 0004021110: cat02=人口, cat03=年齢 (swapped)
        [_class("cat01", "男女別", SEX), _class("cat02", "人口", POP), _class("cat03", "年齢3区分", AGE)],
    ],
)
def test_class_resolution_is_layout_independent(class_objs):
    classes = parse_class_info(_meta(class_objs))
    assert code_for_label(resolve_class(classes, "男女"), "男女計") == "000"
    assert code_for_label(resolve_class(classes, "年齢"), "65歳以上") == "003"
    assert code_for_label(resolve_class(classes, "人口"), "総人口") == "001"


PREFECTURES = [
    ("01", "北海道"), ("02", "青森県"), ("03", "岩手県"), ("04", "宮城県"),
    ("05", "秋田県"), ("06", "山形県"), ("07", "福島県"), ("08", "茨城県"),
    ("09", "栃木県"), ("10", "群馬県"), ("11", "埼玉県"), ("12", "千葉県"),
    ("13", "東京都"), ("14", "神奈川県"), ("15", "新潟県"), ("16", "富山県"),
    ("17", "石川県"), ("18", "福井県"), ("19", "山梨県"), ("20", "長野県"),
    ("21", "岐阜県"), ("22", "静岡県"), ("23", "愛知県"), ("24", "三重県"),
    ("25", "滋賀県"), ("26", "京都府"), ("27", "大阪府"), ("28", "兵庫県"),
    ("29", "奈良県"), ("30", "和歌山県"), ("31", "鳥取県"), ("32", "島根県"),
    ("33", "岡山県"), ("34", "広島県"), ("35", "山口県"), ("36", "徳島県"),
    ("37", "香川県"), ("38", "愛媛県"), ("39", "高知県"), ("40", "福岡県"),
    ("41", "佐賀県"), ("42", "長崎県"), ("43", "熊本県"), ("44", "大分県"),
    ("45", "宮崎県"), ("46", "鹿児島県"), ("47", "沖縄県"),
]


def _build_workbook(path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "第3表"
    ws.cell(row=1, column=1, value="第３表 都道府県、年齢（３区分）、男女別人口－総人口")
    ws.cell(row=4, column=16, value="（単位 千人）")
    ws.cell(row=6, column=5, value="男 女 計")
    ws.cell(row=9, column=5, value="15歳未満")
    ws.cell(row=9, column=6, value="15～64歳")
    ws.cell(row=9, column=7, value="65歳以上")
    r = 13
    ws.cell(row=r, column=1, value="全国")
    for c, v in ((5, 100), (6, 600), (7, 300)):
        ws.cell(row=r, column=c, value=v)
    r += 1
    for code, name in PREFECTURES:
        ws.cell(row=r, column=2, value=code)
        ws.cell(row=r, column=3, value=name)
        ws.cell(row=r, column=5, value=100)   # 15歳未満
        ws.cell(row=r, column=6, value=600)   # 15～64歳
        ws.cell(row=r, column=7, value=300)   # 65歳以上
        r += 1
    wb.save(path)


def test_parse_age_group_table(tmp_path):
    xlsx = tmp_path / "05k2099-3.xlsx"
    _build_workbook(xlsx)
    table = StatFileTable(year=2099, url="https://example.invalid/05k2099-3.xlsx")
    rows = parse_age_group_table(xlsx, table)
    assert len(rows) == 94  # 47 prefectures x (total + elderly)
    tokyo_total = next(
        r for r in rows if r["region_code_estat"] == "13000" and r["age_group"] == "total"
    )
    assert tokyo_total["value_thousands"] == 1000  # 100 + 600 + 300
    tokyo_elderly = next(
        r
        for r in rows
        if r["region_code_estat"] == "13000" and r["age_group"] == "elderly_65plus"
    )
    assert tokyo_elderly["value_thousands"] == 300
    assert tokyo_total["source_id"] == "stat_file"
