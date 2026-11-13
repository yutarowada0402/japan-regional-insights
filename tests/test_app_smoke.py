"""Smoke test: the Streamlit app starts and renders without exceptions
against the committed Gold CSV (test data path used by CI as well)."""

from pathlib import Path

import pytest

streamlit_testing = pytest.importorskip("streamlit.testing.v1")

APP_PATH = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"


def test_app_runs_without_exception():
    at = streamlit_testing.AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    assert not at.exception, f"App raised: {at.exception}"
    assert at.title[0].value == "Japan Regional Insights"
