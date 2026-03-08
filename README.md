# Finance Assistant API

A personal finance backend that exposes a REST API and an MCP (Model Context Protocol) server for managing transactions, accounts, and financial summaries. The application has no LLM or conversational features of its own — its agentic surface is MCP, automatically exposed from the same FastAPI routes.

## What This Application Does

- **Manages financial transactions and accounts** stored in a PostgreSQL database.
- **Exposes a REST API** (FastAPI) for direct programmatic access from frontends or other services.
- **Exposes an MCP server** (FastApiMCP) so that AI agents can discover and call tools generated directly from REST endpoints.
- Provides **financial summaries and aggregations**: monthly breakdowns, spending distributions by category or account, balance trends, and account breakdowns by asset type.

## Core Technologies

| Technology | Role |
|---|---|
| **Python 3.13** | Runtime |
| **FastAPI** | REST API framework |
| **PostgreSQL** | Primary database |
| **SQLAlchemy** | ORM and database session management |
| **Alembic** | Database schema migrations |
| **FastApiMCP** (`fastapi-mcp`) | Auto-generates MCP tools from FastAPI routes |
| **Uvicorn** | ASGI server |
| **Pipenv** | Dependency management |

## Project Structure

```
finance-assistant-api/
├── app.py                # FastAPI application entrypoint
├── src/
│   ├── api/
│   │   ├── routes/        # Domain-based REST route modules
│   │   └── models/        # Pydantic API schemas
│   ├── services/          # Business logic layer
│   ├── repositories/      # Data access layer (SQLAlchemy)
│   ├── database/          # DB initialisation, session management, ORM models
│   └── config/            # Database configuration
├── migrations/            # Alembic migration scripts
├── tests/                 # Test suite
├── docs/                  # Extended documentation
├── Dockerfile
├── Pipfile
└── .env.example
```

## Setup

### 1. Install Dependencies

```bash
pipenv install
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in the required values:

```bash
cp .env.example .env
```

See the [Environment Variables](#environment-variables) section below for a full description of each variable.

### 3. Database Migrations

In `development` mode the application creates tables automatically on first run. To apply Alembic migrations explicitly:

```bash
pipenv run alembic upgrade head
```

## Starting the Application

### REST API

```bash
uvicorn app:app --reload
```

The API is available at `http://localhost:8000`.  
Interactive Swagger docs: `http://localhost:8000/docs`

### MCP Server

```bash
python3 app.py
```

This starts the FastAPI app and also mounts MCP via FastApiMCP. Your microservice (or any MCP-compatible client) can connect to the mounted MCP HTTP endpoint and discover tools generated from the REST routes.

### Docker

```bash
docker build -t finance-assistant-api .
docker run -p 8080:8080 --env-file .env finance-assistant-api
```

The container runs uvicorn on port **8080** (the default for Google Cloud Run). The API is then accessible at `http://localhost:8080`.

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DB_HOST` | Yes | — | PostgreSQL host |
| `DB_PORT` | Yes | — | PostgreSQL port |
| `DB_NAME` | Yes | — | Database name |
| `DB_USER` | Yes | — | Database user |
| `DB_PASSWORD` | Yes | — | Database password |
| `DB_SSL_MODE` | No | `require` | SSL mode (`require` / `disable`) |
| `ENVIRONMENT` | No | `development` | Set to `production` to disable auto table creation |
| `USE_DATABASE` | No | `true` | Set to `false` to use an in-memory SQLite instance instead of PostgreSQL |
| `OPENAI_API_KEY` | No | — | Not used by the application itself; kept for forward compatibility |

> **Note**: When `USE_DATABASE=false` or the PostgreSQL connection fails, the application automatically falls back to an in-memory SQLite database. This is convenient for local development without a running Postgres instance.



### Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Returns `{"status": "healthy"}` |

### Transactions

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/transactions` | List transactions. Query params: `category`, `start_date` (YYYY-MM-DD), `end_date` (YYYY-MM-DD), `account_id` |
| `POST` | `/api/transactions` | Create a transaction. Use negative `amount` for expenses, positive for income |
| `POST` | `/api/transactions/bulk` | Bulk-create transactions from an array |
| `PUT` | `/api/transactions/{transaction_id}` | Partially update a transaction |
| `DELETE` | `/api/transactions/{transaction_id}` | Delete a transaction |
| `GET` | `/api/transactions/balance` | Get the total balance (sum of all transaction amounts) |

### Accounts

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/accounts` | List accounts. Query param: `active_only` (default `true`) |
| `GET` | `/api/accounts/{account_id}` | Get a single account |
| `POST` | `/api/accounts` | Create an account |
| `PUT` | `/api/accounts/{account_id}` | Partially update an account |
| `DELETE` | `/api/accounts/{account_id}` | Deactivate an account (soft delete) |
| `GET` | `/api/accounts/{account_id}/balance` | Get the balance for a specific account |

### Financial Data

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/financial-data/{year}` | Aggregated yearly data: net worth, net savings, month-by-month breakdown, account breakdown |

### Financial Summaries

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/financial-summary/monthly/{month}` | Monthly summary for `YYYY-MM`: total income, expenses, net, and top 5 spending categories |
| `GET` | `/api/financial-summary/spending-distribution` | Spending distribution for a date range. Query params: `start_date`, `end_date`, `group_by` (`category` or `account`) |
| `GET` | `/api/financial-summary/account-breakdown` | Current balances grouped by asset type (liquidity / investments / other) |

## MCP Server

MCP is mounted directly from [app.py](app.py) via FastApiMCP:

- The wrapper converts FastAPI route handlers into MCP tools.
- Tool names mirror route handler names.
- REST and MCP stay aligned by design (single source of truth: route layer + services).
- The duplicated standalone MCP implementation is no longer required for primary usage.

### How It Works

1. Start the app with `python3 app.py`.
2. FastApiMCP mounts MCP HTTP endpoints on the same app.
3. Your microservice connects to the MCP endpoint, lists available tools, and invokes them.
4. Each tool execution calls the same route/service path used by REST, so behavior remains consistent.

### Available Tools

Tools are auto-generated from route handlers, so every endpoint method becomes a corresponding MCP tool with the same naming.

### Connecting from Another Microservice

Use an MCP client in your microservice and point it to the Finance Assistant MCP SSE endpoint.

Example high-level flow:

1. Start Finance Assistant: `python3 app.py`.
2. Configure your microservice MCP client with the MCP URL exposed by FastApiMCP on the same host/port.
3. Connect, discover tools, and invoke them with JSON arguments.

Your microservice is then the integration layer for any downstream agent or application.

## Running Tests

```bash
python -m pytest tests/ -v
```