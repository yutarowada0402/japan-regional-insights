"""Generate the static dashboard site for GitHub Pages (docs/index.html).

Reads the Gold dashboard table (CSV mirror) and the prefecture boundary
GeoJSON parts, and emits a single self-contained HTML page: data and
boundaries are embedded as JSON, charts are rendered client-side with
Plotly.js (CDN), and all filters (year / prefecture) work in the browser.

Run after the dataset build:
    python -m src.processing.build_dataset
    python -m src.processing.build_static_site [--data-dir data] [--out docs]
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PLOTLY_VERSION = "2.35.2"
PLOTLY_URL = f"https://cdn.plot.ly/plotly-{PLOTLY_VERSION}.min.js"

REPO_ROOT = Path(__file__).resolve().parents[2]

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Japan Regional Insights | 都道府県別 人口統計ダッシュボード</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
<script>window.Plotly || document.write('<script src="plotly.min.js"><\\/script>');</script>
<style>
  body { font-family: "Hiragino Kaku Gothic ProN", "Noto Sans JP", sans-serif;
         margin: 0; color: #1a1a2e; background: #f7f8fa; }
  main { max-width: 1100px; margin: 0 auto; padding: 24px 16px 48px; }
  h1 { font-size: 1.7rem; margin: 8px 0 2px; }
  h2 { font-size: 1.2rem; margin: 36px 0 8px; border-left: 4px solid #2e7d32; padding-left: 8px; }
  .sub { color: #555; margin: 0 0 16px; }
  .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
  .kpi { background: #fff; border: 1px solid #e0e3e8; border-radius: 8px; padding: 14px; }
  .kpi .label { color: #666; font-size: .82rem; }
  .kpi .value { font-size: 1.35rem; font-weight: 700; margin-top: 4px; }
  .kpi .delta { color: #2e7d32; font-size: .9rem; }
  section { background: #fff; border: 1px solid #e0e3e8; border-radius: 8px; padding: 16px; margin-top: 8px; }
  label { font-size: .9rem; margin-right: 6px; }
  select { font-size: .95rem; padding: 4px 6px; margin: 4px 8px 12px 0; }
  table { border-collapse: collapse; width: 100%; font-size: .9rem; }
  th, td { border-bottom: 1px solid #eceff3; padding: 5px 8px; text-align: right; }
  th:first-child, td:first-child { text-align: left; }
  .note { background: #fff8e1; border: 1px solid #ffe082; border-radius: 6px; padding: 10px 12px; font-size: .9rem; }
  footer { color: #666; font-size: .82rem; margin-top: 32px; }
  .chart { width: 100%; }
</style>
</head>
<body>
<main>
  <h1>Japan Regional Insights</h1>
  <p class="sub">都道府県別 人口統計ダッシュボード（人口推計・各年10月1日現在）</p>
  <div class="kpis" id="kpis"></div>

  <section>
    <h2>① 都道府県別 人口増減率ランキング</h2>
    <label for="rankYear">年度</label>
    <select id="rankYear"></select>
    <div id="rankChart" class="chart"></div>
    <div id="rankTable"></div>
  </section>

  <section>
    <h2>② 都道府県別 人口推移</h2>
    <label for="trendPref">都道府県</label>
    <select id="trendPref"></select>
    <div id="trendChart" class="chart"></div>
    <div id="trendTable"></div>
    <p class="sub">人口増減率は前年のデータがない年度（初年度・欠年の翌年）は空欄です。欠年の値は補完していません。</p>
  </section>

  <section>
    <h2>③ 地域比較（最大3都道府県）</h2>
    <label>都道府県A</label><select id="cmpA"></select>
    <label>都道府県B</label><select id="cmpB"></select>
    <label>都道府県C</label><select id="cmpC"></select>
    <div id="cmpChart" class="chart"></div>
    <div id="cmpRateChart" class="chart"></div>
    <div id="cmpTable"></div>
  </section>

  <section>
    <h2>④ 高齢化率と人口増減率の相関分析</h2>
    <label for="corrYear">年度</label>
    <select id="corrYear"></select>
    <p>相関係数（ピアソン）：<strong id="corrValue">-</strong></p>
    <div id="corrChart" class="chart"></div>
    <p class="note">注意：ここで示すのは相関関係であり、因果関係ではありません。
    高齢化率が高い地域で人口減少率が大きい傾向が見られても、「高齢化が人口減少の原因である」とは断定できません。
    若年層の流出など、双方に影響する別の要因が存在するためです。</p>
  </section>

  <section>
    <h2>⑤ コロプレスマップ</h2>
    <label for="mapYear">年度</label>
    <select id="mapYear"></select>
    <label for="mapMetric">指標</label>
    <select id="mapMetric">
      <option value="aging_rate">高齢化率（%）</option>
      <option value="population_change_rate">人口増減率（%）</option>
      <option value="total_population">総人口（人）</option>
    </select>
    <div id="mapChart" class="chart"></div>
    <p class="sub">境界データ：国土数値情報（行政区域データ、国土交通省）を加工して作成。</p>
  </section>

  <footer id="sourceNote"></footer>
</main>
<script>
const DATA = __DATA_JSON__;
const BOUNDARIES = __GEOJSON__;
const YEARS = [...new Set(DATA.map(d => d.year))].sort((a, b) => a - b);
const PREFS = [...new Map(DATA.map(d => [d.region_code, d.region_name])).entries()]
  .sort((a, b) => a[0].localeCompare(b[0])).map(([code, name]) => ({ code, name }));
const byYear = y => DATA.filter(d => d.year === y);
const byPref = code => DATA.filter(d => d.region_code === code).sort((a, b) => a.year - b.year);
const fmt = n => n == null ? "" : Math.round(n).toLocaleString("ja-JP");
const pct = n => n == null ? "" : n.toFixed(2);
const rateYears = YEARS.filter(y => byYear(y).some(d => d.population_change_rate != null));

function fillSelect(el, values, labels, selected) {
  el.innerHTML = "";
  values.forEach((v, i) => {
    const o = document.createElement("option");
    o.value = v; o.textContent = labels ? labels[i] : v;
    if (v === selected) o.selected = true;
    el.appendChild(o);
  });
}
function tableHtml(headers, rows) {
  return "<table><thead><tr>" + headers.map(h => `<th>${h}</th>`).join("") + "</tr></thead><tbody>"
    + rows.map(r => "<tr>" + r.map(c => `<td>${c}</td>`).join("") + "</tr>").join("") + "</tbody></table>";
}
function plot(id, traces, layout) {
  if (!window.Plotly) {
    document.getElementById(id).innerHTML =
      "<p class='sub'>グラフライブラリ（Plotly.js）を読み込めませんでした。ネットワーク接続を確認してください。</p>";
    return;
  }
  Plotly.newPlot(id, traces, layout, { responsive: true });
}
function pearson(xs, ys) {
  const n = xs.length, mx = xs.reduce((a, b) => a + b, 0) / n, my = ys.reduce((a, b) => a + b, 0) / n;
  let num = 0, dx = 0, dy = 0;
  for (let i = 0; i < n; i++) { num += (xs[i] - mx) * (ys[i] - my); dx += (xs[i] - mx) ** 2; dy += (ys[i] - my) ** 2; }
  return num / Math.sqrt(dx * dy);
}

function renderKpis() {
  const latest = YEARS[YEARS.length - 1], prev = byYear(latest - 1), cur = byYear(latest);
  const total = cur.reduce((s, d) => s + d.total_population, 0);
  const totalPrev = prev.reduce((s, d) => s + d.total_population, 0);
  const rate = (total - totalPrev) / totalPrev * 100;
  const withRate = cur.filter(d => d.population_change_rate != null);
  const topGrowth = withRate.reduce((a, b) => a.population_change_rate > b.population_change_rate ? a : b);
  const topAging = cur.reduce((a, b) => a.aging_rate > b.aging_rate ? a : b);
  const cards = [
    [`${latest}年 総人口（47都道府県計）`, `${(total / 1e8).toFixed(3)} 億人`, `${rate >= 0 ? "+" : ""}${rate.toFixed(2)}%（前年比）`],
    ["人口増減率 最高", topGrowth.region_name, `${topGrowth.population_change_rate >= 0 ? "+" : ""}${pct(topGrowth.population_change_rate)}%`],
    ["高齢化率 最高", topAging.region_name, `${topAging.aging_rate.toFixed(1)}%`],
    ["収録期間", `${YEARS[0]}〜${latest}年`, ""],
  ];
  document.getElementById("kpis").innerHTML = cards.map(c =>
    `<div class="kpi"><div class="label">${c[0]}</div><div class="value">${c[1]}</div><div class="delta">${c[2]}</div></div>`).join("");
}

function renderRanking() {
  const year = Number(document.getElementById("rankYear").value);
  const rows = byYear(year).filter(d => d.population_change_rate != null)
    .sort((a, b) => b.population_change_rate - a.population_change_rate);
  plot("rankChart", [{
    type: "bar", orientation: "h",
    x: rows.map(d => d.population_change_rate), y: rows.map(d => d.region_name),
    marker: { color: rows.map(d => d.population_change_rate >= 0 ? "#2e7d32" : "#c62828") },
  }], { height: 900, margin: { l: 90, r: 20, t: 10, b: 40 },
        xaxis: { title: "人口増減率（%）" }, yaxis: { autorange: "reversed" } });
  document.getElementById("rankTable").innerHTML = tableHtml(
    ["順位", "都道府県", "総人口（人）", "人口増減率（%）", "高齢化率（%）"],
    rows.map((d, i) => [i + 1, d.region_name, fmt(d.total_population), pct(d.population_change_rate), pct(d.aging_rate)]));
}

function renderTrend() {
  const code = document.getElementById("trendPref").value;
  const rows = byPref(code);
  plot("trendChart", [{
    type: "scatter", mode: "lines+markers",
    x: rows.map(d => d.year), y: rows.map(d => d.total_population),
  }], { margin: { l: 80, r: 20, t: 10, b: 40 },
        xaxis: { title: "年（10月1日現在）" }, yaxis: { title: "総人口（人）" } });
  document.getElementById("trendTable").innerHTML = tableHtml(
    ["年", "総人口（人）", "人口増減率（%）", "高齢化率（%）"],
    rows.map(d => [d.year, fmt(d.total_population), pct(d.population_change_rate), pct(d.aging_rate)]));
}

function renderComparison() {
  const codes = ["cmpA", "cmpB", "cmpC"].map(id => document.getElementById(id).value).filter(v => v);
  const traces = codes.map(code => {
    const rows = byPref(code);
    return { type: "scatter", mode: "lines+markers", name: rows[0].region_name,
             x: rows.map(d => d.year), y: rows.map(d => d.total_population) };
  });
  plot("cmpChart", traces, { margin: { l: 80, r: 20, t: 10, b: 40 },
    xaxis: { title: "年（10月1日現在）" }, yaxis: { title: "総人口（人）" } });
  const latest = YEARS[YEARS.length - 1];
  const rows = codes.map(code => byPref(code).find(d => d.year === latest)).filter(Boolean);
  plot("cmpRateChart", [{
    type: "bar", x: rows.map(d => d.region_name), y: rows.map(d => d.population_change_rate),
    marker: { color: "#2e7d32" },
  }], { margin: { l: 60, r: 20, t: 10, b: 40 }, yaxis: { title: `人口増減率（%、${latest}年）` } });
  document.getElementById("cmpTable").innerHTML = tableHtml(
    ["都道府県", `総人口（人、${latest}年）`, "人口増減率（%）", "高齢化率（%）"],
    rows.map(d => [d.region_name, fmt(d.total_population), pct(d.population_change_rate), pct(d.aging_rate)]));
}

function renderCorrelation() {
  const year = Number(document.getElementById("corrYear").value);
  const rows = byYear(year).filter(d => d.population_change_rate != null);
  const r = pearson(rows.map(d => d.aging_rate), rows.map(d => d.population_change_rate));
  document.getElementById("corrValue").textContent = r.toFixed(3);
  plot("corrChart", [{
    type: "scatter", mode: "markers", text: rows.map(d => d.region_name), hoverinfo: "text+x+y",
    x: rows.map(d => d.aging_rate), y: rows.map(d => d.population_change_rate),
    marker: { size: 9, color: "#1565c0" },
  }], { height: 520, margin: { l: 60, r: 20, t: 10, b: 50 },
        xaxis: { title: "高齢化率（%）" }, yaxis: { title: "人口増減率（%）" },
        shapes: [{ type: "line", x0: 0, x1: 1, xref: "paper", y0: 0, y1: 0,
                   line: { dash: "dot", color: "#888" } }] });
}

const COLOR_STOPS = {
  YlOrRd: ["#ffffcc", "#ffeda0", "#fed976", "#feb24c", "#fd8d3c", "#fc4e2a", "#e31a1c", "#bd0026", "#800026"],
  Viridis: ["#440154", "#46327e", "#365c8d", "#277f8e", "#1fa187", "#4ac16d", "#a0da39", "#fde725"],
};
function scaleColor(t, stops) {
  const x = Math.min(Math.max(t, 0), 1) * (stops.length - 1);
  const i = Math.floor(x), f = x - i;
  const c1 = stops[i], c2 = stops[Math.min(i + 1, stops.length - 1)];
  const rgb = [0, 1, 2].map(k => {
    const a = parseInt(c1.slice(1 + 2 * k, 3 + 2 * k), 16);
    const b = parseInt(c2.slice(1 + 2 * k, 3 + 2 * k), 16);
    return Math.round(a + (b - a) * f);
  });
  return `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
}

function renderMap() {
  // Draw prefecture polygons as filled cartesian scatters. This avoids
  // Plotly's geo engine, which fetches topojson from a CDN at runtime.
  const year = Number(document.getElementById("mapYear").value);
  const metric = document.getElementById("mapMetric").value;
  const rows = byYear(year).filter(d => d[metric] != null);
  const byCode = new Map(rows.map(d => [d.region_code, d]));
  const values = rows.map(d => d[metric]);
  const cmin = Math.min(...values), cmax = Math.max(...values);
  const stops = COLOR_STOPS[metric === "aging_rate" ? "YlOrRd" : "Viridis"];
  const label = { aging_rate: "高齢化率（%）", population_change_rate: "人口増減率（%）",
                  total_population: "総人口（人）" }[metric];
  const traces = [];
  for (const feature of BOUNDARIES.features) {
    const code = feature.properties.PREF_CODE;
    const row = byCode.get(code);
    if (!row) continue;
    const t = cmax > cmin ? (row[metric] - cmin) / (cmax - cmin) : 0.5;
    const fill = scaleColor(t, stops);
    const geom = feature.geometry;
    const polys = geom.type === "Polygon" ? [geom.coordinates] : geom.coordinates;
    for (const poly of polys) {
      const ring = poly[0];
      traces.push({
        type: "scatter", mode: "lines", fill: "toself", fillcolor: fill,
        line: { color: "#ffffff", width: 0.5 }, hoveron: "fills",
        text: `${row.region_name}<br>${label}: ${metric === "total_population" ? fmt(row[metric]) : pct(row[metric])}`,
        hoverinfo: "text", showlegend: false,
        x: ring.map(pt => pt[0]), y: ring.map(pt => pt[1]),
      });
    }
  }
  traces.push({  // dummy trace to render the colorbar
    type: "scatter", mode: "markers", x: [null], y: [null], showlegend: false, hoverinfo: "skip",
    marker: { colorscale: stops.map((c, i) => [i / (stops.length - 1), c]),
              cmin, cmax, color: [cmin], size: 0, showscale: true,
              colorbar: { title: metric === "total_population" ? "人" : "%" } },
  });
  plot("mapChart", traces, {
    height: 640, margin: { l: 0, r: 0, t: 8, b: 0 },
    xaxis: { visible: false }, yaxis: { visible: false, scaleanchor: "x", scaleratio: 1.22 },
  });
}

function init() {
  renderKpis();
  const latestRate = rateYears[rateYears.length - 1];
  fillSelect(document.getElementById("rankYear"), rateYears, rateYears.map(y => `${y}年`), latestRate);
  fillSelect(document.getElementById("corrYear"), rateYears, rateYears.map(y => `${y}年`), latestRate);
  fillSelect(document.getElementById("mapYear"), YEARS, YEARS.map(y => `${y}年`), YEARS[YEARS.length - 1]);
  const tokyo = PREFS.find(p => p.name === "東京都");
  fillSelect(document.getElementById("trendPref"), PREFS.map(p => p.code), PREFS.map(p => p.name), tokyo.code);
  const defaults = ["東京都", "大阪府", "秋田県"].map(n => PREFS.find(p => p.name === n).code);
  ["cmpA", "cmpB", "cmpC"].forEach((id, i) => {
    const el = document.getElementById(id);
    fillSelect(el, ["", ...PREFS.map(p => p.code)], ["（なし）", ...PREFS.map(p => p.name)], defaults[i]);
  });
  document.getElementById("rankYear").addEventListener("change", renderRanking);
  document.getElementById("trendPref").addEventListener("change", renderTrend);
  ["cmpA", "cmpB", "cmpC"].forEach(id => document.getElementById(id).addEventListener("change", renderComparison));
  document.getElementById("corrYear").addEventListener("change", renderCorrelation);
  document.getElementById("mapYear").addEventListener("change", renderMap);
  document.getElementById("mapMetric").addEventListener("change", renderMap);
  renderRanking(); renderTrend(); renderComparison(); renderCorrelation(); renderMap();
  const updated = DATA.reduce((a, d) => d.updated_at > a ? d.updated_at : a, "");
  document.getElementById("sourceNote").textContent =
    `出典：総務省統計局「人口推計」（各年10月1日現在、都道府県・年齢3区分別人口）／ e-Stat API（統計表ID: 0004021110、0003448225）。データ更新日時：${updated}。人口は千人単位で公表された値を人単位に換算しています。`;
}
document.addEventListener("DOMContentLoaded", init);
</script>
</body>
</html>
"""


def ensure_plotly_js(out_dir: Path) -> None:
    """Vendor plotly.min.js next to index.html as an offline fallback.

    The page loads Plotly from the CDN first and falls back to this local
    copy. Download failure is not fatal (CDN may still work for viewers).
    """
    dest = out_dir / "plotly.min.js"
    if dest.exists() and dest.stat().st_size > 1_000_000:
        logger.info("plotly.min.js already present (%s)", dest)
        return
    try:
        logger.info("Downloading Plotly.js from %s", PLOTLY_URL)
        with urllib.request.urlopen(PLOTLY_URL, timeout=60) as response:
            dest.write_bytes(response.read())
        logger.info("Wrote %s (%.1f KiB)", dest, dest.stat().st_size / 1024)
    except Exception as exc:  # noqa: BLE001 - best effort by design
        logger.warning("Could not vendor Plotly.js (%s); CDN link remains", exc)


def load_gold_rows(gold_csv: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with gold_csv.open(encoding="utf-8", newline="") as fh:
        for raw in csv.DictReader(fh):
            rows.append(
                {
                    "region_code": str(raw["region_code"]).zfill(2),
                    "region_name": raw["region_name"],
                    "year": int(raw["year"]),
                    "total_population": float(raw["total_population"]),
                    "elderly_population": float(raw["elderly_population"]),
                    "aging_rate": float(raw["aging_rate"]),
                    "population_change_rate": (
                        float(raw["population_change_rate"])
                        if raw["population_change_rate"] not in ("", None)
                        else None
                    ),
                    "updated_at": raw["updated_at"],
                }
            )
    return rows


def load_boundaries(boundaries_dir: Path) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for path in sorted(boundaries_dir.glob("japan-prefectures-*.geojson")):
        features.extend(json.loads(path.read_text(encoding="utf-8"))["features"])
    if not features:
        raise FileNotFoundError(f"No boundary GeoJSON under {boundaries_dir}")
    return {"type": "FeatureCollection", "features": features}


def build_site(data_dir: Path, assets_dir: Path, out_dir: Path) -> Path:
    gold_csv = data_dir / "gold" / "prefecture_year.csv"
    if not gold_csv.exists():
        raise FileNotFoundError(
            f"Gold CSV not found: {gold_csv} (run build_dataset first)"
        )
    rows = load_gold_rows(gold_csv)
    boundaries = load_boundaries(assets_dir / "boundaries")
    html = HTML_TEMPLATE.replace(
        "__DATA_JSON__", json.dumps(rows, ensure_ascii=False)
    ).replace("__GEOJSON__", json.dumps(boundaries, ensure_ascii=False))
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "index.html"
    dest.write_text(html, encoding="utf-8")
    ensure_plotly_js(out_dir)
    logger.info(
        "Wrote %s (%d rows, %d boundary features, %.1f KiB)",
        dest,
        len(rows),
        len(boundaries["features"]),
        dest.stat().st_size / 1024,
    )
    return dest


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--assets-dir", type=Path, default=REPO_ROOT / "assets")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "docs")
    args = parser.parse_args()
    build_site(args.data_dir, args.assets_dir, args.out)


if __name__ == "__main__":
    main()
