# Financial Data API Endpoint

## Overview

The Financial Data API endpoint provides aggregated financial data for the frontend dashboard. It returns yearly financial data including monthly breakdowns, net worth tracking, and account categorization.

## Endpoint

```
GET /api/financial-data/{year}
```

### Path Parameters

- `year` (int, required): The year to retrieve financial data for (e.g., 2024, 2025)

### Response Format

The response matches the TypeScript interfaces defined in the frontend:

```json
{
  "year": 2024,
  "currentNetWorth": 45800,
  "netSavings": 8200,
  "monthlyData": [
    {
      "month": "Jan",
      "netWorth": 38000,
      "expenses": 2800,
      "income": 4500,
      "net": 1700
    },
    {
      "month": "Feb",
      "netWorth": 39200,
      "expenses": 2600,
      "income": 3800,
      "net": 1200
    }
    // ... more months (12 total)
  ],
  "accountBreakdown": {
    "liquidity": 25000,
    "investments": 18500,
    "otherAssets": 2300
  }
}
```

## Response Fields

### Top-level Fields

- `year` (int): The requested year
- `currentNetWorth` (float): Total net worth as of the most recent month with data
- `netSavings` (float): Sum of all monthly net values (income - expenses) for the year
- `monthlyData` (array): Array of 12 monthly data objects (Jan-Dec)
- `accountBreakdown` (object): Categorized account balances

### Monthly Data Fields

Each object in `monthlyData` contains:

- `month` (string): Short month name ("Jan", "Feb", ..., "Dec")
- `netWorth` (float): Total ending balance across all accounts for that month
- `expenses` (float): Total expenses across all accounts for that month
- `income` (float): Total income across all accounts for that month
- `net` (float): Net value for the month (income - expenses)

### Account Breakdown Fields

- `liquidity` (float): Sum of balances for checking, savings, and cash accounts
- `investments` (float): Sum of balances for investment, brokerage, and retirement accounts
- `otherAssets` (float): Sum of balances for all other account types

## Data Source

The endpoint aggregates data from:
- `MonthlyAccountSnapshot` table: Provides monthly balances, income, and expenses
- `Account` table: Provides account type information for categorization

## Edge Cases

### No Data for Year

If no data exists for the requested year, the endpoint returns a valid response with zero values:

```json
{
  "year": 2024,
  "currentNetWorth": 0.0,
  "netSavings": 0.0,
  "monthlyData": [
    // 12 months with all zeros
  ],
  "accountBreakdown": {
    "liquidity": 0.0,
    "investments": 0.0,
    "otherAssets": 0.0
  }
}
```

### Partial Year Data

If only some months have data, the response includes:
- Zero values for months without data
- Calculated values for months with data
- `currentNetWorth` based on the most recent month with data
- `netSavings` calculated from available data

## Account Type Categorization

Account types are categorized as follows:

**Liquidity:**
- checking
- savings
- cash

**Investments:**
- investment
- brokerage
- retirement

**Other Assets:**
- All other account types

## Example Usage

### cURL

```bash
curl -X GET "http://localhost:8000/api/financial-data/2024" \
  -H "accept: application/json"
```

### Python (requests)

```python
import requests

response = requests.get("http://localhost:8000/api/financial-data/2024")
data = response.json()

print(f"Net Worth: ${data['currentNetWorth']:,.2f}")
print(f"Net Savings: ${data['netSavings']:,.2f}")
```

### JavaScript (fetch)

```javascript
fetch('http://localhost:8000/api/financial-data/2024')
  .then(response => response.json())
  .then(data => {
    console.log('Current Net Worth:', data.currentNetWorth);
    console.log('Monthly Data:', data.monthlyData);
  });
```

## Implementation Details

### Service Layer

The endpoint uses `FinancialDataService` which:
- Queries `MonthlyAccountSnapshot` for all accounts and months in the year
- Aggregates data by month using SQL SUM operations
- Categorizes accounts by type
- Calculates derived metrics (net worth, net savings)

### Performance

- Efficient SQL queries with aggregation at the database level
- Single query per calculation (monthly data, account breakdown, current net worth)
- No N+1 query issues

### Testing

Tests are located in:
- `tests/test_financial_data_service.py`: Unit tests for service methods
- `tests/test_integration_financial_data.py`: Integration tests with in-memory database

Run tests with:
```bash
python -m pytest tests/test_financial_data_service.py tests/test_integration_financial_data.py -v
```

## API Documentation

Interactive API documentation is available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
