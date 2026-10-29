# Tess Chat — Implementation Plan

Deadline: Monday 2026-11-02, 12:00 BRT (to confirm with Pedro: the email says "Wednesday 02/11").
Budget: 3 days (Thu 10/29 – Sat 10/31). Everything — app deployed, docs and demo video — is done by end of Saturday; Sunday 11/01 it is ready to send. No buffer day: the cut order decides what drops.

## 1. Scope

### Required
| # | Requirement | Where it lives |
|---|---|---|
| R1 | Multiple conversations, persisted history | `Conversation`, `Message` aggregates + Postgres |
| R2 | Tools, incl. web search and scraping | `ToolRegistry` port; `web_search` (Tavily), `fetch_url` (httpx + trafilatura) |
| R3 | Images + vision | Attachments → GCS; sent as image blocks to Claude |
| R4 | PDFs in chat | Attachments → GCS; sent as document blocks to Claude |
| R5 | Share a conversation (read-only) | `ShareLink` with opaque token, public read-only route |
| R6 | Cloud deploy, public URL | Cloud Run + Neon + GCS |
| R7 | Everything persisted in DB | users, conversations, messages, attachments, settings, tools, MCP servers, connectors, credits, audit |
| R8 | Auto-compaction at context limit, no interruption | `CompactionPolicy` + `CompactHistory` use case, run inline before the LLM call |
| R9 | Credit/token cap with usage accounting | Append-only `CreditLedger`, reserve → settle |
| R10 | Full audit trail | Domain events → `AuditEvent` table via event bus |

### Differentials
- D1 MCP: users register remote MCP servers (streamable HTTP); their tools join the registry.
- D2 Google Drive + Gmail connectors (read-only: search/read files, search/read emails).
- D3 Login with Google (same OAuth client as D2, incremental scopes).
- D4 Model picker per conversation (Haiku / Sonnet / Opus) plus effort, priced from `model_pricing`.
- D5 Prompt caching on system prompt, tools and history; cache read/write tokens recorded and priced in the ledger.
- D6 Regenerate and edit the last user message (the old branch is kept for audit and marked superseded).
- D7 Auto-title conversations with Haiku after the first reply (charged and audited).
- D8 Custom agents: saved system prompt + enabled tools + model, selectable when a conversation starts.
- D9 Admin usage view: tokens/credits per user, top tools, failures (role `admin` from `ADMIN_EMAILS`).
- D10 Export a conversation as Markdown or JSON.
- D11 OpenTelemetry traces for the agent loop (LLM call, each tool, compaction) exported to Cloud Trace, with `trace_id` in logs and audit rows.

### Reused from ACP (`agents-control-plane/panel/static/index.html`, `panel/server.py`)
- Design tokens, fonts, light/dark theme, markdown rendering (marked + DOMPurify + highlight.js).
- Composer model + effort selector (D4).
- Token/cost math including `cache_read_input_tokens` / `cache_creation_input_tokens` (D5, R9) — port the formula into `domain/credits.py`.
- Usage-by-account screen layout (D9).
- Tool-call labels (`toolLabel`: "Server: action" for MCP tools) and the tool approval card styling (R2, D1).
- Conversation titles in the sidebar and the context-size warning (D7, R8).

Ported as code adapted to the new architecture, not copied wholesale: ACP is stdlib + one HTML file, this project is React + hexagonal backend.

### Out of scope
Multi-provider runtime (port ready, Claude only), billing/payments, team workspaces, local stdio MCP servers.

## 2. Stack

- Backend: Python 3.12, FastAPI, Pydantic v2, pydantic-settings, SQLAlchemy 2 (async) + asyncpg, Alembic, `anthropic`, `mcp` SDK, httpx, trafilatura, structlog, OpenTelemetry (optional), pytest + pytest-asyncio + testcontainers, ruff + mypy, uv.
- Frontend: React + Vite + TypeScript, TanStack Query, react-router, marked + DOMPurify + highlight.js. Design tokens, fonts (Instrument Sans, JetBrains Mono) and chat UI patterns from ACP.
- Infra: Docker (one image: API serves the built SPA), Cloud Run, Neon Postgres (free), GCS bucket (5 GB free, US region), Secret Manager, GitHub Actions (lint, type check, tests, build, deploy).

## 3. Architecture (hexagonal)

```
backend/src/tess_chat/
  domain/            # entities, value objects, domain events, policies — no I/O imports
    conversation.py  message.py  attachment.py  share.py  user.py
    credits.py       # CreditLedger, Reservation, pricing
    compaction.py    # CompactionPolicy (threshold, keep-recent window)
    audit.py  events.py  errors.py
  application/
    ports/           # Protocols: LLMProvider, Tool, ToolRegistry, FileStorage, TokenCounter,
                     # repositories, UnitOfWork, EventBus, Clock, IdGenerator, OAuthClient
    use_cases/       # SendMessage, CreateConversation, RenameConversation, DeleteConversation,
                     # UploadAttachment, ShareConversation, RevokeShare, ViewSharedConversation,
                     # CompactHistory, RegisterMcpServer, ConnectGoogle, GetUsage, ListAudit
    dto.py
  adapters/
    http/            # FastAPI routers, schemas, SSE streaming, auth dependency, error mapping
    persistence/     # SQLAlchemy models, repositories, UnitOfWork, Alembic migrations
    llm/anthropic.py # LLMProvider + TokenCounter (count_tokens API)
    tools/           # web_search.py, fetch_url.py, mcp_tools.py, google_drive.py, gmail.py
    storage/gcs.py   storage/local.py
    auth/google_oauth.py  auth/session.py (signed JWT cookie)
    events/          # in-process EventBus, AuditSubscriber
  config.py          # Settings from env (12-factor)
  main.py            # composition root: wires adapters into use cases (DI container)
frontend/
infra/               # Dockerfile, cloudbuild/gh workflow, Terraform-lite scripts or gcloud commands
docs/                # PLAN.md, ARCHITECTURE.md, ADRs
```

Rules: `domain` imports nothing outside stdlib; `application` imports `domain` + its own ports; only `adapters` and `main.py` touch frameworks. An import-linter contract enforces this in CI.

Patterns: Ports & Adapters, Repository + Unit of Work, Strategy (LLM provider, tools, storage), Observer/Event Bus (audit, usage), Factory/composition root for DI, Template Method for the agent loop steps, Value Objects for money/tokens.

12-factor: config only via env (`Settings`), backing services as attached resources (DB/GCS/LLM by URL/credentials), stateless processes (no local disk state; sessions in signed cookies, everything else in DB), JSON logs to stdout, dev/prod parity via docker compose (Postgres + fake GCS/local storage), migrations as an explicit admin step (`alembic upgrade head` as a Cloud Run job before the new revision), port binding via `$PORT`.

## 4. Key flows

### SendMessage (agent loop)
1. Load conversation (ownership check) inside a UoW.
2. Credit check: `CreditLedger.reserve(estimate)`; refuse with 402-style error if cap reached.
3. Build context: summary checkpoint (if any) + messages after it + new user message with attachments.
4. Count tokens; if over `threshold = 0.8 * model_context`, run `CompactHistory` inline (status event "compacting" on the SSE stream), then rebuild context. The user never sees an error.
5. Stream from Claude with the user's enabled tools. On `tool_use`: execute via `ToolRegistry` (timeout, output truncation), persist tool call + result as messages, emit audit events, loop (max N iterations).
6. Persist assistant message, settle the reservation with real usage (input, output, cache tokens × price table), emit `MessageCompleted`, `CreditsConsumed`.
7. Any failure: release reservation, persist error state, audit `MessageFailed`.

### Compaction
- Older messages (all except the last K turns) are summarized by Claude with a structured prompt (goals, facts, decisions, open threads, attachment references).
- Stored as a `ContextCheckpoint` row pointing to the last covered message; the original messages stay in DB and in the UI. Context building starts from the latest checkpoint. Compaction cost is charged to credits and audited.

### Sharing
- `ShareLink(token, conversation_id, created_by, revoked_at)`; public route `/s/{token}` renders a read-only view (messages up to share time, or live — decide: live, read-only). Attachments served via short-lived signed URLs.

### Credits
- Each user starts with a configurable grant (`DEFAULT_CREDIT_GRANT`), plus a global cap (`GLOBAL_CREDIT_CAP`) to protect the API key.
- Ledger entries: `grant`, `reserve`, `settle`, `release`. Balance = sum. Pricing table per model in DB (seeded).
- UI: balance badge, per-conversation and per-message usage.

### Audit
- Every use case emits domain events; `AuditSubscriber` writes `audit_events(id, at, actor_id, action, subject_type, subject_id, payload jsonb, request_id)` in the same transaction.
- Covered: login/logout, conversation CRUD, message sent/completed/failed, tool invoked/succeeded/failed, compaction, attachment uploaded, share created/viewed/revoked, MCP server added/removed, connector linked/unlinked, credits granted/reserved/settled, cap reached.
- UI: "Activity" page per user; request_id correlates with logs.

### Tools / MCP / connectors
- `Tool` port: `name`, `description`, `input_schema`, `async run(args, ctx)`.
- Built-in tools are rows in `tools` (enabled per user in settings).
- MCP: user adds a server (URL + optional auth header, secrets encrypted with a KMS-derived key); on connect we list tools and cache them in DB; calls go through the MCP client session.
- Google: OAuth with incremental scopes (`drive.readonly`, `gmail.readonly`); tokens encrypted at rest; app in testing mode with evaluators added as test users.

## 5. Data model (initial migration)

users (role), user_settings, agents, conversations, messages (role, content jsonb blocks, token usage, status), attachments (gcs key, mime, size, kind), context_checkpoints, share_links, tools, user_tools, mcp_servers, mcp_server_tools, oauth_connections, credit_ledger, model_pricing, audit_events.

## 6. Task breakdown

### Day 1 — Thu 10/29: foundation + core chat (R1, R7, R9 base, R10 base)
1. Repo, uv project, ruff/mypy/pytest, import-linter contract, pre-commit, docker compose (Postgres).
2. `Settings`, structlog JSON logging, request_id middleware, error mapping.
3. Domain: Conversation, Message, CreditLedger, AuditEvent, events + unit tests.
4. Persistence: SQLAlchemy models, repositories, UoW, Alembic initial migration.
5. Google login (OAuth code flow) + signed session cookie + `current_user` dependency. Dev fallback login behind `AUTH_DEV_MODE`.
6. Anthropic adapter with streaming; SendMessage without tools; SSE endpoint.
7. Event bus + AuditSubscriber; credit reserve/settle wired into SendMessage.
8. Frontend scaffold with ACP tokens: login, sidebar with conversations, chat view with streaming + markdown.
9. Model + effort picker in the composer and per-model pricing (D4), auto-title (D7).
10. Deploy skeleton early: Dockerfile, Neon DB, Cloud Run service, GH Actions deploy. Public URL works end of day.

### Day 2 — Fri 10/30: tools, files, compaction (R2, R3, R4, R8)
1. Tool port, registry, agent loop with tool_use iterations; tool calls rendered in UI (collapsible).
2. `web_search` (Tavily) and `fetch_url` (httpx + trafilatura, size/timeout limits, SSRF guard blocking private IPs).
3. Attachments: upload endpoint, GCS adapter (local adapter for dev), image + PDF blocks to Claude, previews in UI.
4. Token counter + CompactionPolicy + CompactHistory + checkpoints; integration test forcing a low threshold.
5. Usage UI: balance badge, per-message tokens; cap-reached state.
6. Prompt caching breakpoints (D5); regenerate / edit last message (D6).
7. OpenTelemetry setup: spans around LLM, tools, compaction; trace_id in logs and audit (D11).
8. Integration tests (testcontainers Postgres, fake LLM provider).

### Day 3 — Sat 10/31: sharing, audit UI, differentials (R5, R10 UI, D1, D2)
1. Share links: create/revoke, public read-only page, signed attachment URLs.
2. Activity page (audit log with filters).
3. MCP: register server, list/cache tools, execute through registry; settings UI.
4. Google Drive + Gmail tools via incremental OAuth; settings "Connections" UI.
5. Settings page: enabled tools, default model, default system prompt; custom agents CRUD and picker (D8).
6. Admin usage view (D9); export Markdown/JSON (D10).
7. Hardening: rate limit per user, input limits, secret encryption, migrations as Cloud Run job, health/readiness endpoints.

### Sat 10/31 evening: delivery prep (same day)
8. End-to-end pass on the deployed URL; fix blockers only.
9. README (architecture, decisions, how to run, env vars), ARCHITECTURE.md diagram, short ADRs. Written incrementally each day, finalized here.
10. Record the demo video (~3–5 min): login, multi-chat, model picker, web search + scraping, image, PDF, compaction (low threshold demo setting), credits cap, share link in incognito, activity log, MCP, Drive/Gmail, custom agent.

### Sun 11/01: everything ready — send email with URL, video and repo link (deadline is Mon 11/02 12:00).

### Checkpoints
- End of Thu: deployed URL with login, multi-chat, streaming, credits, audit. If not, cut D8–D11 immediately.
- End of Fri: all required items except sharing and audit UI work in prod. If not, cut D2 (Drive/Gmail) too.
- Sat 18:00: feature freeze; only docs, fixes and video after that.

### Cut order if behind
Export → admin view → custom agents → OTel → regenerate/edit → Drive/Gmail → MCP → Activity page polish → rate limiting. Model picker, prompt caching and auto-title stay (cheap, mostly ported from ACP). Required items never get cut.

## 7. Risks
| Risk | Mitigation |
|---|---|
| Google OAuth consent friction | Testing mode + evaluators as test users; dev login fallback disabled in prod |
| Cloud Run cold start in demo | Warm before recording; optional `min-instances=1` for the review week |
| API cost abuse via public URL | Per-user grant + global cap + rate limit |
| SSE through Cloud Run | Request timeout 15 min, heartbeat events |
| Compaction hard to demo | `COMPACTION_THRESHOLD_TOKENS` env override for the demo |

## 8. Open items
- Confirm deadline (Mon 02/11 vs Wed 04/11) with Pedro.
- Anthropic API key and Tavily key (user provides).
- GCP project with billing account (free tier usage expected ~US$0).
