<p align="center">
  <img src="frontend/public/sourcepilot-logo.png" alt="SourcePilot" width="320" />
</p>

# SourcePilot

**Turn a plain-English research request into a source-backed dataset.** SourcePilot proposes a collection plan, gathers information from public web pages, and keeps the results searchable, traceable, and ready to export.

[Live app](https://sourcepilot.onrender.com) · [API health](https://utkarshw1625--data-intelligence-api.modal.run/health)

## How it works

```text
Research request → AI-generated plan → human approval → public-web search and scrape
                 → evidence-checked observations → cumulative, exportable dataset
```

### 1. Turn a question into a collection plan

For example, ask: *“Find publicly listed companies in Berlin hiring senior product designers. Include company, role, location, posting date, and application link.”* The frontend sends this to `POST /api/drafts`. The backend asks a model to propose an event title, **1–3 web search queries**, **1–20 named and typed fields** (`text`, `number`, `date`, `url`, or `boolean`), and **1–4 identity fields** used to recognize the same item in later runs. The proposal is saved as a draft; it does not search the web yet.

The default model provider is OpenRouter. Both planning and page extraction send a server-side `POST` to **`https://openrouter.ai/api/v1/chat/completions`** with this ordered model list:

```json
{
  "models": ["openrouter/free", "qwen/qwen3.8-27b:free"]
}
```

[`openrouter/free`](https://openrouter.ai/openrouter/free) lets OpenRouter choose an eligible free model; [`qwen/qwen3.8-27b:free`](https://openrouter.ai/qwen/qwen3.8-27b%3Afree) is the explicit free fallback candidate. [OpenRouter tries the `models` list in priority order](https://openrouter.ai/docs/guides/routing/model-fallbacks). The request also sets `allow_fallbacks: true`, `require_parameters: true`, `data_collection: "deny"`, and `temperature: 0`. The backend instructs the model to return one JSON object matching the supplied schema, then parses and validates the result locally. The selected free model can vary with provider availability; SourcePilot does not claim that one fixed model handled every request. `MODEL_PROVIDER=ollama` is a separately configured **local alternative** using Ollama's `/api/chat` endpoint and `llama3.1`, not an automatic fallback from OpenRouter. API keys stay on the backend. See [`backend/app/providers.py`](backend/app/providers.py).

### 2. Let the user approve the plan

The user can edit the proposed searches, field names and types, and identity fields. `POST /api/workflows/{id}/approve` validates and saves the plan as an active workflow. **Approval does not start a run**: the user starts it separately with `POST /api/workflows/{id}/runs`. Once approved, the schema is fixed for that workflow; cloning it creates an editable draft with the same starting plan. This keeps repeated runs comparable rather than silently changing the dataset's columns.

### 3. Search and read public pages

The worker submits each approved query to Firecrawl's `/v2/search` endpoint, requesting up to four web results per query. It skips duplicate or nonpublic URLs, then calls Firecrawl's `/v2/scrape` endpoint with **basic proxy**, Markdown output, and main-page content only. Blocked, login-only, paywalled, or unavailable pages are skipped. A run is bounded to **three searches and 12 successfully scraped pages**. For each scraped page, the model is asked for at most 20 candidate records in the approved shape, each with a short verbatim evidence excerpt. See [`backend/app/worker.py`](backend/app/worker.py) and [`backend/app/providers.py`](backend/app/providers.py).

### 4. Check evidence and build a dataset that survives reruns

The backend rejects a candidate if its fields or value types do not match the approved schema, an identity field is empty, a URL field points to a nonpublic address, or its evidence excerpt cannot be found in the scraped page after whitespace normalization. This check establishes a traceable text match; it does **not** independently prove that every claim on the page is true.

Accepted findings become **observations** tied to a run and source page. The approved identity values are normalized and hashed into a record key. A later observation with the same key updates the cumulative **record** and its last-seen time instead of creating another row; the run observations remain in the database. Sources retain the page URL and fetch time. See [`backend/app/models.py`](backend/app/models.py) and [`backend/app/worker.py`](backend/app/worker.py).

### 5. Inspect, export, and repeat

The dashboard shows run stages, search/page/observation counts, quota usage, and pause or failure reasons. Members can search and filter records, open their source URL and evidence, and export the full dataset as **CSV or JSON**. The frontend refreshes runs and records every ten seconds.

Creators or organization admins can start a manual run or choose a daily/weekly schedule with a local hour and timezone. A Modal job checks every minute for due work and eligible retries; execution is best effort after the scheduled time. Paused runs retain their run ID and checkpoint so the worker can resume unfinished provider work. See [`backend/app/scheduling.py`](backend/app/scheduling.py) and [`backend/modal_app.py`](backend/modal_app.py).

The first release uses one shared Clerk organization. Members can view and export its data. A workflow's creator or an organization admin can manage its schedule and runs.

## Stack

| Layer | Technology |
| --- | --- |
| Frontend | React, TypeScript, Vite; Render static hosting |
| API and workers | FastAPI, Python; Modal web endpoint, workers, and minute scheduler |
| Data | TiDB Cloud (MySQL protocol), SQLAlchemy 2, Alembic |
| Authentication | Clerk Organizations and verified session JWTs |
| Collection and extraction | Firecrawl `/v2/search` and `/v2/scrape`; OpenRouter `/api/v1/chat/completions` with `openrouter/free` and `qwen/qwen3.8-27b:free`, returning JSON validated locally |

## Run locally (PowerShell)

Requirements: Python 3.11+, Node.js with Corepack/pnpm, a TiDB database, a Clerk application and organization, and free Firecrawl and OpenRouter API keys.

```powershell
python -m venv backend/.venv
./backend/.venv/Scripts/Activate.ps1
pip install -e "./backend[test]"
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env.local
```

Fill in `backend/.env` with `DATABASE_URL`, `CLERK_ISSUER`, `CLERK_JWKS_URL`, `CLERK_ORGANIZATION_ID`, `FIRECRAWL_API_KEY`, and `OPENROUTER_API_KEY`. Use a TiDB `mysql+pymysql://` URL with TLS certificate and identity checks. Keep `ALLOW_PAID_PROVIDERS=false`, `DISPATCH_MODE=local`, and `FRONTEND_ORIGIN=http://localhost:3000`. Set the **public** `VITE_CLERK_PUBLISHABLE_KEY` in `frontend/.env.local`; its `VITE_API_BASE_URL` should be `http://localhost:8000`. Never put backend keys in `VITE_*` variables or commit `.env` files.

From the repository root, apply migrations and start the API:

```powershell
cd backend
alembic upgrade head
uvicorn app.main:app --reload
```

In a second PowerShell window, start the frontend:

```powershell
cd frontend
corepack pnpm install --frozen-lockfile
corepack pnpm dev
```

Open `http://localhost:3000`. Sign in with a member account and select the configured organization. `GET http://localhost:8000/health` returns `{"status":"ok"}` without exposing configuration.

## Deploy at $0 out of pocket

The frontend is hosted as a Render static site and the backend runs on Modal. Create a **named Modal Secret** called `data-intelligence` from a local `backend/.env.modal` based on `backend/.env.modal.example`. Set `DISPATCH_MODE=modal` and `FRONTEND_ORIGIN` to the exact Render origin, such as `https://sourcepilot.onrender.com`. The Modal `DATABASE_URL` must use a CA path available inside its Linux image, with `ssl_verify_cert=true&ssl_verify_identity=true`.

Before cloud execution, manually verify TiDB Starter stays free, Modal's workspace out-of-pocket spend limit is **$0** with a usage budget below its monthly free credits, and Firecrawl/OpenRouter remain on free plans. Keep `ALLOW_PAID_PROVIDERS=false`. Only after those dashboard checks, set `SPEND_GUARDS_VERIFIED=true` in your local `backend/.env.modal` and update the Secret. Deployment is blocked while that flag is false.

```powershell
modal secret create data-intelligence --from-dotenv backend/.env.modal --force
modal deploy backend/modal_app.py --stream-logs
```

Run `alembic upgrade head` manually from `backend/` against TiDB before deployment. In Render, set only `VITE_API_BASE_URL` (the Modal API origin) and `VITE_CLERK_PUBLISHABLE_KEY`. Add the Render origin to Clerk's allowed origins. The API uses `FRONTEND_ORIGIN` for CORS. Do not store credentials in the repository or Render's `VITE_*` settings.

## Cost and recovery limits

Each run is limited to **3 searches, 12 scraped pages, 100 observations, and 10 minutes per execution attempt**. Each organization has **one active run**, **20 model calls per UTC day**, and **600 Firecrawl credits per UTC month**. A search returning up to four results reserves two credits; each basic scrape reserves one. Provider or quota exhaustion pauses work with a visible reason. The minute scheduler dispatches queued work and resumes eligible paused runs using their existing run ID and saved checkpoint. After an OpenRouter 429, automatic retry delays increase through 1, 3, 5, 10, 30, 120, 300, and 1440 minutes; other provider or quota pauses retry after one hour, while the per-run search limit does not auto-retry. A manual retry creates a new run. SourcePilot does not route to paid models or enhanced proxies.

## Checks

```powershell
cd backend
pytest
ruff check .
cd ../frontend
corepack pnpm build
```

The backend tests use mocked providers and cover the workflow, authorization, quotas, scheduling, and exports. A real-provider smoke test should be kept small and run only after the free-tier spending controls have been verified.
***
## Architecture

<img width="3669" height="8719" alt="diagram" src="https://github.com/user-attachments/assets/2f042007-13fc-4b16-b634-3cbd5c224775" />
