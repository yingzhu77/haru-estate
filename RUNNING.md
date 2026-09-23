# Run HaruEstate

All examples are synthetic. This first release provides deterministic calculations and persisted program steps. DeepSeek and LangGraph integration is a later stage; no model key is required.

## Docker

```sh
docker compose up --build -d
```

Open http://127.0.0.1:8080. Only the web service binds a host port. SQLite and immutable run snapshots are stored in the `haru-estate_haru-data` named volume. Normal restarts and rebuilds retain data. Do not use `docker compose down -v` unless you intend to permanently delete it.

If 8080 is occupied, set `HARU_PORT=8088` before running Compose (PowerShell: `$env:HARU_PORT='8088'`); then use http://127.0.0.1:8088. This does not change the database volume.

The demo binds to localhost and has no authentication or tenant authorization. Do not expose it to a public network. Only one API process is supported. A running job interrupted by a restart can be resumed from History using its original snapshot; completed results are immutable.

## Local development

Backend: Python 3.11, create `backend/.venv`, install `backend/requirements-dev.lock`, then in `backend` run `python -m uvicorn app.main:app --reload`. Frontend: Node 24.15 or later in the 24.x series, run `npm ci` and `npm run dev` in `frontend`. Vite proxies `/api` to port 8000.

Checks: in `backend`, `python -m pytest`, `python -m ruff check app tests`, `python -m mypy app`. In `frontend`, `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`. Browser tests use `npm run test:e2e` against the Docker address; first install Chromium using `npx playwright install chromium`.

For isolated browser testing, point a separate API process at a new `HARU_DATA_DIR`, set `HARU_API_PROXY` to its URL when starting Vite, and set `HARU_E2E_URL` to that Vite URL before running browser tests. These tests create synthetic projects and revisions; use a test database rather than your working dataset.

## Input retries and history

Project creation, project edits, revision saves, CSV confirmation and forecast creation require an `Idempotency-Key` header (8–128 characters). Reuse the same key and payload after an uncertain response; a changed payload with that key returns 409. Successful input writes and their response receipts commit in one SQLite transaction. The browser keeps retry keys for uncertain input writes within the current page session. After refreshing or closing that session, inspect saved records before manually repeating an uncertain creation. Saved versions and forecast tasks persist independently of the browser.

The startup migration adds retry receipts and a run-date index without replacing existing inputs or results. `/api/v1/runs/page` and `/api/v1/projects/{id}/revisions` accept `offset` and `limit` (1–100). Run filtering happens before pagination; portfolio child runs are reached through their bound parent. The existing `/runs` list remains available for the latest 100 matching top-level runs. Revision comparison is read-only, project-scoped, and matches business records by ID; payment schedules without IDs are shown as whole arrays.

The History comparison reconciles common forecast months into signed revenue, cost, expense, tax and interest contributions. It is a component bridge, not causal attribution. Currency, unit, profit basis and rule version must agree. Sources open the saved run rather than the latest project data.

Single-project sensitivity reports both 12-month profit and peak uncovered funding gap from the first forecast month through lifecycle end. A positive gap change means greater funding pressure. An out-of-range variant is marked unavailable without invalidating the base result. Portfolio sensitivity is viewed through bound child runs; individual peak gaps must not be summed. Old runs are not recalculated to populate new columns, which display as unavailable.

## Model boundary

Amounts are CNY yuan, calculated with Decimal and rounded to cents. Screens display ten-thousand yuan. Sales, receipts, delivery-based revenue, development expenditure, cost recognition and payments have separate schedules. The three named scenarios are conditional assumptions, not probability intervals. Simplified taxes are revenue times an explicit example rate; interest is expensed. Results are **simulated management profit**, not statutory net profit or investment advice.

Historical months require records; a zero-activity month must be explicitly recorded. Cost budgets require land, construction and other development cost, including explicit zero amounts where appropriate. The uniform sell-through and area-based cost allocation are example rules requiring business validation. A forecast uses the latest input revision available at its information cutoff, then filters individually known records. A revision's known date must reflect when that revision became available; changing old facts does not modify old runs.

The project portfolio freezes members and child run IDs, sums aligned flows and adds each project's uncovered cash shortfall before finding the peak. Cash surpluses do not fund other projects. Failed members keep the portfolio incomplete without a total. New projects and later edits do not alter previous results.

## Backup and restore

Create a consistent backup without copying a live WAL database directly:

```sh
docker compose exec api python -m app.backup /app/data/haru.sqlite3 /app/data/backups/manual-001.sqlite3
docker compose cp api:/app/data/backups/manual-001.sqlite3 ./backups/manual-001.sqlite3
```

Use a new filename for each backup. Restore only while the target API is stopped, to a **new empty** data directory or volume under the filename `haru.sqlite3`. Start a separate API instance pointing `HARU_DATA_DIR` at it, check project/run counts and known results before switching. Never overwrite a live database or mix a restored database with old WAL files. Tests exercise backup and restore against independent temporary data.

API documentation is available inside the container at `/docs`; public business endpoints use `/api/v1`. Generate the TypeScript contract with `python backend/export_openapi.py` followed by `npm run generate:api` in `frontend`.
