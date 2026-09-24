# Run HaruEstate

All examples are synthetic. Deterministic calculations, input versions and forecast runs work without a model key. The optional DeepSeek assistant uses one LangGraph with SQLite checkpoints to query completed runs, ask for clarification and propose narrowly scoped changes. Only explicit human confirmation can save a proposed input revision. Forecasts are created separately from the workbench.

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

### Optional controlled assistant

Set `DEEPSEEK_API_KEY` and `DEEPSEEK_MODEL` on the API process. Use a model identifier available in your DeepSeek account and official API documentation. In Compose, copy `.env.example` to the ignored `.env`, then fill those two values; preserve any existing local settings. For local Python development, set process environment variables before starting Uvicorn (`.env` is not loaded automatically). Restart the API after changing model configuration. Never put keys in `VITE_*` variables or frontend requests.

The adapter sends requests only to the official `https://api.deepseek.com/chat/completions` endpoint with JSON output. It sends the question, clarification dialogue, project names, phase identifiers/names, operation mode, scenario and available months; it does not send financial amounts or complete input tables. Questions should not include credentials. For queries the model selects one permitted metric and period; the program validates that selection and reads Decimal values from the bound immutable run. The displayed explanation is a maintained glossary, not an invented causal claim. Routing can still be mistaken: review the displayed metric, scope and period. Real-model compatibility must be smoke-tested with the configured model separately from deterministic tests.

`GET /api/v1/agent/status` reports configuration without calling the model. `POST /api/v1/agent/tasks` accepts `{run_id, question}` for read-only queries and requires an idempotency key. Tasks are listed by `GET /api/v1/agent/tasks?run_id=...`; poll an individual task until `completed`, `failed`, `interrupted`, `awaiting_reply` or `awaiting_confirmation`. Reply with `{token, reply}` to `/agent/tasks/{id}/reply` using an idempotency key. The token belongs to one saved clarification. `/agent/tasks/{id}/resume` resumes interrupted or failed work against the same run and checkpoints, without automatically accepting a changed model configuration. All endpoints are under `/api/v1`.

Each task has at most three model calls, including failures, and at most three execution attempts. The adapter makes no automatic retries, caps responses at 64 KiB, uses a 20-second read timeout and checks a 25-second wall-clock budget between response chunks. Slow network reads may extend the observed time up to one additional read timeout. A paid call that was in flight during an abrupt crash may be repeated within the remaining call budget; a validated response saved before the crash is reused. No model number is accepted as a financial result. Optional external tracing is disabled for this graph.

The existing single executor services forecasts and assistant tasks; a slow model request can briefly delay a queued forecast. Closing the page does not cancel work. An interrupted running task is shown for explicit recovery after restart; an unanswered clarification remains available with the same token. Business task records live in `haru.sqlite3`; graph state lives in `agent-checkpoints.sqlite3` in the same data directory/volume. To preserve in-progress assistant work in a backup, stop the API and back up **both databases as a consistent pair**, using the SQLite backup utility for each before restarting. A business-database-only backup retains forecast results but is not a complete assistant recovery backup.

Deterministic model adapters exist only in automated tests. Missing model configuration displays an unavailable assistant; it does not generate simulated AI responses. Document extraction, general approvals and causal explanations remain outside this assistant.

The task list supports `offset` in pages of 20. Select an older task to reply or resume; clarification questions and replies remain visible. Legacy task dialogue is reconstructed from its saved plans and replies. Flow sources are filtered to the answer's months through repeated `months` query parameters on the evidence endpoint. Cash balances and funding gaps retain cumulative evidence through the relevant ending/peak month. Known foreign project names, portfolio subsets and model-reported scope mismatches trigger clarification. Unknown aliases still depend on model interpretation; always review the displayed bound project and period.

For a proposal, send `mode: "change"` and a `known_on` date when creating a task. The bound run must be a single-project run using the latest input revision. The only supported changes are one phase's unsold-price ratio (-90% to +200%) or delivery delay (0–36 whole months). Absolute prices, multiple changes and other fields require clarification. The domain module computes the resulting price with Decimal and cent rounding; sold contracts and historical actual records are preserved. Completed historical phases cannot be changed through this path.

An `awaiting_confirmation` task contains an immutable draft, its base revision, project, phase, before/after values and a base-scenario parameter preview (without workbench overrides). `POST /agent/tasks/{id}/confirm` requires an idempotency key and `{draft_id, token, project_id, phase_id, base_revision_id, base_version}` matching that draft. The model has no confirmation tool. A newer project version rejects the old confirmation with 409. Revision creation, task completion and retry receipt commit together; repeats return the same revision. Drafts and confirmations use the existing business task payload and do not add a database or migration. After confirmation, select an information cutoff on or after the change's known date and generate a new forecast from the workbench; previous runs remain unchanged. Retain both SQLite databases for graph recovery.

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
