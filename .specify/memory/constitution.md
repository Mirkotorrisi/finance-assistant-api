# Finance Assistant API Constitution

## Vision

The Finance Assistant API is the **backbone** of an AI-driven personal finance monitoring system. It provides robust financial data CRUD operations while enabling dynamic, intelligent user interfaces. The backend exposes financial data through multiple interfaces (REST API, MCP Server) to support both traditional web applications and AI agents, allowing the frontend to dynamically determine both UI components and API endpoints based on natural language prompts.

## Core Principles

### I. SQL as Single Source of Truth (NON-NEGOTIABLE)

All numerical data and financial calculations MUST originate from PostgreSQL. Vector embeddings, LLM outputs, and caches are derived artifacts only.

**Rules:**
- All balances, totals, and aggregations calculated via SQL queries
- UI displays data directly from database, never from embeddings or LLM computations
- Any derived data (narratives, embeddings) can be regenerated from SQL at any time
- No financial calculations performed by LLMs or from vector search results

**Rationale:** Ensures consistency, auditability, and data integrity across all interfaces.

### II. Monthly Snapshot Model (NON-NEGOTIABLE)

Monthly account snapshots are the authoritative source for account balances. Transactions provide optional granular detail but never define balances through aggregation.

**Rules:**
- `MonthlyAccountSnapshot.ending_balance` is stored directly, not calculated
- Unique constraint on (account_id, year, month) enforced
- Transactions MAY exist without snapshots, but balances MUST come from snapshots
- Historical balance queries MUST use snapshots, not transaction sums
- Snapshots can be manually entered, imported, or derived once and persisted

**Rationale:** Matches spreadsheet mental model, enables efficient queries, supports manual data entry, simplifies reconciliation.

### III. Three-Layer Architecture (NON-NEGOTIABLE)

Clear separation of concerns across three layers: Repositories → Services → API/MCP. Business logic resides exclusively in the Service layer.

**Rules:**
- **Repositories** (`src/repositories/`): Direct database access only, no business logic
- **Services** (`src/services/`): All business logic, domain rules, orchestration
- **API/MCP** (`src/api/`, `src/mcp/`): Input validation, response formatting, delegation to services
- New features MUST be added to Services first, then exposed via API/MCP as needed
- No database access from API/MCP layers (must use Services)
- No business logic in API/MCP layers (must delegate to Services)

**Rationale:** Enables code reuse across interfaces, simplifies testing, maintains clean architecture.

### IV. Narrative-Only Embeddings (NON-NEGOTIABLE)

Vector stores contain ONLY pre-computed narrative summaries, never raw transactions or financial records.

**Rules:**
- Only allowed document types: `monthly_summary`, `category_summary`, `anomaly`, `yearly_overview`, `note`
- Forbidden patterns: `transaction`, `raw`, `individual`
- All embeddings validated before insertion to prevent raw data leakage
- Narratives generated from SQL aggregations via `AggregationService` → `NarrativeGenerator`
- LLM responses must cite narrative sources, never perform calculations

**Rationale:** Prevents data inconsistencies, ensures LLM answers are grounded in SQL-derived facts, enables safe regeneration.

### V. Dual API Architecture

The backend exposes functionality through two parallel interfaces that share the same Service layer: REST API for frontends, MCP Server for LLM agents.

**Rules:**
- **REST API** (`app.py`): FastAPI entrypoint with routes in `src/api/routes/` for web/mobile frontends
- **MCP Server** (`src/mcp/server.py`): FastMCP tools for LLM agent integration
- Both interfaces MUST use the same Services (no duplicate logic)
- Both interfaces MUST maintain feature parity for core operations
- Authentication and rate limiting applied to both interfaces
- API versioning (e.g., `/api/v2/`) required for breaking changes

**Rationale:** Enables both traditional and AI-driven UIs, maintains consistency, supports future AI agent ecosystem.

### VI. Regenerable Derived Data

All derived data (narratives, embeddings, caches) can be safely deleted and regenerated from SQL without data loss.

**Rules:**
- Derived data marked as regenerable in code and documentation
- Regeneration endpoints exposed for maintenance operations
- Regeneration triggered on: month close, data updates, manual request
- No critical data stored exclusively in derived form
- Regeneration operations must be idempotent

**Rationale:** Simplifies data management, enables schema evolution, supports recovery from corruption.

### VII. AI-Driven Interface Support

The backend is designed to support dynamic frontend generation where both UI components and API endpoints are determined by natural language prompts.

**Rules:**
- API endpoints designed for composability and discovery
- Consistent response formats across all endpoints (JSON schemas documented)
- Metadata endpoints provided for API capability discovery
- Error responses include actionable information for LLMs
- Support for both structured (REST) and conversational (MCP) queries

**Rationale:** Enables innovative AI-driven UX, future-proofs architecture, supports prompt-based interface generation.

## Technology Stack

### Core Technologies

**Backend Framework:** Python 3.13 + FastAPI
- Rationale: Async support, automatic OpenAPI docs, type safety, performance

**Database:** PostgreSQL + SQLAlchemy ORM + Alembic
- Rationale: ACID compliance, JSON support, robust aggregations, mature tooling

**AI/ML:** OpenAI (GPT-4o-mini) + LangGraph
- Rationale: State-of-art NLU, embeddings, conversational AI capabilities

**MCP Integration:** FastMCP
- Rationale: Enables LLM agent integration, standardized tool protocol

**Data Processing:** Pandas + openpyxl
- Rationale: Efficient CSV/Excel imports, data transformations

### Development Tools

- **Testing:** pytest (unit, integration, service tests)
- **Migrations:** Alembic (database schema versioning)
- **Environment:** pipenv (dependency management), python-dotenv (config)
- **API Docs:** Auto-generated via FastAPI/OpenAPI

## Development Standards

### Code Organization

- One repository per entity (e.g., `TransactionRepository`, `AccountRepository`)
- One service per domain area (e.g., `TransactionService`, `FinancialDataService`)
- Services may use multiple repositories
- API schema models in `src/api/models/`, database models in `src/database/models.py`

### Testing Requirements

- Unit tests for all Services (business logic verification)
- Integration tests for Repository layer (database interactions)
- API endpoint tests for both REST and MCP interfaces
- Test database isolation (no shared state between tests)
- Pytest fixtures for common test data

### Error Handling

- Structured exceptions with clear error messages
- HTTP status codes follow REST conventions (200, 201, 400, 404, 500)
- MCP tools return structured error responses for LLM consumption
- Log all errors with context (request ID, user ID, operation)

### API Design

- RESTful conventions for HTTP API (resources, verbs, status codes)
- Pagination for list endpoints (default 30 items, max 100)
- ISO 8601 for dates, ISO 4217 for currencies
- Consistent response envelope: `{ "data": ..., "metadata": ... }`
- OpenAPI documentation kept up-to-date

### Database Guidelines

- Use Alembic migrations for ALL schema changes
- No direct SQL in Services (use Repositories)
- Indexes on foreign keys and frequently queried columns
- Unique constraints for natural keys (e.g., account + year + month)
- Default timestamps (created_at, updated_at) on all tables

## Governance

### Constitutional Authority

This constitution supersedes all other development practices, guidelines, and conventions. When conflicts arise between this document and other documentation, this constitution takes precedence.

### Compliance Requirements

- All code reviews MUST verify compliance with NON-NEGOTIABLE principles
- Architecture Decision Records (ADRs) required for deviations from recommended practices
- Principle violations must be documented and justified in PR descriptions
- New features must demonstrate alignment with core principles before merge

### Amendment Process

Amendments to this constitution require:
1. Written proposal documenting rationale and impact
2. Review of affected codebases and migration requirements
3. Team consensus (in multi-person teams) or self-review checkpoint (solo projects)
4. Migration plan for existing code (if applicable)
5. Version increment and amendment date update

### Principle Categories

- **NON-NEGOTIABLE**: Cannot be violated under any circumstances. Violations block merge.
- **Recommended**: Strong guidance that may be deviated from with justification.

### Quality Gates

Before deployment:
- All tests passing (unit, integration, API)
- No violations of NON-NEGOTIABLE principles
- Database migrations tested and reversible
- API documentation updated
- Derived data regeneration verified (if schema changed)

### Living Document

This constitution evolves with the project. Regular reviews recommended at major milestones (quarterly for active projects, or when adding major features).

**Version**: 1.0.0 | **Ratified**: 2026-02-15 | **Last Amended**: 2026-02-15
