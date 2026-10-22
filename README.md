# Finance Assistant API 💰

The **Finance Assistant API** is the core backend service for managing personal financial data. It provides a robust set of REST endpoints for tracking transactions, accounts, and generating aggregated financial summaries.

## 🚀 Quick Start

This service is typically run as part of the [Finance Assistant Monorepo](../README.md) using Docker Compose.

### Local Development (with uv)

We use **uv** for high-performance dependency management.

1. Ensure you have [uv](https://github.com/astral-sh/uv) installed.
2. Install dependencies:
   ```bash
   uv sync
   ```
3. Run the development server:
   ```bash
   uv run uvicorn app:app --reload --port 8080
   ```

### Database

SQLite by default (`~/.finance-assistant/finance.db`, or `FINANCE_DB_PATH`). Postgres is used when `DB_PASSWORD` or
`DB_HOST` is set (or `FINANCE_DB=postgres`); the other variables are `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_SSL_MODE`.
The schema is migrated automatically at startup (SQLite, and Postgres unless `ENVIRONMENT=production`).

### Database Migrations (Alembic)

Run by hand for a production Postgres, after taking a dump:
```bash
uv run alembic upgrade head
```

To create a new migration after model changes:
```bash
uv run alembic revision --autogenerate -m "description of changes"
```

## 🛠️ Features

- **Projects (workspaces)**: every request works in one project, chosen with `X-Workspace-Id` (default: the caller's
  project) and identified with `X-User-Id`. Data is isolated per project at the database session.
- **Blueprints**: a validated, versioned document per project (category tree, groups, dimensions, rules, instructions):
  `/api/workspaces/{id}/blueprint`, `.../preview`, `.../export`, `/api/blueprint-templates`, `/api/blueprints/validate`.
- **Transactions and accounts**: CRUD, with provenance on every category (who decided it, confidence, confirmed or not).
- **Imports**: `POST /api/imports` (account required) deduplicates rows against what is stored, records an undoable batch
  and pairs transfers between the user's own accounts; `/api/transfers/*` to adjust them.
- **Review**: `/api/review/queue|confirm|accept|coverage`, merchant rules (`/api/merchant-rules`, `/resolve`).
- **Reports**: `/api/reports/spending` (by category, group, account or month, with `coverage`),
  `/api/reports/category-usage`, plus the summaries used by the dashboard.
- **MCP**: an auto-generated MCP surface is mounted at `/sse`; the agent's curated tool set lives in
  [`../finance-mcp`](../finance-mcp).

## 🐳 Docker

The API is containerized for production and development:
```bash
docker build -t finance-api .
docker run -p 8080:8080 finance-api
```

---
Part of the [Finance Assistant Monorepo](../)