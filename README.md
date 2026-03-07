# Finance Assistant API

A personal finance backend that exposes a REST API and an MCP (Model Context Protocol) server for managing transactions, accounts, and financial summaries. The application has no LLM or conversational features of its own — its agentic surface is the MCP server, which lets any compatible AI agent call the same business logic that the REST API uses.

## What This Application Does

- **Manages financial transactions and accounts** stored in a PostgreSQL database.
- **Exposes a REST API** (FastAPI) for direct programmatic access from frontends or other services.
- **Exposes an MCP server** (FastMCP) so that AI agents can discover and call financial tools via the Model Context Protocol.
- Provides **financial summaries and aggregations**: monthly breakdowns, spending distributions by category or account, balance trends, and account breakdowns by asset type.

## Core Technologies

| Technology | Role |
|---|---|
| **Python 3.13** | Runtime |
| **FastAPI** | REST API framework |
| **PostgreSQL** | Primary database |
| **SQLAlchemy** | ORM and database session management |
| **Alembic** | Database schema migrations |
| **FastMCP** (`mcp` library) | MCP server for AI agent integration |
| **Uvicorn** | ASGI server |
| **Pipenv** | Dependency management |

## Project Structure

```
finance-assistant-api/
├── src/
│   ├── api/               # FastAPI application and route definitions
│   │   └── app.py
│   ├── mcp/               # MCP server (tool definitions)
│   │   └── server.py
│   ├── services/          # Business logic layer
│   ├── repositories/      # Data access layer (SQLAlchemy)
│   ├── database/          # DB initialisation, session management, ORM models
│   ├── config/            # Database configuration
│   └── models/            # Shared domain models
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
uvicorn src.api.app:app --reload
```

The API is available at `http://localhost:8000`.  
Interactive Swagger docs: `http://localhost:8000/docs`

### MCP Server

```bash
python -m src.mcp.server
```

This starts the FastMCP server over stdio. AI agents (e.g. Claude Desktop, any MCP-compatible client) can connect to it to discover and call the financial tools listed in the [MCP Server](#mcp-server) section below.

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

## REST API Endpoints

Interactive documentation is available at `http://localhost:8000/docs` once the server is running.

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
| `GET` | `/api/balance` | Get the total balance (sum of all transaction amounts) |

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
| `GET` | `/api/summary/monthly/{month}` | Monthly summary for `YYYY-MM`: total income, expenses, net, and top 5 spending categories |
| `GET` | `/api/distribution/spending` | Spending distribution for a date range. Query params: `start_date`, `end_date`, `group_by` (`category` or `account`) |
| `GET` | `/api/breakdown/accounts` | Current balances grouped by asset type (liquidity / investments / other) |

## MCP Server

The MCP server (`src/mcp/server.py`) is built with [FastMCP](https://github.com/jlowin/fastmcp) and exposes the application's business logic as callable tools over the Model Context Protocol. Any MCP-compatible AI agent (e.g. Claude Desktop) can connect to the server and call these tools directly.

### How It Works

1. Start the MCP server with `python -m src.mcp.server`.
2. The server communicates over **stdio** using the MCP protocol.
3. An AI agent connects to the server, lists the available tools, and calls them by name with JSON arguments.
4. Each tool delegates to the same service layer used by the REST API, so behaviour is identical.

### Available Tools

#### Transaction & Account Tools

| Tool | Arguments | Description |
|---|---|---|
| `list_transactions` | `category?`, `start_date?`, `end_date?`, `account_id?` | List transactions with optional filters |
| `add_transaction` | `amount`, `category`, `description`, `date?`, `currency?`, `account_id?` | Add a new transaction |
| `update_transaction` | `transaction_id`, `amount?`, `category?`, `description?`, `date?`, `account_id?` | Update an existing transaction |
| `delete_transaction` | `transaction_id` | Delete a transaction |
| `get_balance` | — | Get the current total balance |
| `list_accounts` | — | List all accounts |
| `get_balance_trend` | `num_months?` (default 12) | Get the balance trend for the last N months |

#### Financial Summary Tools

| Tool | Arguments | Description |
|---|---|---|
| `get_monthly_summary` | `month` (YYYY-MM) | Monthly income, expenses, net, and top spending categories |
| `get_spending_distribution` | `start_date`, `end_date`, `group_by?` (`category`/`account`) | Spending breakdown for a date range |
| `get_account_breakdown` | — | Current balances grouped by asset type with percentages |

### Connecting from Claude Desktop

Add the following entry to your Claude Desktop MCP configuration:

```json
{
  "mcpServers": {
    "finance-assistant": {
      "command": "python",
      "args": ["-m", "src.mcp.server"],
      "cwd": "/path/to/finance-assistant-api",
      "env": {
        "DB_HOST": "...",
        "DB_PORT": "...",
        "DB_NAME": "...",
        "DB_USER": "...",
        "DB_PASSWORD": "..."
      }
    }
  }
}
```

## Running Tests

```bash
python -m pytest tests/ -v
```

## License

[Add your license here]
