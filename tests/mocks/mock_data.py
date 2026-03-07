"""Shared mock data used across unit and integration tests."""

from datetime import date

# ---------------------------------------------------------------------------
# Account fixtures
# ---------------------------------------------------------------------------

MOCK_ACCOUNTS = [
    {
        "id": 1,
        "name": "Main Checking",
        "type": "checking",
        "currency": "EUR",
        "is_active": True,
        "current_balance": 0.0,
    },
    {
        "id": 2,
        "name": "Savings",
        "type": "savings",
        "currency": "EUR",
        "is_active": True,
        "current_balance": 0.0,
    },
    {
        "id": 3,
        "name": "Investment Portfolio",
        "type": "investment",
        "currency": "EUR",
        "is_active": True,
        "current_balance": 0.0,
    },
    {
        "id": 4,
        "name": "Retirement Fund",
        "type": "retirement",
        "currency": "EUR",
        "is_active": True,
        "current_balance": 0.0,
    },
    {
        "id": 5,
        "name": "Inactive Account",
        "type": "checking",
        "currency": "EUR",
        "is_active": False,
        "current_balance": 0.0,
    },
]

# ---------------------------------------------------------------------------
# Category fixtures
# ---------------------------------------------------------------------------

MOCK_CATEGORIES = [
    {"id": 1, "name": "salary", "type": "income", "color": "#4CAF50"},
    {"id": 2, "name": "groceries", "type": "expense", "color": "#FF5722"},
    {"id": 3, "name": "rent", "type": "expense", "color": "#9C27B0"},
    {"id": 4, "name": "transportation", "type": "expense", "color": "#2196F3"},
    {"id": 5, "name": "dining", "type": "expense", "color": "#FF9800"},
    {"id": 6, "name": "entertainment", "type": "expense", "color": "#E91E63"},
    {"id": 7, "name": "utilities", "type": "expense", "color": "#607D8B"},
    {"id": 8, "name": "investment", "type": "income", "color": "#009688"},
]

# ---------------------------------------------------------------------------
# Transaction fixtures
# ---------------------------------------------------------------------------

MOCK_TRANSACTIONS = [
    # January 2024 – account 1
    {
        "id": 1,
        "account_id": 1,
        "date": date(2024, 1, 1),
        "amount": 3000.0,
        "category": "salary",
        "description": "Monthly salary",
        "currency": "EUR",
    },
    {
        "id": 2,
        "account_id": 1,
        "date": date(2024, 1, 5),
        "amount": -200.0,
        "category": "groceries",
        "description": "Weekly groceries",
        "currency": "EUR",
    },
    {
        "id": 3,
        "account_id": 1,
        "date": date(2024, 1, 10),
        "amount": -800.0,
        "category": "rent",
        "description": "January rent",
        "currency": "EUR",
    },
    {
        "id": 4,
        "account_id": 1,
        "date": date(2024, 1, 15),
        "amount": -50.0,
        "category": "transportation",
        "description": "Bus pass",
        "currency": "EUR",
    },
    # February 2024 – account 1
    {
        "id": 5,
        "account_id": 1,
        "date": date(2024, 2, 1),
        "amount": 3000.0,
        "category": "salary",
        "description": "Monthly salary",
        "currency": "EUR",
    },
    {
        "id": 6,
        "account_id": 1,
        "date": date(2024, 2, 10),
        "amount": -180.0,
        "category": "groceries",
        "description": "Grocery shopping",
        "currency": "EUR",
    },
    # January 2024 – account 2 (savings)
    {
        "id": 7,
        "account_id": 2,
        "date": date(2024, 1, 2),
        "amount": 500.0,
        "category": "salary",
        "description": "Savings deposit",
        "currency": "EUR",
    },
    # January 2024 – account 3 (investment)
    {
        "id": 8,
        "account_id": 3,
        "date": date(2024, 1, 3),
        "amount": 1000.0,
        "category": "investment",
        "description": "ETF purchase",
        "currency": "EUR",
    },
]

# Convenience subsets
JANUARY_2024_TRANSACTIONS = [t for t in MOCK_TRANSACTIONS if t["date"].year == 2024 and t["date"].month == 1]
FEBRUARY_2024_TRANSACTIONS = [t for t in MOCK_TRANSACTIONS if t["date"].year == 2024 and t["date"].month == 2]
ACCOUNT_1_TRANSACTIONS = [t for t in MOCK_TRANSACTIONS if t["account_id"] == 1]
