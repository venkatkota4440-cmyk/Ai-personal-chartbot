# Repository evaluation

Evaluated on **16 October 2026** against the shortlist in
[REPOSITORY_SHORTLIST.md](REPOSITORY_SHORTLIST.md). The shortlist itself says
the projects are not a tested combined stack and must be checked before
adoption, so this records what was checked and what was decided.

## How each repository was checked

- Shallow, read-only git clone (no checkout, nothing executed).
- License files read from the default branch.
- Date of the latest commit on the default branch.
- README read for scope and maturity statements.

**Not checked:** open issues, CVE history, release cadence beyond the latest
commit, or runtime behaviour. None of these projects was installed or run.
Treat the "maintenance" column as a single data point, not an audit.

## Results

| # | Repository | License (read from repo) | Latest commit | Decision |
|---|---|---|---|---|
| 1 | PersonalClaw/PersonalClaw | MIT | 2026-10-15 | **Reference only** |
| 2 | Vexillon-ai/MIRA | AGPL-3.0 | 2026-10-16 | **Reference only (no code copied)** |
| 3 | letta-ai/letta | Apache-2.0 | 2026-09-10 | **Not adopted for MVP** |
| 4 | langchain-ai/langgraph | MIT | 2026-10-16 | **Not adopted for M4; revisit later** |
| 5 | n8n-io/n8n | Sustainable Use License + Enterprise License for `.ee` files | 2026-10-16 | **Candidate connector backend (post-MVP), integrated by API** |
| 6 | langgenius/dify | Modified Apache-2.0 (multi-tenant and branding conditions) | 2026-10-16 | **Rejected (overlaps the core)** |
| 7 | open-webui/open-webui | Open WebUI License (BSD-3 style with branding conditions) | 2026-10-16 | **UI reference only** |
| 8 | agent0ai/agent-zero | MIT | 2026-10-13 | **Pattern reference only; never as runtime** |
| 9 | khoj-ai/khoj | AGPL-3.0 | 2026-08-01 | **Reference only for M6 document search** |
| 10 | elyase/awesome-personal-ai-assistants | CC0-1.0 | 2026-02-25 | **Discovery list, not a dependency** |

## Reasoning

### Foundation: build our own core, keep the agreed stack

The project brief fixes the stack (FastAPI, SQLAlchemy, Alembic, Next.js) and
the exact data model, approval lifecycle, and API. Adopting a whole platform
as the foundation would mean either replacing that design or maintaining a
fork. The deciding points:

- **PersonalClaw** (MIT) has the closest feature set: chat, memory, goal
  loops, automation, and channels. Its README states it is **pre-1.0 with
  breaking changes expected**. Building on a moving pre-1.0 platform, then
  retrofitting payload-hash approvals, would cost more than building a small
  core we fully understand. It stays a useful design reference for memory UX
  and the dashboard layout.
- **MIRA** is **AGPL-3.0**. Copying its code into this project would put the
  whole platform under AGPL network-use obligations. It is used for ideas
  only; no code is copied.

### Memory: Letta not needed for the MVP

The listed `letta-ai/letta` repository now contains only a README and policy
files. Its README says development moved to **`letta-ai/letta-code`**. The
MVP's memory rules (proposed → approved, owner-scoped, a per-conversation off
switch, edit/delete/export) are simple relational data, so they fit in our
own `memories` table. Revisit Letta only if semantic recall over long
histories becomes a real need.

### Orchestration: LangGraph deferred

**LangGraph** (MIT, very active) is the strongest candidate for multi-step
agent graphs with human-in-the-loop interrupts. For M4/M5, however, the brief
specifies an exact, deterministic lifecycle: an idempotency key, a run lock,
strict plan schema validation, per-step policy classification, and approval
bound to a payload hash. That lifecycle is safer and easier to audit as an
explicit state machine stored in our own `automation_runs` and `run_steps`
tables, which also act as durable checkpoints. Adding LangGraph would create a
second source of truth for run state. Reconsider it for open-ended
conversational agents after M7.

### Integrations: n8n is the most promising path to real connectors

**n8n** is not OSI open source. Under the Sustainable Use License, internal
and personal use is allowed, but offering it as a hosted service to others is
not, and `.ee` files need an enterprise licence. For a **personal** platform,
running n8n as a separate service is acceptable. The safe integration shape:

```
Our approval service ──(only after approval is consumed)──► n8n webhook ──► external service
```

n8n would never decide *whether* an action runs; it would only perform an
action our backend has already approved, using least-privilege credentials
stored in n8n, not in our database. This is not part of M1–M7, because the
brief forbids real external connections in the MVP. See the open question
about Instagram below.

### Rejected or reference-only

- **Dify** is a full LLM-app platform with its own users, workflows, and RAG.
  It would duplicate most of our core, and its licence restricts multi-tenant
  use. Rejected.
- **Open WebUI** has a custom licence with branding requirements. It is useful
  as a reference for chat UX patterns; no code is copied.
- **Agent Zero** gives the agent a computer/terminal and executes code. That
  conflicts directly with the non-negotiable rule that model output never runs
  arbitrary code. Its tool-description patterns may inform the typed tool
  registry; it will not be run.
- **Khoj** is **AGPL-3.0**. It is a reference for document search UX in M6
  only.

## Result for this repository

No third-party agent framework is a runtime dependency in M1. All code here
is original and uses permissively licensed libraries (FastAPI, SQLAlchemy,
Alembic, Next.js, Radix UI, and others pinned in the manifests).

## Update after M2 (chat and memory)

PersonalClaw's memory module was inspected more closely (read-only), and three
of its ideas were adopted in our own code: recall disclosure, one memory
switch that blocks both reading and proposing, and explicit "remember" cues.
See D-019 in [DECISIONS.md](DECISIONS.md). Letta remains unnecessary: keyword
recall over approved memories meets the PRD, and the function can switch to
semantic recall later without changing the API.
