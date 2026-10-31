"""Streamlit dashboard for observed e-Stat data."""

import gzip
import json
import os
from pathlib import Path

import duckdb
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Japan Regional Insights", layout="wide")
st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1440px;}
.hero {padding: 1.2rem 0 1.1rem; border-bottom: 1px solid rgba(125,145,175,.2); margin-bottom: 1.2rem;}
.eyebrow {font-size:.74rem; letter-spacing:.18em; color:#76d6c2; font-weight:700;}
.hero h1 {font-size:2.25rem; letter-spacing:-.04em; margin:.25rem 0 .2rem;}
.hero p {color:#9caec2; margin:0;}
</style>
<div class="hero"><div class="eyebrow">JAPAN · REGIONAL DATA ATLAS</div>
<h1>日本の地域を、地図で読む。</h1><p>人口と高齢化の現在地、そしてその変化。</p></div>
""", unsafe_allow_html=True)
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
controls = st.columns([1, 2, 2])
with controls[0]:
    year = st.selectbox("基準年", options=years, index=len(years) - 1, format_func=lambda y: f"{y}年")
with controls[1]:
    metric = st.radio("地図に表示", ["高齢化率", "人口"], horizontal=True, label_visibility="visible")
metric_col = "aging_rate" if metric == "高齢化率" else "population"
metric_unit = "%" if metric == "高齢化率" else "千人"
palette = "YlOrRd" if metric == "高齢化率" else "Teal"
current = frame[frame.year == year]
mapped = current.dropna(subset=[metric_col]).copy()
mapped["map_code"] = mapped.prefecture_code.astype(str).str[:2]
if not mapped.empty:
    low = mapped.loc[mapped[metric_col].idxmin()]
    high = mapped.loc[mapped[metric_col].idxmax()]
    avg = mapped[metric_col].mean()
    cards = st.columns(4)
    cards[0].metric(f"{year}年 · 全国平均", f"{avg:,.1f}{metric_unit}")
    cards[1].metric("最も高い地域", f"{high.prefecture}", f"{high[metric_col]:,.1f}{metric_unit}")
    cards[2].metric("最も低い地域", f"{low.prefecture}", f"{low[metric_col]:,.1f}{metric_unit}")
    cards[3].metric("対象地域", f"{mapped.prefecture.nunique()} / 47", "都道府県")

    @st.cache_data
    def load_boundaries():
        with gzip.open("assets/japan-prefectures.geojson.gz", "rt", encoding="utf-8") as source:
            return json.load(source)

    boundaries = load_boundaries()
    figure = go.Figure(go.Choropleth(
        geojson=boundaries,
        featureidkey="properties.PREF_CODE",
        locations=mapped.map_code,
        z=mapped[metric_col],
        text=mapped.prefecture,
        customdata=mapped[[metric_col, "population", "aging_rate"]].to_numpy(),
        colorscale=palette,
        marker={"line": {"color": "#f1f5f9", "width": 0.65}},
        colorbar={"title": metric_unit, "thickness": 15, "len": .72, "outlinewidth": 0},
        hovertemplate="<b>%{text}</b><br>" + metric + ": %{z:,.1f}" + metric_unit
        + "<br>人口: %{customdata[1]:,.0f} 千人<br>高齢化率: %{customdata[2]:.1f}%<extra></extra>",
    ))
    figure.update_geos(fitbounds="locations", visible=False, projection_type="mercator", bgcolor="rgba(0,0,0,0)")
    figure.update_layout(
        height=650, margin={"l": 0, "r": 0, "t": 8, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#d8e3ef", "family": "sans-serif"},
        coloraxis_colorbar={"outlinewidth": 0},
    )
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
else:
    st.info(f"{year}年の{metric}データはありません。")

st.markdown("#### 地域ごとの変化")
if frame.population.notna().any():
    selected = st.multiselect("比較する都道府県", sorted(frame.prefecture.unique()), default=list(current.nlargest(5, "population").prefecture))
    compare = frame[frame.prefecture.isin(selected)].dropna(subset=["population"])
    st.plotly_chart(px.line(compare, x="year", y="population", color="prefecture", markers=True, labels={"year": "年", "population": "人口（千人）", "prefecture": "都道府県"}), width="stretch")
with st.expander("データについて"):
    st.write(f"出典: {', '.join(frame.source.dropna().unique())} · 統計表ID: {', '.join(frame.stats_data_id.dropna().unique())}")
    st.write(f"対象年: {int(frame.year.min())}–{int(frame.year.max())} · 統計表更新日: {', '.join(frame.source_updated_date.dropna().unique())}")
    st.caption("高齢化率は65歳以上人口÷総人口。境界データ: 国土数値情報（行政区域データ、国土交通省）を加工。")
