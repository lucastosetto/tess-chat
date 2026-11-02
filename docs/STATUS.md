# Status

Read with `docs/PLAN.md`. Decisions here override the plan where they differ.

## Deadline

Monday 11/02 12:00 (confirmed). Everything (deployed app, docs, video) done by Saturday 10/31.

## Decisions made after PLAN.md

- **LLM:** Gemini (free tier) is the primary provider; Groq (open-source models, free tier) is the fallback on 429/5xx via a `FallbackLLMProvider` (chain of responsibility over the `LLMProvider` port). Skip the fallback when the turn has PDFs or images that the Groq model cannot handle. Claude is optional, used only if Gemini quality is too poor. Tests use a fake provider.
- **Database:** Postgres on Neon (free). Not Firestore: the credit ledger needs ACID transactions, and audit/usage needs aggregations and foreign keys.
- **Infra as code:** Terraform in `infra/` (see `infra/README.md`).
- **Repo:** `lucastosetto/tess-chat`, private. Add the evaluators as collaborators before delivery.

## Infrastructure (applied)

- **GCP project:** `tess-chat-19db69` in org `morvillolucas-org`; billing "LTM - Dev"; budget alert R$ 5.
- **gcloud:** config `tess`, account `morvillolucas@gmail.com`.
- **Terraform auth:** ADC points to a work account, so run with `GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token --account=morvillolucas@gmail.com)`.
- **Bootstrap state:** local only, in `infra/bootstrap/terraform.tfstate` (gitignored).
- **`infra/main`** (GCS state) holds:
  - APIs;
  - Artifact Registry `us-central1-docker.pkg.dev/tess-chat-19db69/tess-chat`;
  - bucket `tess-chat-19db69-attachments`;
  - runtime service account `tess-chat-runtime@`;
  - Secret Manager.
- **Gated on variables:**
  - Cloud Run: `deploy_service = false` until it is ready.
  - GitHub Workload Identity Federation: needs `github_repo = "lucastosetto/tess-chat"`.
- **Secrets and env vars:** Cloud Run maps each secret name to an env var (upper-case, `-` → `_`).

| Secret | Status |
|---|---|
| gemini-api-key | set |
| groq-api-key | set |
| tavily-api-key | set |
| database-url | set (Neon direct, no pooler) |
| session-secret | set |
| anthropic-api-key | empty (optional) |
| google-oauth-client-id / -secret | set |
| smtp-password | set (Gmail app password for sign-in links) |

## Neon

- **Project:** `mute-grass-71956150`, branch `production`, AWS us-east-2, Postgres 18.
- **Connection:**
  - Use the direct URL; asyncpg breaks with the PgBouncer pooler.
  - Settings must convert `postgresql://...?sslmode=require&channel_binding=require` to `postgresql+asyncpg://` and pass SSL via connect args.
- **Local env:** `.env` holds `DATABASE_URL` (Neon). Local dev and tests should use docker compose Postgres instead.
- **Agent skills:** installed in `.claude/skills/`.

## Day 1 progress (10/29)

- Backend: uv project, ruff, mypy strict, pytest, import-linter (3 contracts), docker compose Postgres on port 5433 (5432 is taken by an SSH tunnel locally), `tess_test` database for tests.
- Domain, use cases, SQLAlchemy async + Alembic `0001_initial` (users, conversations, messages, credit_ledger, model_pricing, audit_events).
- Dev login (`AUTH_DEV_MODE`), signed JWT cookie.
- SSE chat through `LLMProvider`: Gemini and Groq via one OpenAI-compatible adapter, `FallbackLLMProvider` falls back on any error before the first chunk.
- Models: `gemini-3.5-flash` (`gemini-2.5-flash` is retired for new users, `gemini-3.8-flash` was timing out under load) and Groq `openai/gpt-oss-120b` (`llama-3.3-70b-versatile` is gone).
- Event bus + AuditSubscriber in the same transaction; credits reserve → settle/release.
- Frontend: Vite + React + TanStack Query, login, sidebar, streaming chat with Markdown.
- Dockerfile (SPA served by the API), `.github/workflows/ci.yml` (checks, build, migrate job, deploy).
- Terraform: `auth_dev_mode` and `unset_secrets` variables added; `terraform.tfvars` sets `github_repo`, `deploy_service = true`, `auth_dev_mode = true`.

## Day 2 progress (10/29)

- Model picker (Auto or a fixed model, which skips the fallback) and reasoning effort per conversation; ACP-style pickers.
- Auto-title by the LLM after the first reply, charged in credits, streamed as an SSE `title` event.
- Sign-in: Google OAuth (code flow, state cookie, verified email only) and email magic link (single use, 15 min, hashed token, 5 per 15 min per email, SMTP via Gmail). Dev login removed.

## Day 3 progress (11/01)

- R5 share links: snapshot of the messages up to the link's creation, token stored as a hash (URL shown once), creating a new link revokes the old one, public page `/s/{token}` outside the auth gate, attachments proxied through the token, `no-store` and `noindex` headers.
- D1 MCP: streamable HTTP client (JSON and SSE responses, `Mcp-Session-Id`, paginated `tools/list`, 2 MB cap, private IP block). Tools are cached on the server row, exposed as `mcp_{server}__{tool}`, and run through the `ToolRegistry`. Headers are encrypted. Tested against `https://mcp.deepwiki.com/mcp`.
- D2 Google: incremental OAuth (Drive and Gmail scopes requested separately), refresh token encrypted, access token refreshed lazily; tools `drive_search`, `drive_read` (Docs, Sheets, Slides, PDF, text), `gmail_search`, `gmail_read`. Real consent not tested yet: it needs the redirect URI, scopes and APIs set up in GCP.
- D8 custom agents: instructions, default model and allowed tool groups (`web`, `drive`, `gmail`, `mcp:{server}`, or all). Chosen from the same composer menu as the model.
- D9 admin view (`/admin`, admins from `ADMIN_EMAILS` at sign-up): usage per user, top tools with failed calls, failed replies by error.
- D6 regenerate the last reply and edit the last user message. Replaced messages get `superseded_at`, stay in the database for audit and are hidden from the chat, share and export; a `message.superseded` audit event is written.
- D5 prompt caching: the system prompt and tools come first and never change inside a chat, so Gemini's implicit cache applies. Cached input tokens are read from the provider, priced at the cached rate in the ledger and shown on each reply.
- D10 export to Markdown or JSON.
- Hardening: rate limits per user (chat 20/min, upload 30/min, writes 60/min, public 120/min; in memory, per instance), body size limits (256 KB JSON, PDF size for uploads), Fernet secret box, `/api/ready` checks the database.
- Migration `0006_shares_mcp_connections_agents` (also `agents.tools` and `messages.superseded_at`).

## Known limits

- Rate limits are per Cloud Run instance; a shared store (Redis) would be needed with more instances.
- Google verification is pending, so only test users can grant Gmail access.

## Next

- Record the demo video.
