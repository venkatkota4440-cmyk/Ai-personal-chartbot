# Personal AI Agent Platform — Technical Documentation

> Source of truth: the Technical Documentation PDF supplied by the project owner (v1.0, 16 October 2026). Faithful text copy; deviations are recorded in [DECISIONS.md](DECISIONS.md).

```text
               PERSONAL AI AGENT PLATFORM
                     Technical Documentation & Implementation Guide
                                    Version 1.0 | 16 October 2026 | Beginner-friendly MVP guide

1. Purpose and Scope
This document describes a practical implementation blueprint for a personal AI agent platform that supports chat, memory,
projects/tasks, and safe scheduled automation on desktop and mobile. It also explains how to add the ScamShield AI project as a
managed project. It is a blueprint, not a claim that the system has already been deployed.

2. System Overview
  User (Desktop / Mobile Web) → Frontend → FastAPI Backend → Auth + Policy Gate → AI Orchestrator →
  Tools/Connectors
  ■ PostgreSQL / File Storage
  Scheduler → Job Queue → Worker → Policy Gate → Tool Execution → Audit Log / Notifications

The model proposes plans and content. The backend—not the model—enforces authentication, permissions, validation, approval,
rate limits, and logging.

3. Recommended Technology
 Layer                                       Suggested choice                              Purpose

 Frontend                                    Next.js/React + TypeScript + Tailwind         Responsive UI, accessible components

 API                                         FastAPI + Pydantic                            Typed endpoints and request validation

 Database                                    PostgreSQL                                    Users, memory, tasks, workflows, runs,
                                                                                           approvals

 Local development                           SQLite                                        Quick prototype only; migrate before
                                                                                           multi-user deployment

 Background jobs                             Redis + RQ/Celery or managed queue            Run scheduled/long-running jobs outside
                                                                                           web requests

 AI provider                                 Provider adapter for a model API              Chat, planning, summarization, structured
                                                                                           outputs

 Testing                                     pytest + frontend unit/e2e tests              Regression and safety validation

 Deployment                                  Managed frontend + backend + database         TLS, secrets, logs, backups

4. Suggested Repository Structure
  personal-ai-agent/
  apps/
  web/ # Next.js UI
  api/
  app/
  main.py
  api/routes/
  core/config.py
  core/security.py
  db/models.py
  db/session.py
  services/ai.py
  services/memory.py
  services/policy.py
  services/automation.py
  workers/tasks.py
  schemas/
  tests/
  pyproject.toml
  packages/
  shared-types/
  migrations/
     docs/
     PRD.md
     TECHNICAL_DOCUMENTATION.md
     .env.example
     docker-compose.yml
     README.md

    5. Core Data Model
    Entity                                      Important fields                                  Notes

    users                                       id, email, password_hash, timezone,               Never store raw passwords
                                                created_at

    conversations                               id, user_id, title, created_at                    Owner-scoped records

    messages                                    id, conversation_id, role, content,               Apply retention and sensitive-data controls
                                                created_at

    memories                                    id, user_id, content, source, approved,           Allow user review, edit, delete
                                                updated_at

    projects                                    id, user_id, name, description, status            ScamShield AI can be one project

    tasks                                       id, project_id, title, status, priority, due_at   Include ownership and audit timestamps

    automations                                 id, user_id, name, trigger_type, schedule,        Store versioned workflow definitions
                                                enabled, policy

    automation_runs                             id, automation_id, status, started_at,            Each execution has a unique run ID
                                                finished_at, error

    approvals                                   id, run_id, action_summary,                       Approval must bind to exact proposed
                                                payload_hash, status, expires_at                  action

    audit_events                                id, user_id, actor, action, target, result,       Avoid storing secrets in audit payloads
                                                timestamp

    6. API Design
    Method + route                              Purpose                                           Key safeguards

    POST /api/chat                              Send message and receive assistant                Auth, per-user rate limit, model timeout
                                                response

    GET /api/conversations                      List user's conversations                         Owner-scoped query

    GET/POST /api/memories                      List or create memories                           Explicit consent and validation

    PATCH/DELETE /api/memories/{id}             Edit or delete a memory                           Verify ownership; log change

    GET/POST /api/projects                      List or create projects                           Owner-scoped CRUD

    GET/POST /api/tasks                         List or create tasks                              Validate status, dates, project ownership

    GET/POST /api/automations                   List or create automations                        Validate trigger, steps, permission policy

    POST /api/automations/{id}/run              Manually run workflow                             Authorization, run limits, idempotency

    GET /api/runs/{id}                          Inspect run state and output                      Owner-scoped access

    POST /api/approvals/{id}/approve            Approve a pending action                          Re-check action hash, expiry, permissions

    POST /api/approvals/{id}/reject             Reject a pending action                           Record decision and reason

    POST /api/runs/{id}/cancel                  Request cancellation                              Only cancel safely; worker checks
                                                                                                  cancellation

    7. Automation Execution Lifecycle
1    Trigger fires: user request, scheduled time, or an allowed event.
2      Create an automation_run record with status queued and a unique idempotency key.
3      Worker loads the workflow version and verifies that it is enabled and owned by the user.
4      Planner converts the goal into structured steps; validate output against a strict schema.
5      Policy service classifies each proposed tool action by risk and checks permissions.
6      Low-risk allowlisted actions may execute. High-risk actions create an approval record and pause.
7      On approval, verify the exact payload has not changed, the approval is unexpired, and permissions remain valid.
8      Execute with timeouts, bounded retries, rate limits, and per-step logging.
9      Store the result and transition to succeeded, partially_succeeded, failed, awaiting_approval, or cancelled.
10     Notify the user and retain an audit trail without secrets.

     8. Permission Policy
     Default policy: allow read-only analysis and internal drafts; ask before external communication, publishing, sharing, deleting,
     spending, or changing security/account settings. For each connector, request only the scopes required. An approval should
     authorize one exact action and expire after a short configured period.

     9. Memory Design
•      Store only information that is useful over time and appropriate to retain.
•      Separate user-approved facts from transient chat context and AI-generated guesses.
•      Record source, creation time, and last-updated time.
•      Provide inspect, edit, delete, export, and retention controls.
•      Do not treat arbitrary text from a website or uploaded document as a trusted memory instruction.
•      Use retrieved memories only when relevant; support a per-conversation memory-off option.

     10. Prompt-Injection and Tool Safety
•      Treat webpages, documents, email content, and tool results as untrusted data, not instructions.
•      Never let model output directly call arbitrary code or shell commands.
•      Expose narrow, typed tools with allowlisted parameters.
•      Validate URLs, file paths, MIME types, sizes, and connector targets.
•      Require confirmation for irreversible or external actions.
•      Redact tokens, passwords, and personal data from logs.
•      Apply per-user quotas, timeouts, maximum steps, and circuit breakers.

     11. UI/UX Specification
•      Primary navigation: Chat, Tasks, Projects, Automations, Approvals, Files, Settings.
•      Home view: greeting, today's priorities, active projects, recent runs, and approvals awaiting action.
•      Automation detail: trigger, workflow steps, permission mode, last run, next run, and run history.
•      Approval view: exact action, target, preview, risk explanation, Approve once, Reject, and optional edit/review path.
•      Use dark navy surfaces, electric-purple primary actions, cyan highlights, and clear severity/status colors.
•      Motion: subtle scroll reveals and transitions; disable or reduce motion when user preferences request it.
•      Ensure readable contrast, keyboard support, focus indicators, descriptive labels, and mobile-friendly touch targets.

     12. Example Workflow Definitions
     12.1 Daily briefing
       name: Daily Briefing
       trigger:
      type: schedule
      cron: '0 8 * * *'
      steps:
      - type: read_tasks
      - type: summarize_priorities
      - type: draft_briefing
      permissions:
      auto_allowed: [read_tasks, summarize_priorities, draft_briefing]
      require_approval: []
      output: notification_and_dashboard_card

    12.2 Coding task helper
      name: Coding Task Helper
      trigger: manual
      steps:
      - type: clarify_goal_if_needed
      - type: inspect_user_provided_files
      - type: propose_plan
      - type: draft_code_and_tests
      - type: create_project_tasks
      permissions:
      auto_allowed: [read_project_tasks, draft_code_and_tests, create_internal_task]
      require_approval: [push_commit, open_pull_request, deploy]

    12.3 ScamShield project review
      name: ScamShield Weekly Review
      trigger:
      type: schedule
      cron: '0 10 * * 1'
      steps:
      - type: read_project_milestones
      - type: summarize_open_tasks
      - type: identify_blockers
      - type: draft_next_week_plan
      permissions:
      auto_allowed: [read_project_milestones, summarize_open_tasks, draft_next_week_plan]
      require_approval: [publish_report, modify_production_settings]

    13. Environment Configuration
      # .env.example — placeholders only; never commit real secrets
      APP_ENV=development
      DATABASE_URL=sqlite:///./app.db
      AI_PROVIDER=your_provider
      AI_API_KEY=replace_with_secret
      SESSION_SECRET=replace_with_long_random_secret
      REDIS_URL=redis://localhost:6379/0
      LOG_LEVEL=INFO

    Use a secrets manager or deployment environment variables in production. Never put API keys in frontend code, public
    repositories, screenshots, or client-side bundles.

    14. Testing Plan
•     Unit tests: policy decisions, schema validation, memory ownership, workflow parsing, risk classification.
•     Integration tests: database persistence, worker-to-API flow, approval lifecycle, connector errors.
•     End-to-end tests: sign-in, create task, create automation, run, approve/reject, inspect history.
•     Security tests: cross-user access denial, expired approval, changed payload, invalid URL, oversized file, rate-limit behavior.
•     Reliability tests: duplicate trigger, worker crash, timeout, retry limit, cancellation, database unavailable.
•     Accessibility tests: keyboard-only navigation, contrast, focus order, reduced-motion mode.

    15. Deployment Checklist
•     Separate development and production environments.
•     Use HTTPS, secure cookies, CSRF protection where applicable, and safe CORS configuration.
•     Run migrations as a controlled deployment step.
•     Configure health checks, structured logs, alerting, and error reporting.
•     Back up the database and test restoration.
•     Restrict database/network access; rotate credentials; configure rate limits.
•     Document rollback and data-export/deletion procedures.
•     Start with demo mode and synthetic data; add live integrations one at a time.

    16. Implementation Roadmap
     Milestone                                     Build                                           Definition of done

     M1                                            Foundation and auth                             Secure login, schema migrations,
                                                                                                   responsive shell

     M2                                            Chat and memory                                 Persistent conversations and
                                                                                                   user-controlled memory

     M3                                            Projects and tasks                              CRUD, filters, priorities, due dates

     M4                                            Automation engine                               Scheduler, queue, worker, run states, logs

     M5                                            Approvals and policies                          High-risk actions pause and require
                                                                                                   one-time approval

     M6                                            Notifications and files                         Run notifications and validated file
                                                                                                   handling

     M7                                            Hardening                                       Automated tests, security review,
                                                                                                   backups, deployment guide

    17. Operational Runbook
•     If a run fails: inspect run ID, step logs, and sanitized error; retry only after confirming idempotency.
•     If an integration is compromised: revoke connector access, rotate secrets, disable related automations, inspect audit events.
•     If duplicate actions occur: pause the workflow, inspect idempotency keys, correct the trigger/locking issue, and add a regression
      test.
•     If AI output appears unsafe or incorrect: stop execution, preserve relevant logs, review untrusted input and tool policy, then test a
      mitigation.
•     If data is lost: stop writes if necessary, restore to a separate environment first, validate, then follow the documented recovery
      plan.

    18. Important Implementation Note
    Begin with a local demo using synthetic data. Do not connect email, messaging, payment, or production systems until
    authentication, approval gates, audit logging, and failure handling have been tested. A prototype with chat and SQLite is not
    production-ready until these controls are implemented.
```
