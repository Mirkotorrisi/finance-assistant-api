# MCP Architecture & Refactor Documentation

## Overview

The Finance Assistant backend has been refactored to separate business logic from the API layer and the LLM Agent. We have introduced a Model Context Protocol (MCP) Server to expose core capabilities to the Agent.

## Architecture

The system is split into:

1.  **Core Backend (Source of Truth)**:
    -   **Repositories**: Direct database access (`src/repositories/`).
    -   **Services**: Business logic and domain rules (`src/services/`).
    -   **API Layer**: Two interfaces:
        -   **REST API (`src/api/app.py`)**: For Frontend applications.
        -   **MCP Server (`src/mcp/server.py`)**: For LLM Agents.

2.  **LLM Agent**:
    -   Connects to the MCP Server.
    -   Does NOT access the database directly.
    -   Uses tools exposed by the MCP Server.

## MCP Server

The MCP Server is defined in `src/mcp/server.py`.

### Responsibilities
-   Validation of inputs.
-   Business logic execution (via Services).
-   Data persistence (via Repositories).
-   Exposing tools for the Agent.

### Exposed Tools
-   `list_transactions`: Filter and view transactions.
-   `add_transaction`: Add a single transaction.
-   `update_transaction`: Modify an existing transaction.
-   `delete_transaction`: Remove a transaction.
-   `get_balance`: Get the current total balance.
-   `list_accounts`: View available accounts.
-   `get_balance_trend`: View historical balance trend.

## REST API Compatibility

The existing FastAPI application in `src/api/app.py` has been updated to use the same Service layer as the MCP Server (`TransactionService`).
-   All endpoints (`GET /api/transactions`, `POST /api/transactions`, etc.) function exactly as before.
-   The dependency injection logic in `app.py` now provides `TransactionService` instead of `FinanceMCPDatabase`.

## How to Run

### REST API
```bash
uvicorn src.api.app:app --reload
```

### MCP Server
To run the MCP server locally (e.g. for testing or connecting a local agent):
```bash
python src/mcp/server.py
```
Note: You may need to install the `mcp` package: `pipenv install` (we added it to Pipfile).

## Development Guidelines

-   **Logic Location**: All business logic MUST reside in `src/services/`.
-   **Database Access**: All SQL queries MUST reside in `src/repositories/`.
-   **New Features**: Add to a Service, then expose in both `app.py` (if needed by frontend) and `mcp/server.py` (if needed by Agent).
