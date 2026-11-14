"""Japan Regional Insights - 都道府県別人口統計ダッシュボード.

人口推計（総務省統計局）の都道府県別データを可視化する。
データは data/gold/prefecture_year.parquet（優先）または .csv を読み込む。
パイプライン未実行でデータが無い場合は、その旨と実行方法を表示する。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLD_DIR = REPO_ROOT / "data" / "gold"
BOUNDARIES_DIR = REPO_ROOT / "assets" / "boundaries"

st.set_page_config(page_title="Japan Regional Insights", layout="wide")


@st.cache_data
def load_gold() -> pd.DataFrame:
    """Load the Gold dashboard table (Parquet preferred, CSV fallback)."""
    parquet_path = GOLD_DIR / "prefecture_year.parquet"
    csv_path = GOLD_DIR / "prefecture_year.csv"
    if parquet_path.exists():
        df = pd.read_parquet(parquet_path)
    elif csv_path.exists():
        df = pd.read_csv(csv_path)
    else:
        return pd.DataFrame()
    df["region_code"] = df["region_code"].astype(str).str.zfill(2)
    return df.sort_values(["region_code", "year"]).reset_index(drop=True)


@st.cache_data
def load_boundaries() -> dict:
    """Prefecture boundaries (国土数値情報 行政区域データを加工).

    The boundary data is shipped as two GeoJSON files (split for size);
    their features are merged here.
    """
    features: list[dict] = []
    for path in sorted(BOUNDARIES_DIR.glob("japan-prefectures-*.geojson")):
        features.extend(json.loads(path.read_text(encoding="utf-8"))["features"])
    if not features:
        return {}
    return {"type": "FeatureCollection", "features": features}


def show_map(df: pd.DataFrame) -> None:
    st.subheader("⑤ コロプレスマップ")
    boundaries = load_boundaries()
    if not boundaries:
        st.info("境界データ（assets/boundaries/japan-prefectures-*.geojson）がありません。")
        return
    metric_labels = {
        "aging_rate": "高齢化率（%）",
        "population_change_rate": "人口増減率（%）",
        "total_population": "総人口（人）",
    }
    metric = st.radio(
        "表示する指標",
        list(metric_labels),
        format_func=lambda k: metric_labels[k],
        horizontal=True,
        key="map_metric",
    )
    years = sorted(df["year"].unique())
    if metric == "population_change_rate":
        years = [
            y for y in years if df[df["year"] == y]["population_change_rate"].notna().any()
        ]
    year = st.selectbox("年度", years, index=len(years) - 1, key="map_year")
    data = df[df["year"] == year].dropna(subset=[metric])
    # Draw prefecture polygons as filled cartesian scatters instead of
    # Plotly's geo engine (which fetches topojson from a CDN at runtime).
    import plotly.graph_objects as go
    from plotly.colors import sample_colorscale

    scale = "YlOrRd" if metric == "aging_rate" else "Viridis"
    cmin, cmax = float(data[metric].min()), float(data[metric].max())
    by_code = data.set_index("region_code")
    fig = go.Figure()
    for feature in boundaries["features"]:
        code = feature["properties"]["PREF_CODE"]
        if code not in by_code.index:
            continue
        row = by_code.loc[code]
        t = (float(row[metric]) - cmin) / (cmax - cmin) if cmax > cmin else 0.5
        fill = sample_colorscale(scale, [t])[0]
        geom = feature["geometry"]
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        for poly in polys:
            ring = poly[0]
            fig.add_trace(
                go.Scatter(
                    x=[pt[0] for pt in ring],
                    y=[pt[1] for pt in ring],
                    mode="lines",
                    fill="toself",
                    fillcolor=fill,
                    line={"color": "#ffffff", "width": 0.5},
                    hoveron="fills",
                    text=f"{row['region_name']}<br>{metric_labels[metric]}: {row[metric]:,.2f}",
                    hoverinfo="text",
                    showlegend=False,
                )
            )
    fig.add_trace(
        go.Scatter(
            x=[None],
            y=[None],
            mode="markers",
            marker={
                "colorscale": scale,
                "cmin": cmin,
                "cmax": cmax,
                "color": [cmin],
                "size": 0,
                "showscale": True,
                "colorbar": {"title": "人" if metric == "total_population" else "%"},
            },
            hoverinfo="skip",
            showlegend=False,
        )
    )
    fig.update_layout(
        height=640,
        margin={"l": 0, "r": 0, "t": 8, "b": 0},
        xaxis={"visible": False},
        yaxis={"visible": False, "scaleanchor": "x", "scaleratio": 1.22},
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("境界データ：国土数値情報（行政区域データ、国土交通省）を加工して作成。")


def show_kpis(df: pd.DataFrame, latest_year: int) -> None:
    latest = df[df["year"] == latest_year]
    prev = df[df["year"] == latest_year - 1]
    national_now = latest["total_population"].sum()
    national_prev = prev["total_population"].sum()
    national_rate = (
        (national_now - national_prev) / national_prev * 100
        if national_prev
        else float("nan")
    )
    top_growth = latest.dropna(subset=["population_change_rate"]).nlargest(
        1, "population_change_rate"
    )
    top_aging = latest.nlargest(1, "aging_rate")
    cols = st.columns(4)
    cols[0].metric(
        f"{latest_year}年 総人口（47都道府県計）",
        f"{national_now / 1e8:.3f} 億人",
        f"{national_rate:+.2f}% (前年比)",
    )
    if not top_growth.empty:
        row = top_growth.iloc[0]
        cols[1].metric(
            "人口増減率 最高",
            row["region_name"],
            f"{row['population_change_rate']:+.2f}%",
        )
    if not top_aging.empty:
        row = top_aging.iloc[0]
        cols[2].metric("高齢化率 最高", row["region_name"], f"{row['aging_rate']:.1f}%")
    cols[3].metric("収録期間", f"{int(df['year'].min())}〜{int(df['year'].max())}年")


def show_ranking(df: pd.DataFrame) -> None:
    st.subheader("① 都道府県別 人口増減率ランキング")
    years = sorted(df["year"].unique())
    rate_years = [y for y in years if df[df["year"] == y]["population_change_rate"].notna().any()]
    year = st.selectbox("年度", rate_years, index=len(rate_years) - 1, key="rank_year")
    data = (
        df[df["year"] == year]
        .dropna(subset=["population_change_rate"])
        .sort_values("population_change_rate", ascending=False)
        .reset_index(drop=True)
    )
    data["順位"] = data.index + 1
    data["区分"] = data["population_change_rate"].apply(
        lambda v: "増加" if v >= 0 else "減少"
    )
    fig = px.bar(
        data,
        x="population_change_rate",
        y="region_name",
        color="区分",
        color_discrete_map={"増加": "#2e7d32", "減少": "#c62828"},
        labels={"population_change_rate": "人口増減率（%）", "region_name": "都道府県"},
        height=900,
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(
        data[["順位", "region_name", "total_population", "population_change_rate", "aging_rate"]]
        .rename(
            columns={
                "region_name": "都道府県",
                "total_population": "総人口（人）",
                "population_change_rate": "人口増減率（%）",
                "aging_rate": "高齢化率（%）",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )


def show_trend(df: pd.DataFrame) -> None:
    st.subheader("② 都道府県別 人口推移")
    names = sorted(df["region_name"].unique())
    name = st.selectbox("都道府県", names, index=names.index("東京都"), key="trend_pref")
    data = df[df["region_name"] == name]
    fig = px.line(
        data,
        x="year",
        y="total_population",
        markers=True,
        labels={"year": "年（10月1日現在）", "total_population": "総人口（人）"},
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(
        data[["year", "total_population", "population_change_rate", "aging_rate"]].rename(
            columns={
                "year": "年",
                "total_population": "総人口（人）",
                "population_change_rate": "人口増減率（%）",
                "aging_rate": "高齢化率（%）",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )
    st.caption("人口増減率は初年度（データ開始年）については前年データが無いため空欄です。")


def show_comparison(df: pd.DataFrame) -> None:
    st.subheader("③ 地域比較（最大3都道府県）")
    names = sorted(df["region_name"].unique())
    selected = st.multiselect(
        "比較する都道府県",
        names,
        default=["東京都", "大阪府", "秋田県"],
        max_selections=3,
        key="cmp_prefs",
    )
    if not selected:
        st.info("都道府県を1つ以上選択してください。")
        return
    data = df[df["region_name"].isin(selected)]
    fig = px.line(
        data,
        x="year",
        y="total_population",
        color="region_name",
        markers=True,
        labels={
            "year": "年（10月1日現在）",
            "total_population": "総人口（人）",
            "region_name": "都道府県",
        },
    )
    st.plotly_chart(fig, use_container_width=True)
    latest_year = int(df["year"].max())
    latest = data[data["year"] == latest_year].sort_values(
        "population_change_rate", ascending=False
    )
    fig2 = px.bar(
        latest,
        x="region_name",
        y="population_change_rate",
        color="region_name",
        labels={
            "region_name": "都道府県",
            "population_change_rate": f"人口増減率（%、{latest_year}年）",
        },
    )
    st.plotly_chart(fig2, use_container_width=True)
    st.dataframe(
        latest[
            ["region_name", "total_population", "population_change_rate", "aging_rate"]
        ].rename(
            columns={
                "region_name": "都道府県",
                "total_population": f"総人口（人、{latest_year}年）",
                "population_change_rate": "人口増減率（%）",
                "aging_rate": "高齢化率（%）",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )


def show_correlation(df: pd.DataFrame) -> None:
    st.subheader("④ 高齢化率と人口増減率の相関分析")
    years = sorted(df["year"].unique())
    rate_years = [y for y in years if df[df["year"] == y]["population_change_rate"].notna().any()]
    year = st.selectbox("年度", rate_years, index=len(rate_years) - 1, key="corr_year")
    data = df[df["year"] == year].dropna(subset=["population_change_rate"])
    corr = data["aging_rate"].corr(data["population_change_rate"])
    st.metric("相関係数（ピアソン）", f"{corr:.3f}")
    fig = px.scatter(
        data,
        x="aging_rate",
        y="population_change_rate",
        hover_name="region_name",
        labels={
            "aging_rate": "高齢化率（%）",
            "population_change_rate": "人口増減率（%）",
        },
        height=520,
    )
    fig.add_hline(y=0, line_dash="dot")
    st.plotly_chart(fig, use_container_width=True)
    st.warning(
        "注意：ここで示すのは相関関係であり、因果関係ではありません。"
        "高齢化率が高い地域で人口減少率が大きい傾向が見られても、"
        "「高齢化が人口減少の原因である」とは断定できません。"
        "若年層の流出など、双方に影響する別の要因が存在するためです。"
    )


def main() -> None:
    st.title("Japan Regional Insights")
    st.caption("都道府県別 人口統計ダッシュボード")
    with st.spinner("データを読み込んでいます…"):
        df = load_gold()
    if df.empty:
        st.error(
            "Goldデータが見つかりません。先にデータパイプラインを実行してください："
            "`python -m src.ingestion.download` → `python -m src.processing.build_dataset`"
        )
        st.stop()

    latest_year = int(df["year"].max())
    show_kpis(df, latest_year)

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["① 増減率ランキング", "② 人口推移", "③ 地域比較", "④ 高齢化率との相関", "⑤ 地図"]
    )
    with tab1:
        show_ranking(df)
    with tab2:
        show_trend(df)
    with tab3:
        show_comparison(df)
    with tab4:
        show_correlation(df)
    with tab5:
        show_map(df)

    updated = pd.to_datetime(df["updated_at"]).max()
    st.divider()
    st.caption(
        "出典：総務省統計局「人口推計」（各年10月1日現在、都道府県・年齢3区分別人口）"
        "／ e-Stat API（統計表ID: 0004021110、0003448225）。"
        f"データ更新日時：{updated}。"
        "人口は千人単位で公表された値を人単位に換算しています。"
    )


main()
