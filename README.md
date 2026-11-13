# Japan Regional Insights

日本の都道府県別人口統計を分析・可視化するWebアプリケーションです。
政府のオープンデータ（総務省統計局「人口推計」）を使い、人口増減率ランキング、
人口推移、地域比較、高齢化率との相関をインタラクティブに確認できます。

データエンジニアリングのポートフォリオとして、Python によるデータ取得、
dbt + DuckDB によるデータモデリング（Medallion アーキテクチャ）、
GitHub Actions による CI/CD、Streamlit による可視化を一貫して実装しています。

## 機能（MVP）

1. **都道府県別 人口増減率ランキング** — 年度選択、増加/減少の色分け、棒グラフ+テーブル
2. **都道府県別 人口推移** — 折れ線グラフと年次増減率
3. **地域比較** — 最大3都道府県の人口推移と増減率を比較
4. **高齢化率 × 人口増減率の相関分析** — 散布図（地域名ホバー）と相関係数
   ※ 相関関係と因果関係は別物である旨の説明を画面上に明記しています
5. **コロプレスマップ**（追加機能）— 高齢化率・人口増減率・総人口を地図で表示
   境界データは国土数値情報（行政区域データ、国土交通省）を加工した
   `assets/japan-prefectures-{1,2}.geojson`（先行ブランチで作成された境界データを再利用し、
   座標の丸め・小島嶼の省略・2ファイル分割による軽量化を施したもの）

## アーキテクチャ

```
┌─────────────────┐   ┌──────────────────┐   ┌────────────────────┐   ┌────────────────┐
│  Sources        │   │  Bronze          │   │  Silver / Gold     │   │  App           │
│  人口推計        │──▶│  data/bronze/    │──▶│  dbt (dbt-duckdb)  │──▶│  Streamlit     │
│  ・e-Stat API    │   │  生データ(CSV)   │   │  data/silver/      │   │  app/          │
│  ・公式Excel     │   │  + 取得メタ情報  │   │  data/gold/        │   │  prefecture_   │
│   (フォールバック)│   │                  │   │  Parquet + CSV     │   │  year を読込   │
└─────────────────┘   └──────────────────┘   └────────────────────┘   └────────────────┘
        src/ingestion/                          dbt/models/               app/streamlit_app.py
```

- **Bronze**: API/Excel から取得した生データ（千人単位の原値）と出典情報を保持。再処理可能。
- **Silver**（dbt staging）: 都道府県コード統一（`01000` → `01`）、型変換、人単位への換算、重複排除。
- **Gold**（dbt marts）: 中心テーブル `fact_regional_indicator`（region_code × year × indicator_code）と、
  ダッシュボード向けの `gold_prefecture_year`（総人口、高齢者人口、高齢化率、人口増減率）。
- 指標: `total_population`（総人口）、`elderly_population`（65歳以上人口）を基礎指標とし、
  `population_change_rate`（前年比 %）と `aging_rate`（%）を Gold で算出します。

## データソース

| 項目 | 内容 |
|---|---|
| 統計名 | 人口推計（政府統計コード 00200524） |
| 提供機関 | 総務省統計局 |
| 対象 | 都道府県・年齢（3区分）・男女別人口（総人口）、各年10月1日現在 |
| 対象年度 | 2016〜2024年（47都道府県 × 9年） |
| 原単位 | 千人（パイプラインで人単位に換算） |
| 取得経路1（主） | e-Stat API: 統計表ID `0004021110`（2016〜2020）、`0003448225`（2021〜2024） |
| 取得経路2（予備） | 統計局サイトの公表 Excel（各年 第3表、2019・2021〜2024年分） |
| 関連表 | 年齢（5歳階級）表 `0003448237`（2020〜2024）の所在を getMetaInfo で確認済み（本MVPでは未使用） |

詳細な出典記録は [`data/source_manifest.csv`](data/source_manifest.csv) を参照してください。

注意点:
- 人口増減率はデータ開始年（2016年）については前年データが無いため算出されません（補完しません）。
- Excel 経路の総人口は年齢3区分の合計のため、公表総数と最大1千人程度の丸め差が生じます。

## ローカル実行手順

前提: Python 3.12+

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 1) データ取得（Bronze）
#    ESTAT_APP_ID があれば e-Stat API、無ければ公式Excelから取得します
export ESTAT_APP_ID=<your e-Stat application ID>   # 任意
python -m src.ingestion.download

# 2) dbt 変換 + Gold/Silver の Parquet・CSV 生成
python -m src.processing.build_dataset

# 3) アプリ起動
streamlit run app/streamlit_app.py
```

テスト:

```bash
pytest -q
ruff check src app tests
dbt build --project-dir dbt --profiles-dir dbt   # JRI_BRONZE_CSV / JRI_DUCKDB_PATH は build_dataset 経由が簡単です
```

## CI/CD（GitHub Actions）

- **CI**（`.github/workflows/ci.yml`）: Pull Request 時に ruff、pytest、dbt build（テスト用フィクスチャ使用）を実行。
- **データ更新**（`.github/workflows/data-update.yml`）: 月次スケジュール + 手動実行。
  取得 → Bronze → dbt 変換 → 検証 → Gold 生成を一時領域で行い、成功した場合のみ公開データを差し替えます。
  差分がある場合のみコミットします（`GITHUB_TOKEN` の push は他ワークフローを起動しないため無限ループになりません）。

### ESTAT_APP_ID について

- e-Stat API を使う場合のみ必要です。リポジトリの Settings → Secrets and variables → Actions に
  `ESTAT_APP_ID` を登録してください（ユーザーが自身のアプリケーションIDを登録する前提です）。
- 未登録の場合は自動的に公式 Excel 経路にフォールバックします。
- ローカルでも環境変数未設定なら Excel 経路で動作します。キーをコードやリポジトリに含めることはありません。

## Streamlit Community Cloud へのデプロイ

1. [Streamlit Community Cloud](https://share.streamlit.io/) で本リポジトリを選択。
2. Main file path に `app/streamlit_app.py` を指定して Deploy。
3. アプリはリポジトリ内の `data/gold/prefecture_year.parquet`（無ければ `.csv`）を読むため、
   追加のシークレット設定なしで動作します（データは data-update ワークフローがコミットしたものを使用）。

## ディレクトリ構成

```
├── app/streamlit_app.py        # Streamlit ダッシュボード
├── src/ingestion/              # データ取得（e-Stat API / 公式Excel）
├── src/processing/             # 変換ヘルパーとビルド統括
├── dbt/                        # dbt プロジェクト（staging / marts / seeds / tests）
├── data/
│   ├── bronze/                 # 生データ（CSV）
│   ├── silver/                 # Silver 層（Parquet + CSV）
│   ├── gold/                   # Gold 層（Parquet + CSV）※アプリの参照先
│   └── source_manifest.csv     # 出典マニフェスト
├── tests/                      # pytest（変換ロジック、パーサー、アプリ起動確認）
└── .github/workflows/          # CI / データ更新
```

## ライセンス

MIT License（`LICENSE` ファイル参照）。データの出典は「人口推計」（総務省統計局）です。
