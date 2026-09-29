<p align="center">
  <img src="frontend/public/sourcepilot-logo.png" alt="SourcePilot" width="320" />
</p>

# SourcePilot

**Turn a plain-English research request into a source-backed dataset.** SourcePilot proposes a collection plan, gathers information from public web pages, and keeps the results searchable, traceable, and ready to export.

[Live app](https://sourcepilot.onrender.com) · [API health](https://utkarshw1625--data-intelligence-api.modal.run/health)

## How it works

1. Describe the information you need. An OpenRouter free model proposes search queries, typed fields, and identity fields.
2. Edit and approve the proposed schema before collection starts. After the first run, clone the workflow to change its fields.
3. Firecrawl searches and scrapes public pages. SourcePilot extracts records, validates evidence, and merges duplicates by the approved identity fields while retaining observations from each run.
4. Monitor runs and quota usage, inspect each record's source URL, evidence excerpt, and fetch time, then search, filter, or export the cumulative dataset as CSV or JSON.
5. Optionally schedule daily or weekly reruns. A Modal job checks for due work hourly; starts are best effort within that hour.

The first release uses one shared Clerk organization. Members can view and export its data. A workflow's creator or an organization admin can manage its schedule and runs.

## Stack

| Layer | Technology |
| --- | --- |
| Frontend | React, TypeScript, Vite; Render static hosting |
| API and workers | FastAPI, Python; Modal web endpoint, workers, and hourly scheduler |
| Data | TiDB Cloud (MySQL protocol), SQLAlchemy 2, Alembic |
| Authentication | Clerk Organizations and verified session JWTs |
| Collection and extraction | Firecrawl free search/basic scrape; OpenRouter free structured-output models |

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

Each run is limited to **3 searches, 12 scraped pages, 100 observations, and 10 minutes per execution attempt**. Each organization has **one active run**, **20 model calls per UTC day**, and **600 Firecrawl credits per UTC month**. A search returning up to four results reserves two credits; each basic scrape reserves one. Provider or quota exhaustion pauses work with a visible reason. The hourly scheduler recovers eligible paused or queued work using the same run ID; a manual retry creates a new run. SourcePilot does not route to paid models or enhanced proxies.

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
