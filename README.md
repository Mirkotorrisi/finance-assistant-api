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

### Database Migrations (Alembic)

To update your local database schema:
```bash
uv run alembic upgrade head
```

To create a new migration after model changes:
```bash
uv run alembic revision --autogenerate -m "description of changes"
```

## 🛠️ Features

- **Transaction Management**: CRUD for income and expenses.
- **Account Tracking**: Manage checking, savings, and investment accounts.
- **Financial Summaries**: Aggregated data for net worth and monthly breakdowns.
- **MCP Integration**: Fully compatible with the Model Context Protocol for AI Agent interaction.

## 🐳 Docker

The API is containerized for production and development:
```bash
docker build -t finance-api .
docker run -p 8080:8080 finance-api
```

---
Part of the [Finance Assistant Monorepo](../)