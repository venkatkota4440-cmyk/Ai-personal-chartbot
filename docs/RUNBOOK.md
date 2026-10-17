# Runbook

Operational procedures. Sections marked *(M4+)* describe behaviour that
arrives in later milestones; they are kept here so the structure is ready.

## Health and logs

- `GET /api/health` returns `200 {"status":"ok"}` when the database answers,
  and `503 {"status":"degraded"}` otherwise. It never includes configuration
  values.
- API logs are one JSON object per line on stdout, with `request_id`, path
  (never query strings), status, and duration. Secrets, tokens, cookies, and
  passwords are redacted by key name and by pattern; emails are masked
  (`o***@example.com`).
- Every API response carries `X-Request-ID`. Error bodies include the same
  `request_id`, so a user can quote it and you can `grep` the logs for it.

```bash
docker compose logs -f api            # live API logs
docker compose logs api | grep <request_id>
```

## Audit trail

`audit_events` records who did what, to which target, and the result
(`auth.register`, `auth.login` success/failure, `auth.logout`,
`settings.update`). Metadata passes through redaction before storage.

```sql
SELECT timestamp, action, result, target, request_id
FROM audit_events ORDER BY timestamp DESC LIMIT 50;
```

## Common incidents

### Someone may be guessing a password
1. Look for repeated `auth.login` / `failure` events for one target.
2. Rate limiting already returns `429` after 5 attempts per minute for an
   account.
3. If needed, set `ALLOW_REGISTRATION=false` and rotate the account password.

### Sign out every session for a user
`SESSION_SECRET` rotation invalidates CSRF tokens only. To revoke sessions:

```sql
UPDATE sessions SET revoked_at = now() WHERE user_id = '<id>' AND revoked_at IS NULL;
```

### A secret may have leaked
1. Rotate it in the deployment environment (never in git).
2. For `SESSION_SECRET`: restart the API. CSRF tokens refresh automatically
   on the client.
3. For an AI provider key: revoke it at the provider, then set the new key.
4. Inspect `audit_events` for the affected period.

### Chat replies fail
The UI and API return a typed category, and the user's message is already saved:
- `ai_unavailable`: provider down, timeout, rate-limited, missing or invalid key,
  or model not allowlisted. Check `AI_PROVIDER`, `AI_API_KEY`, and `ALLOWED_MODELS`.
- `ai_invalid_output`: the reply failed schema validation or was cut off. It was
  discarded. Repeated occurrences mean the prompt or the `AI_MAX_OUTPUT_TOKENS`
  limit needs attention.
- `ai_refused`: the model (and its fallback) declined.

```sql
SELECT timestamp, result, metadata_sanitized FROM audit_events
WHERE action = 'chat.reply' ORDER BY timestamp DESC LIMIT 20;
```

### A run fails *(M4+)*
Inspect the run ID, step logs, and sanitized error. Retry only after
confirming idempotency (the same `Idempotency-Key` returns the existing run).

### Duplicate actions *(M4+)*
Disable the automation, inspect `automation_runs.idempotency_key` and the
lock columns, fix the trigger or locking, and add a regression test.

### AI output looks unsafe or wrong *(M2+)*
Stop the run (cancel), keep the logs, review the untrusted input and the tool
policy, then test a mitigation before re-enabling.

### Data loss
Stop writes if needed, restore to a **separate** environment first, validate,
then follow [DEPLOYMENT.md § Backup and restore](DEPLOYMENT.md#backup-and-restore).
