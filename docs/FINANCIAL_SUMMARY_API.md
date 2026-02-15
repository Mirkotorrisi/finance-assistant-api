# Financial Summary & Aggregation API

This document describes the UI-driven financial aggregation tools added to the Finance Assistant API. These endpoints provide chart-ready data for generative UI components.

## Overview

The Financial Summary API provides three main aggregation endpoints designed to power modern financial dashboards and UI components:

1. **Monthly Summary**: Income, expenses, net, and top spending categories for a specific month
2. **Spending Distribution**: Category or account breakdown for a date range with amounts, percentages, and counts
3. **Account Breakdown**: Current balances organized by account type with percentages

All endpoints return structured JSON that matches generative UI expectations and can be directly consumed by chart components.

## REST API Endpoints

### 1. Get Monthly Summary

Returns financial summary for a specific month including income, expenses, net income, and top spending categories.

**Endpoint**: `GET /api/summary/monthly/{month}`

**Parameters**:
- `month` (path parameter, required): Month in format "YYYY-MM" (e.g., "2024-01")

**Response Model**: `MonthlySummaryResponse`
```json
{
  "month": "2024-01",
  "income": 5000.00,
  "expenses": 3200.00,
  "net": 1800.00,
  "top_categories": [
    {
      "category": "Groceries",
      "amount": 800.00,
      "count": 15
    },
    {
      "category": "Transportation",
      "amount": 600.00,
      "count": 8
    }
  ]
}
```

**Use Cases**:
- SummaryTable component showing monthly financial overview
- Monthly performance metrics
- Quick financial health snapshot

**Example**:
```bash
curl http://localhost:8000/api/summary/monthly/2024-01
```

---

### 2. Get Spending Distribution

Returns spending distribution breakdown by category or account for a date range.

**Endpoint**: `GET /api/distribution/spending`

**Query Parameters**:
- `start_date` (required): Start date in format "YYYY-MM-DD"
- `end_date` (required): End date in format "YYYY-MM-DD"
- `group_by` (optional, default: "category"): Grouping method - "category" or "account"

**Response Model**: `SpendingDistributionResponse`
```json
{
  "start_date": "2024-01-01",
  "end_date": "2024-01-31",
  "group_by": "category",
  "total_amount": 3200.00,
  "distribution": [
    {
      "name": "Groceries",
      "amount": 800.00,
      "percent": 25.00,
      "count": 15
    },
    {
      "name": "Transportation",
      "amount": 600.00,
      "percent": 18.75,
      "count": 8
    },
    {
      "name": "Dining",
      "amount": 500.00,
      "percent": 15.63,
      "count": 12
    }
  ]
}
```

**Use Cases**:
- Pie chart or bubble chart showing spending by category
- Account-based spending analysis
- Period-over-period spending comparison

**Examples**:
```bash
# By category
curl "http://localhost:8000/api/distribution/spending?start_date=2024-01-01&end_date=2024-01-31&group_by=category"

# By account
curl "http://localhost:8000/api/distribution/spending?start_date=2024-01-01&end_date=2024-01-31&group_by=account"
```

---

### 3. Get Account Breakdown

Returns current account breakdown by type (liquidity, investments, other) with individual account details.

**Endpoint**: `GET /api/breakdown/accounts`

**Parameters**: None

**Response Model**: `AccountBreakdownDetailResponse`
```json
{
  "total_balance": 172500.00,
  "by_type": {
    "liquidity": {
      "amount": 15500.00,
      "percent": 9.0
    },
    "investments": {
      "amount": 157000.00,
      "percent": 91.0
    },
    "other": {
      "amount": 0.00,
      "percent": 0.0
    }
  },
  "accounts": [
    {
      "account_id": 4,
      "name": "Retirement",
      "type": "retirement",
      "category": "investments",
      "balance": 105000.00,
      "percent": 60.9,
      "currency": "EUR"
    },
    {
      "account_id": 3,
      "name": "Investment",
      "type": "investment",
      "category": "investments",
      "balance": 52000.00,
      "percent": 30.1,
      "currency": "EUR"
    }
  ]
}
```

**Account Type Categories**:
- **Liquidity**: checking, savings, cash
- **Investments**: investment, brokerage, retirement
- **Other**: All other account types

**Use Cases**:
- Portfolio allocation visualization
- Asset distribution charts
- Net worth breakdown by account type

**Example**:
```bash
curl http://localhost:8000/api/breakdown/accounts
```

---

## MCP Server Tools

The same functionality is available via MCP (Model Context Protocol) tools for AI agents:

### Tool: get_monthly_summary

```python
@mcp.tool()
def get_monthly_summary(month: str) -> str:
    """Get monthly financial summary including income, expenses, net, and top categories.
    
    Args:
        month: Month in format "YYYY-MM" (e.g., "2024-01")
        
    Returns:
        JSON string containing monthly summary data
    """
```

### Tool: get_spending_distribution

```python
@mcp.tool()
def get_spending_distribution(start_date: str, end_date: str, group_by: str = "category") -> str:
    """Get spending distribution breakdown for a date range.
    
    Args:
        start_date: Start date in format "YYYY-MM-DD"
        end_date: End date in format "YYYY-MM-DD"
        group_by: Grouping method - "category" or "account" (default: "category")
        
    Returns:
        JSON string containing spending distribution data
    """
```

### Tool: get_account_breakdown

```python
@mcp.tool()
def get_account_breakdown() -> str:
    """Get current account breakdown by type with balances and percentages.
    
    Returns:
        JSON string containing account breakdown data
    """
```

---

## Service Layer

All endpoints are backed by the `FinancialSummaryService` located in `src/services/financial_summary_service.py`.

### Methods

#### get_monthly_summary(month: str) -> Dict[str, Any]
Returns monthly summary with income, expenses, net, and top 5 spending categories.

#### get_spending_distribution(start_date: str, end_date: str, group_by: str) -> Dict[str, Any]
Returns spending distribution grouped by category or account for a date range.

#### get_account_breakdown() -> Dict[str, Any]
Returns current account breakdown using the most recent snapshot data for each account.

---

## Data Sources

### Monthly Summary
- **Income/Expenses**: Aggregated from `MonthlyAccountSnapshot` table
- **Top Categories**: Calculated from `Transaction` table (expense transactions only)

### Spending Distribution
- **Data Source**: `Transaction` table
- **Filter**: Only expense transactions (amount < 0)
- **Grouping**: By category name or account ID

### Account Breakdown
- **Data Source**: `MonthlyAccountSnapshot` joined with `Account` table
- **Selection**: Most recent snapshot for each active account
- **Categorization**: Based on account type field

---

## Error Handling

All endpoints include comprehensive input validation:

### Invalid Month Format
```json
{
  "detail": "Invalid month format. Use 'YYYY-MM' (e.g., '2024-01')"
}
```
**Status Code**: 400

### Invalid Date Format
```json
{
  "detail": "Invalid date format. Use 'YYYY-MM-DD'"
}
```
**Status Code**: 400

### Invalid Group By
```json
{
  "detail": "group_by must be 'category' or 'account'"
}
```
**Status Code**: 400

---

## Integration with Generative UI

These endpoints are specifically designed for generative UI components:

### SummaryTable Component
Use `/api/summary/monthly/{month}` to populate:
- Income/Expense summary cards
- Net income metric
- Top spending categories table

### Chart Components (Pie/Bubble)
Use `/api/distribution/spending` to generate:
- Category-based spending pie charts
- Account-based spending distribution
- Interactive bubble charts with size = amount, color = category

### Portfolio Visualization
Use `/api/breakdown/accounts` to display:
- Asset allocation donut chart
- Account balance table with percentages
- Type-based portfolio breakdown

---

## Schema Compatibility

All response models use Pydantic for validation and are compatible with:
- TypeScript/Zod schemas (via OpenAPI generation)
- JSON Schema validators
- GraphQL type definitions

To generate TypeScript types:
```bash
# Visit the OpenAPI docs
http://localhost:8000/docs

# Or generate schemas programmatically
curl http://localhost:8000/openapi.json > openapi.json
```

---

## Testing

Comprehensive test coverage includes:

### Unit Tests
- `tests/test_financial_summary_service.py`: Service layer logic
- 13 test cases covering all methods and edge cases

### Integration Tests
- `tests/test_integration_summary_endpoints.py`: End-to-end functionality
- Real database operations with SQLite in-memory
- 4 test scenarios with detailed output

Run tests:
```bash
# Unit tests only
python -m pytest tests/test_financial_summary_service.py -v

# Integration tests
python tests/test_integration_summary_endpoints.py

# All tests
python -m pytest tests/ -v
```

---

## Architecture Notes

### Design Principles
1. **UI-First**: Data format optimized for direct UI consumption
2. **Chart-Ready**: Percentages, counts, and formatting included
3. **Consistent**: Same data available via REST API and MCP Server
4. **Validated**: Pydantic models ensure type safety

### Service Responsibilities
- **FinancialSummaryService**: Aggregation and calculation logic
- **MCP Server**: Tool exposure for AI agents
- **FastAPI App**: REST endpoints for frontend

### Data Flow
```
Database (PostgreSQL)
    ↓
Service Layer (FinancialSummaryService)
    ↓ ↓
    ↓ └→ MCP Server (AI Agents)
    ↓
REST API (Frontend/Dashboard)
```

---

## Future Enhancements

Potential improvements for future versions:

1. **Caching**: Redis cache for frequently accessed aggregations
2. **Time Ranges**: Predefined ranges (last 30 days, last quarter, YTD)
3. **Comparisons**: Period-over-period comparison data
4. **Forecasting**: Predictive spending patterns
5. **Custom Grouping**: User-defined category groups
6. **Export**: CSV/Excel export functionality

---

## Support

For issues or questions:
- Review the main [README.md](../README.md)
- Check [MCP Architecture docs](mcp_architecture.md)
- See [Financial Data API docs](FINANCIAL_DATA_API.md)
