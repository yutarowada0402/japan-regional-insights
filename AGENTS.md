# Repository guidance

- 表示する統計値はすべて公的統計（e-Stat / 総務省統計局「人口推計」）由来とし、出典メタデータを各層で保持すること。
- 認証情報（ESTAT_APP_ID 等）をコミットしない。実データはパイプラインで再生成できる形にし、捏造した観測値を入れない。
- データ取得・変換・表示の責務分離を守る（src/ingestion / dbt / app）。
- 変更前に `ruff check src app tests`、`pytest`、`python -m src.processing.build_dataset` を通すこと。
- 利用者向けドキュメント（README等）は日本語で書く。

（方針の一部は先行ブランチ feature/japan-regional-insights-mvp の AGENTS.md から引き継いだ。）
