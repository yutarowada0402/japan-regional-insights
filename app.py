"""Streamlit dashboard for observed e-Stat data."""

import os
from pathlib import Path

import duckdb
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Japan Regional Insights", layout="wide")
st.title("Japan Regional Insights")
st.caption("e-Stat 公開統計に基づく都道府県別の人口・高齢化分析")
db_path = Path(os.getenv("DATABASE_PATH", "data/regional_insights.duckdb"))
if not db_path.exists():
    st.warning("データベースがありません。READMEの手順でe-Statデータを取得してください。")
    st.stop()
with duckdb.connect(str(db_path), read_only=True) as con:
    frame = con.execute("SELECT * FROM gold_regional_metrics ORDER BY year, prefecture").df()
if frame.empty:
    st.info("対象データがありません。ETL設定と統計表IDを確認してください。")
    st.stop()
years = sorted(frame.year.dropna().astype(int).unique())
year = st.select_slider("表示年", options=years, value=years[-1])
current = frame[frame.year == year]
left, right = st.columns(2)
with left:
    pop = current.dropna(subset=["population"])
    if not pop.empty:
        st.plotly_chart(px.bar(pop.sort_values("population", ascending=False), x="prefecture", y="population", title="都道府県別人口", labels={"prefecture": "都道府県", "population": "人口"}), use_container_width=True)
with right:
    aging = current.dropna(subset=["aging_rate"])
    if not aging.empty:
        st.plotly_chart(px.bar(aging.sort_values("aging_rate", ascending=False), x="prefecture", y="aging_rate", title="都道府県別高齢化率", labels={"prefecture": "都道府県", "aging_rate": "高齢化率"}), use_container_width=True)
if frame.population.notna().any():
    selected = st.multiselect("比較する都道府県", sorted(frame.prefecture.unique()), default=list(current.nlargest(5, "population").prefecture))
    compare = frame[frame.prefecture.isin(selected)].dropna(subset=["population"])
    st.plotly_chart(px.line(compare, x="year", y="population", color="prefecture", markers=True, title="人口推移", labels={"year": "年", "population": "人口", "prefecture": "都道府県"}), use_container_width=True)
st.subheader("データ情報")
st.write(f"年次: {int(frame.year.min())}–{int(frame.year.max())} / 出典: {', '.join(frame.source.dropna().unique())} / 統計表ID: {', '.join(frame.stats_data_id.dropna().unique())} / 統計表更新日: {', '.join(frame.source_updated_date.dropna().unique())}")
st.caption("人口の単位は統計表記載の千人、高齢化率は65歳以上人口÷総人口です。データ取得時刻: " + ', '.join(frame.updated_at.dropna().unique()))
