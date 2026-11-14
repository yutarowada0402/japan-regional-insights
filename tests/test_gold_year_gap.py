"""Regression coverage for calendar-year comparisons in the actual dbt model."""

from pathlib import Path

import duckdb
import pytest
from jinja2 import Template


def test_gold_requires_previous_calendar_year():
    root = Path(__file__).resolve().parents[1]
    model = root / "dbt/models/marts/gold_prefecture_year.sql"
    sql = Template(model.read_text()).render(ref=lambda name: name)
    with duckdb.connect() as con:
        # Use repository fixture values, omitting 2023 only for Hokkaido.
        fixture = root / "tests/fixtures/bronze_sample.csv"
        con.execute(
            """
            create table fact_regional_indicator as
            select substr(region_code_estat, 1, 2) as region_code, year,
                case age_group when 'total' then 'total_population'
                    else 'elderly_population' end as indicator_code,
                value_thousands * 1000 as value, source_id,
                retrieved_at as updated_at
            from read_csv(?, types = {'region_code_estat': 'VARCHAR'})
            where not (region_code_estat = '01000' and year = 2023)
            """,
            [str(fixture)],
        )
        con.execute(
            "create table dim_region as select distinct region_code, "
            "region_code as region_name from fact_regional_indicator"
        )
        result = con.execute(sql)
        columns = [column[0] for column in result.description]
        rows = {
            (row["region_code"], row["year"]): row
            for values in result.fetchall()
            for row in [dict(zip(columns, values, strict=True))]
        }
        # Neither the first observation nor a gap can produce a yearly rate.
        assert rows[("01", 2022)]["population_change_rate"] is None
        assert rows[("01", 2024)]["prev_year_population"] is None
        assert rows[("01", 2024)]["population_change_rate"] is None
        # Another region's consecutive years still produce the expected rate.
        expected = round(
            100 * (rows[("13", 2024)]["total_population"]
                   / rows[("13", 2023)]["total_population"] - 1),
            3,
        )
        assert rows[("13", 2024)]["population_change_rate"] == pytest.approx(expected)
