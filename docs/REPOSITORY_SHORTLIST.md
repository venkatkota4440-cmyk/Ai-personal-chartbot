# Personal AI Agent Platform --- Repository Research Pack

**Prepared:** 16 October 2026\
**Purpose:** Share this file with Claude Code to evaluate open-source
repositories and plan a safe, unified personal AI agent platform.

## 1. Project goal

Build a personal AI agent platform for desktop and mobile that can help
with: - Personal assistant conversations and useful long-term memory -
Learning and coding support - Research and document understanding -
Projects, tasks, goals, and daily briefings - Scheduled and
event-triggered workflows - Integrations with approved apps and
services - A managed workspace for the ScamShield AI project -
Permission controls: routine low-risk work may run automatically;
important/external/destructive actions require approval

The product should have a polished, responsive interface, a persistent
database, observable automation runs, and secure tool execution. Do not
assume any repository is production-ready without inspection.

## 2. Repository shortlist

These are separate projects. This list is a research shortlist, not a
claim that they have been tested together or that all are
maintained/compatible with one another. Verify each repository's current
README, license, latest releases, open issues, security posture,
deployment needs, and API before choosing it.

  --------------------------------------------------------------------------------------------------------------------
  \#                Repository        Main area to evaluate Link
  ----------------- ----------------- --------------------- ----------------------------------------------------------
  1                 PersonalClaw      Potential             https://github.com/PersonalClaw/PersonalClaw
                                      personal-agent        
                                      foundation:           
                                      assistant, memory,    
                                      tasks, tools          

  2                 MIRA              Self-hosted personal  https://github.com/Vexillon-ai/MIRA
                                      assistant, memory,    
                                      messaging and         
                                      automation            

  3                 Letta             Stateful agents and   https://github.com/letta-ai/letta
                                      long-term memory      

  4                 LangGraph         Stateful, multi-step  https://github.com/langchain-ai/langgraph
                                      agent orchestration   
                                      and human approval    
                                      checkpoints           

  5                 n8n               Workflow automation,  https://github.com/n8n-io/n8n
                                      schedules, and        
                                      service integrations  

  6                 Dify              LLM applications,     https://github.com/langgenius/dify
                                      visual AI workflows,  
                                      tools, and document   
                                      retrieval             

  7                 Open WebUI        Self-hosted AI chat   https://github.com/open-webui/open-webui
                                      interface and model   
                                      integration reference 

  8                 Agent Zero        Extensible agent      https://github.com/agent0ai/agent-zero
                                      framework and         
                                      computer/tool-use     
                                      patterns              

  9                 Khoj              Personal knowledge    https://github.com/khoj-ai/khoj
                                      assistant and search  
                                      over                  
                                      documents/knowledge   

  10                Awesome Personal  Curated discovery     https://github.com/elyase/awesome-personal-ai-assistants
                    AI Assistants     list for finding      
                                      additional options    
  --------------------------------------------------------------------------------------------------------------------

## 3. Suggested evaluation strategy

Do not clone and combine all ten projects blindly. First inspect the
current codebase and then compare candidate projects.

### Evaluate first

1.  **PersonalClaw and MIRA:** compare as possible foundations; choose
    at most one unless there is a clear technical reason to combine
    them.
2.  **LangGraph:** evaluate if custom agent orchestration, durable
    state, and approval checkpoints are needed.
3.  **Letta:** evaluate as a dedicated memory service only if the chosen
    foundation's memory is insufficient.
4.  **n8n:** evaluate for integrations and scheduled workflows rather
    than writing every connector from scratch.
5.  **Khoj or Dify:** evaluate for document search and retrieval
    workflows.
6.  **Open WebUI:** use as a UI reference or optional component; do not
    replace an existing frontend unless that is the best fit.
7.  **Agent Zero:** inspect in a sandbox if computer-use or tool-use
    patterns are relevant.
8.  **Awesome Personal AI Assistants:** use as a discovery list, not as
    a dependency.

### Architecture principle

Prefer a small number of clear components over a large collection of
overlapping agent frameworks. Keep one source of truth for users,
projects, tasks, permissions, and audit events. Integrate through
documented APIs where practical.

## 4. Target architecture

-   **Frontend:** existing frontend if viable; otherwise Next.js/React +
    TypeScript with responsive mobile and desktop layouts.
-   **Backend API:** FastAPI/Python or the existing backend, with
    authentication and request validation.
-   **Database:** PostgreSQL for deployed environments; SQLite only for
    a local prototype.
-   **Agent orchestration:** evaluate LangGraph or a framework already
    included in the selected foundation.
-   **Memory:** user-controlled persistent memory with
    view/edit/delete/export options.
-   **Automation:** a scheduler and background worker; evaluate n8n for
    external integrations.
-   **Tool gateway:** typed, allowlisted tools; never let model output
    execute arbitrary shell commands or code directly.
-   **Approval service:** high-risk actions pause until the user
    approves the exact proposed action.
-   **Audit trail:** record run IDs, action, target, status, timestamps,
    and sanitized errors.
-   **Files:** private file storage, input validation, and safe document
    parsing.
-   **Observability:** structured logs, health checks, bounded retries,
    timeouts, and usage limits.

## 5. Mandatory safety requirements

1.  Treat web pages, emails, documents, and tool results as untrusted
    content; they must not override system or user instructions.
2.  Require explicit, one-time approval immediately before sending
    messages, publishing, externally sharing files, deleting data,
    spending money, or changing account/security settings.
3.  Display the exact target and content/action in the approval screen.
    Bind approval to the exact action payload and expire approvals.
4.  Use least-privilege connector scopes. Provide a way to disconnect
    integrations and revoke credentials.
5.  Keep API keys and secrets on the server; never put them in browser
    code, public repositories, screenshots, or logs.
6.  Add authentication, per-user authorization, rate limits, input
    validation, timeouts, step limits, and bounded retries.
7.  Use idempotency keys and locking to prevent duplicate scheduled
    actions.
8.  Keep an audit trail without logging passwords, tokens, or
    unnecessary sensitive content.
9.  Start with synthetic/demo data and read-only integrations. Test
    before enabling live actions.
10. Never claim a workflow completed unless the backend confirms its
    result.

## 6. Claude Code task prompt

Copy the prompt below into Claude Code after providing this file. If the
codebase is available in the current workspace, inspect it before making
changes.

------------------------------------------------------------------------

**Prompt for Claude Code**

Act as a principal software architect, senior full-stack engineer, AI
agent engineer, and application security reviewer.

I want to build a personal AI agent platform using the repository
shortlist in this document. Do not assume the listed repositories are
compatible or safe to combine.

### Step 1 --- Inspect before changing anything

-   Inspect the existing workspace, its README, package manifests,
    folder structure, environment configuration, tests, frontend,
    backend, database schema, and current features.
-   Report what is already implemented, what works, what is incomplete,
    and what must not be overwritten.
-   Do not expose secrets. Do not print environment variable values or
    credentials.

### Step 2 --- Evaluate the repositories

For each candidate that is relevant: - Verify the repository URL,
license, maintenance activity, releases, dependencies, deployment
requirements, security considerations, and integration interface using
available repository files or reliable current sources. - Summarize its
strengths, weaknesses, and whether it should be adopted, integrated by
API, used only as a reference, or rejected. - Do not invent features or
claim that code has been tested if it has not. - Prefer a small
architecture with minimal overlapping frameworks.

### Step 3 --- Recommend one architecture

The platform must support: - Personal AI chat and conversation history -
Persistent, user-controlled memory - Projects, goals, and task
management - Coding and research assistance - Document search and
summarization - Scheduled and event-triggered workflows - Automation run
history, notifications, cancellation where safe, and error handling - A
ScamShield AI project workspace - Responsive desktop and mobile UI -
Human approval for important actions

Recommend a primary foundation and explain why. Show component
boundaries and data flow. Keep the existing stack if it is sound; do not
rewrite everything without a concrete reason.

### Step 4 --- Make an implementation plan

Create a phased plan with: - Files and modules to add or modify -
Database migrations and entities - API endpoints and request/response
schemas - Background scheduler/worker approach - Memory retrieval and
editing controls - Tool registry and policy/approval service - Frontend
routes and UI states - Testing and deployment steps - Risks,
dependencies, and acceptance criteria

### Step 5 --- Implement incrementally

-   Start with a short plan and identify any blocker before modifying
    files.
-   Implement one milestone at a time.
-   Preserve existing working functionality.
-   Use typed interfaces, input validation, error states, and
    migrations.
-   Add automated tests for new behavior.
-   Do not add real credentials or connect live external accounts
    without my explicit approval.
-   Do not send messages, publish content, delete data, spend money, or
    change production settings without approval.
-   Use placeholders in `.env.example`; never commit actual secrets.

### Step 6 --- Verify and report

Run relevant tests and lint/type checks that are available. Clearly
separate: - Completed and verified - Implemented but not tested -
Blocked or still required

Give exact local run commands, required environment variable names (not
their values), migration steps, test commands, and deployment notes. Do
not claim production readiness unless the required security,
reliability, and recovery controls have been validated.

Start by inspecting the current workspace and returning the audit plus
recommended architecture. Do not make broad changes before that report.

------------------------------------------------------------------------

## 7. Acceptance checklist

-   [ ] Existing codebase audited before changes
-   [ ] Repository licenses and maintenance checked
-   [ ] One primary architecture selected
-   [ ] Authentication and per-user authorization work
-   [ ] Memory can be viewed, edited, and deleted by the user
-   [ ] Projects and tasks persist across restarts
-   [ ] Automation runs have unique IDs and visible statuses
-   [ ] High-risk actions pause for explicit approval
-   [ ] Duplicate scheduled runs are prevented
-   [ ] Errors, timeouts, retries, and cancellation are handled
-   [ ] Secrets are not exposed to the frontend or logs
-   [ ] Unit, integration, security, and end-to-end tests are added
-   [ ] Backup, restore, deployment, and rollback steps are documented

## 8. Final reminder

This document is a repository evaluation and implementation brief. It is
not a bundled copy of the source code for the listed projects. Review
each project's license and requirements before downloading, deploying,
or redistributing it.
