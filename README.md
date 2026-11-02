# Tess Chat

Multi-conversation AI chat with streaming, credits and an audit trail. FastAPI (hexagonal) + React, deployed on Cloud Run with Neon Postgres.

**Live demo:** https://tess-chat-320840833152.us-central1.run.app

> The demo runs on free tiers and may be offline or out of credits. If you'd like to try it, reach out to me at morvillolucas@gmail.com and I'll bring it up for you.

## Features

- Multiple conversations with SSE streaming, model picker (Gemini, Groq) with fallback, reasoning effort, LLM auto-titles.
- Tools: web search, URL fetch, Google Drive and Gmail (read-only), and any remote MCP server the user registers.
- Image and PDF attachments, context compaction, credits with a per-user and global cap, audit trail and an Activity page.
- Share links: public read-only snapshot at `/s/{token}`, revocable, attachments proxied through the token.
- Custom agents (instructions, default model, allowed tools), regenerate and edit the last message, export to Markdown or JSON, admin view at `/admin` (usage per user, top tools, failures).
- Hardening: per-user rate limits, request body limits, Fernet encryption of stored secrets (MCP headers, Google refresh tokens), SSRF guard on outbound fetches.

Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Progress and decisions: [docs/STATUS.md](docs/STATUS.md).

## Run locally

```bash
docker compose up -d
cd backend
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run python -m tess_chat.main
```

```bash
cd frontend
pnpm install
pnpm dev
```

Open http://localhost:5173. Without LLM keys the backend answers with a fake provider.

### Google Drive and Gmail

The OAuth client needs the redirect URI `{origin}/api/connections/google/callback`, the `drive.readonly` and `gmail.readonly` scopes on the consent screen (test users added while the app is unverified), and the Drive and Gmail APIs enabled (`infra/main/apis.tf`).

### Environment

See `backend/.env.example`. `SECRETS_KEY` encrypts stored secrets and falls back to `SESSION_SECRET`; changing it makes saved MCP headers and Google tokens unreadable. `RATE_LIMIT_*_PER_MINUTE` tune the limits; they are kept in memory per instance.

## Checks

```bash
cd backend
uv run ruff check . && uv run mypy && uv run lint-imports
TEST_DATABASE_URL=postgresql://tess:tess@localhost:5433/tess_test uv run pytest
cd ../frontend && npx tsc -b && npx eslint src
```

## Layout

- `backend/src/tess_chat/domain`: entities, credit ledger, domain events. Standard library only.
- `backend/src/tess_chat/application`: ports (`LLMProvider`, repositories, `UnitOfWork`, `EventBus`) and use cases.
- `backend/src/tess_chat/adapters`: FastAPI, SQLAlchemy, Gemini/Groq (OpenAI-compatible) with fallback, MCP client, Google Workspace client, Fernet secret box, event bus and audit.
- `backend/src/tess_chat/main.py`: composition root.
- `import-linter` enforces the layering in CI.

## Deploy

Push to `main` runs CI, builds the image, runs `alembic upgrade head` as a Cloud Run job and deploys the service, authenticating through Workload Identity Federation. Infrastructure lives in `infra/` (Terraform).
