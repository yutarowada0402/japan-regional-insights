import pytest

from src.processing.transforms import (
    aging_rate,
    map_age_group,
    normalize_prefecture_code,
    parse_year_from_time_name,
    population_change_rate,
    thousands_to_persons,
)


class TestNormalizePrefectureCode:
    def test_hokkaido(self):
        assert normalize_prefecture_code("01000") == "01"

    def test_okinawa(self):
        assert normalize_prefecture_code("47000") == "47"

    def test_national_total_is_none(self):
        assert normalize_prefecture_code("00000") is None

    @pytest.mark.parametrize("bad", ["1300", "48000", "13", "abcde", ""])
    def test_invalid_codes_raise(self, bad):
        with pytest.raises(ValueError):
            normalize_prefecture_code(bad)


class TestAgeGroupMapping:
    def test_total(self):
        assert map_age_group("総数") == "total"

    def test_elderly(self):
        assert map_age_group("65歳以上") == "elderly_65plus"

    def test_unknown_raises(self):
        with pytest.raises(ValueError):
            map_age_group("15歳未満")


class TestUnitsAndRates:
    def test_thousands_to_persons(self):
        assert thousands_to_persons(14010) == 14_010_000

    def test_change_rate_positive(self):
        assert population_change_rate(1050, 1000) == pytest.approx(5.0)

    def test_change_rate_negative(self):
        assert population_change_rate(980, 1000) == pytest.approx(-2.0)

    def test_change_rate_undefined(self):
        assert population_change_rate(1000, 0) is None
        assert population_change_rate(1000, None) is None

    def test_aging_rate(self):
        assert aging_rate(300, 1000) == pytest.approx(30.0)

    def test_aging_rate_undefined(self):
        assert aging_rate(300, 0) is None


class TestParseYear:
    def test_full_label(self):
        assert parse_year_from_time_name("2021年10月1日現在") == 2021

    def test_bare_year(self):
        assert parse_year_from_time_name("2016") == 2016

    def test_invalid(self):
        with pytest.raises(ValueError):
            parse_year_from_time_name("不明")
