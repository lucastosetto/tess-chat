# Tess Chat

Multi-conversation AI chat with streaming, credits and an audit trail. FastAPI (hexagonal) + React, deployed on Cloud Run with Neon Postgres.

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

## Checks

```bash
cd backend
uv run ruff check . && uv run mypy && uv run lint-imports
TEST_DATABASE_URL=postgresql://tess:tess@localhost:5433/tess_test uv run pytest
```

## Layout

- `backend/src/tess_chat/domain`: entities, credit ledger, domain events. Standard library only.
- `backend/src/tess_chat/application`: ports (`LLMProvider`, repositories, `UnitOfWork`, `EventBus`) and use cases.
- `backend/src/tess_chat/adapters`: FastAPI, SQLAlchemy, Gemini/Groq (OpenAI-compatible) with fallback, event bus and audit.
- `backend/src/tess_chat/main.py`: composition root.
- `import-linter` enforces the layering in CI.

## Deploy

Push to `main` runs CI, builds the image, runs `alembic upgrade head` as a Cloud Run job and deploys the service, authenticating through Workload Identity Federation. Infrastructure lives in `infra/` (Terraform).
