# Multimodal Personal Finance Assistant

A professional, self-contained virtual assistant for managing personal finances. This application allows users to interact via text or voice, perform complex queries on their financial data, and manage transactions through both a CLI and a REST API with WebSocket support.

## Features

- **Monthly-Based Financial Model**: Spreadsheet-inspired approach where monthly snapshots are the source of truth for balances. See [Monthly Data Model Documentation](docs/MONTHLY_DATA_MODEL.md) for details.
- **Multimodal Interaction**: Supports text-based input and audio transcription (via `SpeechRecognition`).
- **MCP Architecture**: Uses a dedicated Model Context Protocol (MCP) Server to decouple business logic from the conversational flow and UI.
- **Intelligent NLU**: Powered by OpenAI's `gpt-4o-mini` to dynamically interpret user intent, categories, and timeframes.
- **Dynamic Transaction Management**:
  - Add expenses or income.
  - Delete transactions by ID.
  - Query historic spending with natural language (e.g., "last 3 days", "this week").
- **PostgreSQL Persistence**: Database-backed storage using SQLAlchemy.
- **State Management**: Built with `LangGraph` to manage conversational history and execution nodes.
- **REST API & WebSocket**: FastAPI-based API for programmatic access and real-time chat via WebSocket.

## Architecture

The system is split into two main components:

1.  **Core Backend / MCP Server**: owns the business logic and database.
2.  **LLM Agent**: consumes the MCP Server APIs.

```
llm-finance-assistant/
├── src/
│   ├── repositories/      # Data Access Layer (SQLAlchemy)
│   │   ├── transaction_repository.py
│   │   ├── account_repository.py
│   │   ├── snapshot_repository.py
│   │   └── category_repository.py
│   ├── services/          # Business Logic Layer
│   │   ├── transaction_service.py
│   │   └── account_service.py
│   ├── mcp/               # MCP Server Layer
│   │   └── server.py      # MCP Tool definitions
│   ├── api/               # REST API Layer
│   │   └── app.py         # FastAPI endpoints (consumes Services)
│   ├── business_logic/    # Deprecated module
│   ├── database/          # Database configuration and models
│   ├── config/            # Configuration
│   ├── workflow/          # Agentic workflow
│   ├── models/            # Shared data models
│   └── ...
├── scripts/               # Utility scripts
└── docs/                  # Documentation
```

## Prerequisites

- Python 3.10+
- OpenAI API Key
- PostgreSQL Database

## Setup

1. **Install Dependencies**:

   Using pipenv:
   ```bash
   pipenv install
   ```

2. **Configure Environment**:
   Create a `.env` file in the project root (use `.env.example` as a template):

   ```env
   OPENAI_API_KEY=your_actual_key_here
   DB_PASSWORD=your_database_password_here
   ENVIRONMENT=development
   USE_DATABASE=true
   ```

3. **Database Setup** (Optional):
   In development mode, tables are created automatically on first run. To seed the database:
   ```bash
   python scripts/seed_database.py
   ```

## Usage

### 1. REST API & WebSocket (for Frontend)

Start the FastAPI server:

```bash
uvicorn src.api.app:app --reload
```

The API will be available at `http://localhost:8000`.
- **Docs**: http://localhost:8000/docs

### 2. MCP Server (for Agents)

Start the MCP Server:

```bash
python -m src.mcp.server
```

This starts the MCP server using the `mcp` library (FastMCP). LLM agents can connect to this server to discover and call tools.

### 3. CLI

Run the assistant in interactive mode (Note: CLI needs update to use new services, currently uses LangGraph workflow):

```bash
python -m src.main_cli
```

## MCP Tools

The following tools are exposed by the MCP Server:
- `add_transaction`
- `list_transactions`
- `update_transaction`
- `delete_transaction`
- `get_balance`
- `list_accounts`
- `get_balance_trend`

See [docs/mcp_architecture.md](docs/mcp_architecture.md) for more details.

## Development

### Running Tests

Run unit tests with pytest:

```bash
python -m pytest tests/ -v
```

### Key Components

- **Repositories**: Handle all direct SQL interactions.
- **Services**: Contain the domain logic (e.g., ensuring categories exist before adding transactions, managing monthly snapshots).
- **MCP Server**: The entry point for AI agents. It delegates work to the Service layer.
- **REST API**: The entry point for the frontend. It delegates work to the SAME Service layer as the MCP server.

## License

[Add your license here]
