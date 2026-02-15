# Implementation Plan: Project Constitution

## Problem Statement
Update the constitution.md template with the actual architectural principles and design decisions for the Finance Assistant API backend. This project serves as the backbone for an AI-driven personal finance monitoring system where:
- Backend provides financial data CRUD operations via SQL queries
- Frontend is dynamically generated from prompts
- Frontend determines both UI components AND API endpoints to call
- Built with Python FastAPI, PostgreSQL, and exposes MCP server for LLM integration

## Proposed Approach
Analyze existing architecture documentation and extract the core principles that guide the project. Fill in the constitution template with:
1. Strategic architectural principles (SQL-first, monthly snapshots)
2. Technology stack decisions and rationale
3. Development guidelines (testing, API design, service patterns)
4. Governance rules for maintaining architectural integrity

## Workplan

- [x] Review existing architecture documentation
- [x] Identify existing constitution template structure
- [x] Extract core architectural principles from codebase
  - [x] SQL-First RAG principles
  - [x] Monthly snapshot data model principles
  - [x] Service layer separation principles
  - [x] Dual API architecture (REST + MCP)
  - [x] AI/LLM integration patterns

- [ ] Draft constitution content
  - [ ] Vision statement
  - [ ] Core principles (5-7 key principles)
  - [ ] Technology stack section
  - [ ] Development standards section
  - [ ] Governance rules

- [ ] Update constitution.md file
  - [ ] Replace template placeholders with actual content
  - [ ] Ensure principles are clear and actionable
  - [ ] Add version and ratification date
  - [ ] Verify formatting and consistency

- [x] Validate constitution alignment
  - [x] Check against existing docs
  - [x] Ensure no contradictions
  - [x] Confirm completeness

## Validation Summary

✅ **Alignment with SQL_FIRST_RAG_ARCHITECTURE.md**: Principle I (SQL as Single Source of Truth) and Principle IV (Narrative-Only Embeddings) directly reflect the SQL-first RAG architecture.

✅ **Alignment with MONTHLY_DATA_MODEL.md**: Principle II (Monthly Snapshot Model) captures the core design philosophy that snapshots are source of truth, transactions are optional detail.

✅ **Alignment with mcp_architecture.md**: Principle III (Three-Layer Architecture) and Principle V (Dual API Architecture) reflect the separation between Repositories, Services, and API/MCP layers.

✅ **No contradictions**: All principles extracted from existing documentation. Constitution codifies implicit design decisions.

✅ **Completeness**: Covers data architecture, service design, API patterns, testing, and governance.

## Key Principles Identified

### Strategic (Non-Negotiable):
1. **SQL as Single Source of Truth**: All numerical data from PostgreSQL, never from embeddings
2. **Monthly Snapshot Model**: Balances stored monthly, transactions are optional detail
3. **Separation of Concerns**: Clear layers (Repositories → Services → API/MCP)
4. **Narrative-Only Embeddings**: Only pre-computed summaries embedded, never raw transactions

### Tactical (Recommended):
5. **Dual API Architecture**: REST for frontend, MCP for LLM agents, both use same services
6. **Regenerable Derived Data**: Narratives and embeddings can be regenerated from SQL anytime
7. **AI-Driven Interface**: Backend supports dynamic UI generation based on prompts

## Technology Stack
- **Backend**: Python 3.13, FastAPI
- **Database**: PostgreSQL, SQLAlchemy ORM, Alembic migrations  
- **AI/ML**: OpenAI (GPT-4o-mini), LangGraph, embeddings
- **MCP**: FastMCP for LLM agent integration
- **Data Processing**: Pandas, openpyxl for imports

## Notes
- Constitution should guide ALL future development decisions
- Principles must be clear enough for new contributors to follow
- Technology choices should be justified with rationale
- Allow flexibility where appropriate, mandate where critical
