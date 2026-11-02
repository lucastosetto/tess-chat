# Architecture

```
            React SPA (Vite)                    public page /s/{token}
                  │  REST + SSE (/api)                 │
                  ▼                                    ▼
 ┌──────────────── adapters/http (FastAPI) ─────────────────────────┐
 │ routes · auth cookie · rate limits · body limits · error mapping │
 └───────────────────────────────┬──────────────────────────────────┘
                                 ▼
 ┌──────────────── application (use cases + ports) ─────────────────┐
 │ SendMessage agent loop ── ToolRegistry ◄── UserToolSource        │
 │ sharing · agents · mcp · connections · export · admin · credits  │
 │ ports: LLMProvider, UnitOfWork, repositories, McpGateway,        │
 │        GoogleWorkspace, SecretBox, EventBus, Tracer              │
 └───────────────────────────────┬──────────────────────────────────┘
                                 ▼
 ┌──────────────── domain (stdlib only) ────────────────────────────┐
 │ Conversation · Message · CreditLedger · ShareLink · Agent        │
 │ McpServer · Connection · domain events                           │
 └──────────────────────────────────────────────────────────────────┘
 adapters: SQLAlchemy (Postgres) · Gemini/Groq with fallback · Tavily ·
           HttpMcpGateway · GoogleWorkspaceClient · FernetSecretBox ·
           AuditSubscriber · OpenTelemetry
```

## Rules

- `domain` imports nothing outside the standard library. `application` never imports FastAPI, SQLAlchemy, httpx, structlog or config. `import-linter` enforces both in CI.
- `main.py` is the only place that builds adapters and wires use cases.
- Every write goes through a `UnitOfWork`; domain events are published in the same transaction and `AuditSubscriber` writes `audit_events`.

## Chat turn

1. `SendMessage` loads the conversation and, if set, its agent (instructions, default model, allowed tool groups). In `edit` or `regenerate` mode the last turn is marked superseded first.
2. Credits are reserved, then the tool registry is built: built-in tools plus each `UserToolSource` (enabled MCP servers, connected Google products), filtered by the agent's tool groups.
3. The agent loop streams model output over SSE and runs tool calls (up to a fixed number of rounds). Old messages are replaced by a summary when the context grows.
4. Credits are settled by tokens used, or released on failure. Usage, tool calls and cost are saved on the message.

## Tools from integrations

- **MCP**: on register or refresh the server's `tools/list` is cached on its row. At chat time each tool becomes `mcp_{server}__{tool}` and runs `tools/call` on a new session. Headers are sealed with the secret box.
- **Google**: OAuth with `include_granted_scopes`, so Drive and Gmail are granted one at a time. The refresh token is sealed; access tokens are refreshed when needed. Tools appear only for granted scopes.

## Share links

A link stores a hash of a random token. The public endpoint returns only messages created before the link, without cost or usage. Attachments are served through `/api/shared/{token}/attachments/{id}` after checking that the attachment belongs to one of those messages. Revoking or rotating the link stops it at once.

## Limits and secrets

- In-memory sliding-window rate limiter per user (or IP when signed out), per bucket: chat, upload, write, public.
- ASGI middleware rejects bodies over 256 KB (JSON) or the PDF limit (uploads) with 413.
- `FernetSecretBox` key: SHA-256 of `SECRETS_KEY` (falls back to `SESSION_SECRET`).
- Outbound fetches (URL tool, MCP) block private and loopback addresses.
