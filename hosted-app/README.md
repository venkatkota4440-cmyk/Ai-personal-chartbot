# Hosted app

The version of the Personal Agent that is actually **live and really posts to
Instagram**. It is not part of the FastAPI/Next.js project in `apps/` — that
project's connectors are still stubs that say "NOT sent".

| File | What it is |
|---|---|
| `agent-app.html` | The whole app: one file, no build step, no dependencies. |
| `how-posting-works.html` | What happens when you approve a post, and where it stops. |
| `run-it-for-real.html` | Earlier guide to running the FastAPI project yourself. |

## How it runs

`agent-app.html` is published as a private Claude Artifact and uses the
viewer's own claude.ai connectors at runtime. It never holds a token: every
external call runs as the signed-in viewer, and the page's code cannot read
their credentials.

Declared runtime capabilities:

- `db` — the shared document store holding tasks, actions, memories, activity,
  messages and settings.
- `user` — who is viewing.
- `sample` — Claude, for chat replies and the low-risk briefings.
- `mcp` — **Postproxy** (`auth_status`, `profiles_list`, `post_publish`,
  `post_status`) and **Google Drive** (`search_files`).

## The safety model, in the code

1. `ACTIONS` classifies each action type. Anything with a `publish` field
   really leaves the app and is always high risk.
2. A high-risk action never runs on its own. It becomes `pending` and waits.
3. `openApproval()` shows the resolved account name and id, the exact arguments
   that will be sent, and a SHA-256 `fingerprint()` of them. The fingerprint is
   sent as Postproxy's `idempotency_key`, so one approval cannot double-post.
4. The account is confirmed once and stored **by its id**, not by a typed
   handle (`confirmed()`). If the connected account later differs, publishing
   is blocked, not merely warned about.
5. The connected account is re-checked immediately before the call; if it
   changed since the sheet opened, nothing is sent.
6. `publish()` records what actually happened. Postproxy accepting a job is
   **not** publication, so the action becomes `queued`; only `checkPost()`
   reading a real Instagram status promotes it to `published`. A connector
   failure with an ambiguous outcome (`server_unavailable`, `upstream_error`,
   `cancelled`) is recorded as `unknown`, never as success.

## The scheduler

An hourly Claude scheduled task moves due actions from `scheduled` to
`pending`, and runs the low-risk summaries. It is created **with no
connectors**, so it has no route to Instagram at all — the approval gate is
enforced by its lack of access, not only by its instructions.

## Media

Instagram downloads the file itself, so the media address has to serve bytes:

- Postproxy's own upload host is unreachable from both the artifact sandbox and
  the build container, so in-page uploads are not possible.
- Google Drive's `/thumbnail?id=...&sz=w1080` serves the image directly and
  works, provided the folder is shared as "Anyone with the link". The Drive API
  available here can only share with named people, so that one switch has to be
  set by hand, once.
- A link to a *page* (`instagram.com/reel/...`, Google Photos, `/file/d/.../view`)
  can never work: it returns HTML. `mediaProblem()` rejects these before an
  action is scheduled rather than failing silently later.
