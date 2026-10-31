# Japan Regional Insights

e-Statの公開統計をDuckDBに取り込み、都道府県別人口・高齢化・地域差を探索するStreamlit MVPです。取得値をダミーで補完しません。統計表IDとAPIキーが未設定、またはAPIに対象指標がなければ、該当値は表示されません。

## セットアップ

1. Python 3.11以上を用意し、`python -m venv .venv && source .venv/bin/activate && pip install -e .[dev]` を実行します。
2. e-Stat API利用登録を行い、アプリケーションIDを取得します（[API利用ガイド](https://www.e-stat.go.jp/api/api-dev/how_to_use)）。`.env.example`を`.env`にコピーし、`ESTAT_APP_ID`を設定します。
3. `.env.example`の統計表ID `0003448225` は、e-Stat「人口推計」表011「都道府県，年齢（3区分），男女別人口－総人口，日本人人口」です。人口総数と65歳以上人口が同じ表にあることを確認し、高齢化率を65歳以上人口÷総人口×100で算出します。
4. `set -a; source .env; set +a; python -m japan_regional_insights.etl` で実データを取得します。
5. `streamlit run app.py` でダッシュボードを起動します。

## アーキテクチャ

```text
e-Stat API v3 JSON -> data/bronze/*.json (原応答)
                   -> DuckDB bronze_observations (受信値)
                   -> silver_observations (型整備・欠損除外・重複排除)
                   -> gold_regional_metrics (都道府県×年次の分析テーブル)
                   -> Streamlit / Plotly
```

ETLは`src/japan_regional_insights/etl.py`、dbtのGoldモデルは`models/`にあります。各レコードに統計表ID、出典、単位、取得時刻を保持します。e-Stat API v3.0は`/rest/3.0/app/json/getStatsData`にGETで`appId`と`statsDataId`を渡す方式です（[公式仕様](https://www.e-stat.go.jp/api/api-info/e-stat-manual3-0)）。

## 指標の範囲と制約

- 人口推移は人口推計表011の都道府県別、年次値です。取得時点のデータは2021〜2024年です。
- 高齢化率は同じ表の「65歳以上」人口を「総数」人口で割った派生値です。人口値の単位は千人、高齢化率は%です。
- 地域比較は選択年の都道府県比較と複数年人口推移です。経済指標は、統計単位・基準年の整合を別途確認するまで追加していません。
- e-Statの利用登録なしではAPI取得できません。キーを設定していない状態で実データの取り込みを装う動作はありません。

## 品質確認とCI

`pytest`はAPI応答の変換、都道府県・年次・単位メタデータの保持、集計地域の除外を確認します。dbtで`dbt test`を実行するとGoldのキー欠損を検査できます。GitHub ActionsはPRでRuffとpytestを実行します。

```sh
ruff check .
pytest
dbt test --project-dir . --profiles-dir .
```
