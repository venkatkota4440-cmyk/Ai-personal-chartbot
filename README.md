# Personal AI Agent Platform

A personal AI assistant for chat, memory, projects, tasks, and **safe**
automations. Routine low-risk work can run automatically; anything consequential
(sending, publishing, deleting, spending, changing security settings) waits for
your explicit, one-time approval.

> **Status: Milestone 5 of 7.** Working and tested: sign-in, chat with
> memory, projects and tasks, the automation engine (scheduler, worker,
> run timeline, cancellation) and the approval gate. Files and the final
> hardening pass are still marked "not available yet". The interface follows
> Apple's design language in light and dark appearance. This is **not
> production-ready**; see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Two things live in this repository

They are not the same program, and the difference matters:

| | `apps/` (this project) | [`hosted-app/`](hosted-app/) |
|---|---|---|
| What it is | The full architecture: FastAPI + Next.js, 14 tables, migrations, 133 backend tests | One HTML file, no build step |
| Posting | **Nothing leaves it.** Connectors are stubs that return "NOT sent" | **Really publishes to Instagram**, via the viewer's own connector |
| Where it runs | Your own server, or `docker compose up` | Published as a private page that borrows the viewer's connectors |
| Why it exists | The deployable system, built to the PRD | To get the automation genuinely working end to end |

If you only want to read how the safety model is enforced in code, start with
`apps/api/app/services/policy.py` and `approvals.py`. If you want the version
that actually posts, read [`hosted-app/README.md`](hosted-app/README.md).

> **Before running `hosted-app/agent-app.html` yourself:** `DRIVE_FOLDER` in it
> is deliberately blank. A Google Drive folder shared as "anyone with the link"
> is reachable by anyone who knows its id, so that id is a credential and is
> never committed to this public repository. Fill in your own.

## What is in here

```
personal-ai-agent/
  apps/api/            FastAPI backend (Python 3.12+)
    app/main.py        app factory: middleware, routes, error handlers
    app/api/routes/    thin HTTP routes (auth, settings, health)
    app/core/          config, security, CSRF/size/request-id middleware, rate limits, logging, redaction
    app/db/            SQLAlchemy models (whole data model), session, owner-scoped repository helpers
    app/services/      business logic (auth, settings, audit)
    app/schemas/       Pydantic request/response models
    app/workers/       RQ worker jobs (heartbeat now; automation executor in M4)
    tests/             pytest suite
  apps/web/            Next.js 16 + React 19 + Tailwind 4 + Radix UI
  packages/shared-types/  TypeScript API contracts used by the web app
  migrations/          Alembic migrations
  docs/                PRD, technical doc, decisions, runbook, deployment, repo evaluation
  docker-compose.yml   web, api, worker, redis, postgres (+ one-shot migrate)
```

## Quick start (local, no Docker)

You need **Python 3.12+** and **Node.js 22+**.

```bash
cd personal-ai-agent

# 1. Configuration: placeholders only, edit as needed (never commit .env)
cp .env.example .env

# 2. Backend
python3 -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r apps/api/requirements-dev.txt
cd apps/api
alembic upgrade head                   # creates ./app.db (SQLite)
uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```bash
cd personal-ai-agent/apps/web
npm install
npm run dev                            # http://localhost:3000
```

Open http://localhost:3000, create an account (password of at least 12
characters), and you will land on the home view.

> Without `SESSION_SECRET` in `.env`, development uses a random secret and you
> are signed out whenever the API restarts. Generate one with
> `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

## Quick start (Docker, full stack on PostgreSQL)

```bash
cd personal-ai-agent
cp .env.example .env     # set POSTGRES_PASSWORD and SESSION_SECRET
docker compose up --build
```

- Web: http://localhost:3000
- API (localhost only, for debugging): http://localhost:8000/api/health

Migrations run as a separate one-shot `migrate` service before the API
starts.

## How safety actually works

1. A trigger creates a run with a server-derived idempotency key, so the same
   trigger twice gives you one run, not two.
2. The worker validates the stored workflow against a strict schema. A step
   type that is not in the registry is refused.
3. Every step is classified by the backend: low, medium, high, or prohibited.
   An automation's own policy cannot downgrade a high-risk step.
4. A high-risk step stops the run and creates an approval showing the exact
   action, target, data and consequence, with a fingerprint of the payload.
5. Approving re-checks that fingerprint, the expiry and the permissions, then
   runs the step once and marks the approval used.
6. Nothing reaches a real external service in this version: connectors are
   stubs that say "NOT sent".

## Running the checks

```bash
# Backend (from apps/api, venv active)
python -m pytest                 # unit + integration tests
ruff check . ../../migrations    # lint
ruff format --check . ../../migrations
mypy app                         # strict type check
alembic check                    # models and migrations agree

# Frontend (from apps/web)
npm run typecheck
npm run lint
npm test                         # Vitest unit tests
npm run build
npm run e2e                      # Playwright: starts its own API (fresh SQLite) and web server

# Scheduler (separate process; only needed for scheduled automations)
python -m app.workers.scheduler  # from apps/api
```

`npm run e2e` expects the Python venv at `personal-ai-agent/.venv`, or set
`E2E_PYTHON`. Run `npx playwright install chromium` once, or point
`PLAYWRIGHT_CHROMIUM_EXECUTABLE` at an existing Chromium.

## Using a real AI model (optional)

Out of the box the assistant uses a deterministic **mock** model: free,
offline, and clearly labelled "demo mode". To use Claude, set these in `.env`
(server side only; the key never reaches the browser):

```
AI_PROVIDER=anthropic
AI_API_KEY=<your Anthropic API key>
ALLOWED_MODELS=mock-deterministic,claude-opus-5-5
```

Restart the API, then pick the model in **Settings → Assistant model**. Every
reply is validated against a strict schema before it is stored; invalid or
refused replies are reported as errors, never shown as answers.

## Security model (short version)

- The **backend** enforces authentication, authorization, validation, rate
  limits, and audit logging. The AI model only ever proposes things (M2+).
- Sessions are server-side; the cookie is `HttpOnly` + `SameSite=Lax` (+
  `Secure` in production) and only its hash is stored.
- Every state-changing request needs a signed CSRF token and an allowed
  origin.
- Every user-owned query is scoped to the signed-in user; another user's
  record looks exactly like a missing one (`404`).
- Errors return `{"error": {"category", "message", "request_id"}}`, never
  stack traces.
- Secrets live only in server-side environment variables. The browser talks
  only to the web origin, which proxies `/api`.

Details and trade-offs: [docs/DECISIONS.md](docs/DECISIONS.md).

## Roadmap

| Milestone | Scope | Status |
|---|---|---|
| M1 | Foundation and auth | ✅ done |
| M2 | Chat and memory (MockProvider + Claude adapter, proposed/approved memories) | ✅ done |
| M3 | Projects and tasks, ScamShield AI seed data | ✅ done |
| M4 | Automation engine: scheduler, worker, idempotency, cancellation | ✅ done |
| M5 | Approvals and policies: payload-hash, expiry, one-time use | ✅ done |
| M6 | Files and document summaries (notifications shipped with M5) | next |
| M7 | Hardening, accessibility, e2e flows, backup/restore, deployment | |

## Documentation

- [docs/PRD.md](docs/PRD.md): product requirements
- [docs/TECHNICAL_DOCUMENTATION.md](docs/TECHNICAL_DOCUMENTATION.md): architecture blueprint
- [docs/DECISIONS.md](docs/DECISIONS.md): every choice and deviation, with reasons
- [docs/REPOSITORY_EVALUATION.md](docs/REPOSITORY_EVALUATION.md): licence and maintenance review of the 10 shortlisted open-source projects
- [docs/RUNBOOK.md](docs/RUNBOOK.md): operating and incident procedures
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md): environments, release, rollback, backup
