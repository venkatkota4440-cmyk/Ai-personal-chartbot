# Deployment

> **Status after M1:** the stack has been run locally with docker compose
> (PostgreSQL 16, Redis 7) and smoke-tested. **It is not production-ready.**
> The approval gates, automation safety controls, and the M7 security review
> are not built yet. The full production guide is completed in M7.

## Environments

| | Development | Production |
|---|---|---|
| `APP_ENV` | `development` | `production` |
| Database | SQLite file or compose PostgreSQL | Managed PostgreSQL with backups |
| Cookies | `Secure` off (http://localhost) | `Secure` on; HTTPS required |
| API docs | `/api/docs` enabled | disabled |
| `SESSION_SECRET` | auto-generated if missing (sessions reset on restart) | **required**, ≥ 32 random characters; startup fails otherwise |

## Required environment variables (names only)

API and worker: `APP_ENV`, `DATABASE_URL`, `REDIS_URL`, `SESSION_SECRET`,
`CORS_ORIGINS`, `RATE_LIMIT_BACKEND`, `ALLOW_REGISTRATION`, `LOG_LEVEL`,
`FORWARDED_ALLOW_IPS` (only behind a trusted proxy), `AI_PROVIDER`,
`AI_API_KEY`, `ALLOWED_MODELS`.

Web (build time): `API_INTERNAL_URL`.

Docker compose also reads `POSTGRES_PASSWORD`.

Keep values in your platform's secret store. Never commit them, and never
expose them to the browser.

## Release steps

1. Build images: `docker compose build` (or your CI equivalent).
2. **Run migrations as a separate, controlled step:**
   `docker compose run --rm migrate`. The API never migrates on start.
3. Deploy the API and worker, then wait for `/api/health` to return 200.
4. Deploy the web app (built with the correct `API_INTERNAL_URL`).
5. Smoke test: sign in, open Settings, save a change.

## Rollback

- **Code:** redeploy the previous image tags.
- **Schema:** every migration has a `downgrade()`; the M1 migration's
  downgrade is tested automatically. Run `alembic downgrade -1` only after
  taking a backup. Prefer forward fixes for migrations that drop data.

## Backup and restore

PostgreSQL (compose):

```bash
# Backup
docker compose exec -T postgres pg_dump -U paa -d paa -Fc > backup-$(date +%F).dump
# Restore into a fresh database (test this regularly, in a separate environment first)
docker compose exec -T postgres createdb -U paa paa_restore
docker compose exec -T postgres pg_restore -U paa -d paa_restore < backup-YYYY-MM-DD.dump
```

SQLite (local): stop the API, then copy `app.db` (plus any `-wal`/`-shm`
files).

Backup automation and a tested restore drill are M7 deliverables.

## Security checklist before any public deployment

- [ ] HTTPS everywhere; `APP_ENV=production` (secure cookies, docs off)
- [ ] Strong `SESSION_SECRET` from a secret manager
- [ ] `CORS_ORIGINS` set to the real web origin only
- [ ] `ALLOW_REGISTRATION=false` after the owner account exists
- [ ] Database not reachable from the internet; least-privilege DB user
- [ ] `FORWARDED_ALLOW_IPS` set to the reverse proxy only
- [ ] Backups configured and a restore tested
- [ ] M5 approval gates and the M7 security review complete
