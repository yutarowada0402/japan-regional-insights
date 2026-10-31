from japan_regional_insights.etl import _flatten


def test_flatten_keeps_prefecture_metadata_and_values():
    payload = {
        "GET_STATS_DATA": {
            "PARAMETER": {"STATS_DATA_ID": "table-1"},
            "STATISTICAL_DATA": {
                "CLASS_INF": {"CLASS_OBJ": [
                    {"@id": "area", "CLASS": [{"@code": "13000", "@name": "東京都"}]},
                    {"@id": "time", "CLASS": [{"@code": "2001", "@name": "2020年10月1日現在"}]},
                ]},
                "DATA_INF": {"VALUE": [{"@area": "13000", "@time": "2001", "@cat01": "000", "@cat02": "000", "@cat03": "001", "@unit": "千人", "$": "14000"}, {"@area": "13000", "@time": "2001", "@cat01": "000", "@cat02": "003", "@cat03": "001", "@unit": "千人", "$": "4000"}]},
            },
        }
    }
    rows = _flatten(payload, "population")
    assert len(rows) == 2
    assert rows[0]["prefecture"] == "東京都"
    assert rows[0]["year"] == 2020
    population = next(row for row in rows if row["indicator"] == "population")
    aging_rate = next(row for row in rows if row["indicator"] == "aging_rate")
    assert population["year"] == 2020
    assert population["value"] == 14000
    assert population["stats_data_id"] == "table-1"
    assert aging_rate["value"] == 4000 / 14000 * 100
    assert aging_rate["unit"] == "%"


def test_flatten_drops_aggregate_area():
    payload = {
        "GET_STATS_DATA": {"STATISTICAL_DATA": {
            "CLASS_INF": {"CLASS_OBJ": [{"@id": "time", "CLASS": [{"@code": "2001", "@name": "2020年"}]}]},
            "DATA_INF": {"VALUE": [{"@area": "00000", "@time": "2001", "@cat01": "000", "@cat02": "000", "@cat03": "001", "$": "1"}]},
        }}
    }
    assert _flatten(payload, "population") == []
