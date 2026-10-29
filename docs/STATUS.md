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
| google-oauth-client-id / -secret | empty, set up at end of Day 1 |

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

## Next

- Apply `infra/main` (WIF + Cloud Run), push, verify the deploy.
- Google OAuth (console), then set `auth_dev_mode = false`.
- Day 1 items 9 (model picker, auto-title by LLM) moved to Day 2.
