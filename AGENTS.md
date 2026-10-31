# Repository guidance

- Keep all displayed observations sourced from e-Stat and retain source metadata through every layer.
- Never commit credentials, downloaded production data, or fabricated observations.
- ETL should be deterministic, idempotent, and safe to rerun.
- Run `ruff check .` and `pytest` before submitting changes.
- Keep documentation in Japanese where it describes the end-user application.

