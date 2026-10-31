from japan_regional_insights.etl import _flatten


def test_flatten_keeps_prefecture_metadata_and_values():
    payload = {
        "GET_STATS_DATA": {
            "PARAMETER": {"STATS_DATA_ID": "table-1"},
            "STATISTICAL_DATA": {
                "CLASS_INF": {"CLASS_OBJ": [{"@id": "area", "CLASS": [{"@code": "13000", "@name": "東京都"}]}]},
                "DATA_INF": {"VALUE": [{"@area": "13000", "@time": "2020", "@unit": "千人", "$": "14000"}]},
            },
        }
    }
    rows = _flatten(payload, "population")
    assert len(rows) == 1
    assert rows[0]["prefecture"] == "東京都"
    assert rows[0]["year"] == 2020
    assert rows[0]["value"] == 14000
    assert rows[0]["stats_data_id"] == "table-1"


def test_flatten_drops_aggregate_area():
    payload = {
        "GET_STATS_DATA": {"STATISTICAL_DATA": {
            "CLASS_INF": {"CLASS_OBJ": []},
            "DATA_INF": {"VALUE": [{"@area": "00000", "@time": "2020", "$": "1"}]},
        }}
    }
    assert _flatten(payload, "population") == []
