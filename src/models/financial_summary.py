"""Pydantic models for financial-summary endpoints."""

from typing import Dict, List

from pydantic import BaseModel, ConfigDict, Field


class TopCategoryItem(BaseModel):
    """A single spending category entry in a monthly summary."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"category": "groceries", "amount": 320.00, "count": 8}
        }
    )

    category: str = Field(..., description="Category name.")
    amount: float = Field(..., description="Total amount spent in this category.")
    count: int = Field(..., description="Number of transactions in this category.")


class MonthlySummaryResponse(BaseModel):
    """Monthly financial summary including income, expenses, and top spending categories."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "month": "2024-01",
                "income": 3000.00,
                "expenses": 1200.50,
                "net": 1799.50,
                "top_categories": [
                    {"category": "groceries", "amount": 320.00, "count": 8},
                    {"category": "transport", "amount": 180.00, "count": 5},
                ],
            }
        }
    )

    month: str = Field(..., description="Month in YYYY-MM format.")
    income: float = Field(..., description="Total income for the month.")
    expenses: float = Field(..., description="Total expenses for the month.")
    net: float = Field(..., description="Net amount (income minus expenses).")
    top_categories: List[TopCategoryItem] = Field(
        ..., description="Top 5 spending categories for the month."
    )


class DistributionItem(BaseModel):
    """A single item in a spending distribution breakdown."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "groceries",
                "amount": 320.00,
                "percent": 26.67,
                "count": 8,
            }
        }
    )

    name: str = Field(..., description="Category or account name.")
    amount: float = Field(..., description="Total spending amount for this item.")
    percent: float = Field(..., description="Percentage of total spending represented by this item.")
    count: int = Field(..., description="Number of transactions contributing to this item.")


class SpendingDistributionResponse(BaseModel):
    """Spending distribution breakdown for a date range grouped by category or account."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
                "group_by": "category",
                "total_amount": 1200.50,
                "distribution": [
                    {"name": "groceries", "amount": 320.00, "percent": 26.67, "count": 8},
                    {"name": "transport", "amount": 180.00, "percent": 15.00, "count": 5},
                ],
            }
        }
    )

    start_date: str = Field(..., description="Start date of the period (YYYY-MM-DD).")
    end_date: str = Field(..., description="End date of the period (YYYY-MM-DD).")
    group_by: str = Field(..., description="Grouping method used: 'category' or 'account'.")
    total_amount: float = Field(..., description="Total spending amount across all items.")
    distribution: List[DistributionItem] = Field(
        ..., description="Spending items sorted by amount descending."
    )


class TypeBreakdownItem(BaseModel):
    """Amount and percentage for a single account-type bucket."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"amount": 5000.00, "percent": 22.22}}
    )

    amount: float = Field(..., description="Total balance for this account type.")
    percent: float = Field(..., description="Percentage of total balance represented by this type.")


class AccountItem(BaseModel):
    """Individual account entry in an account breakdown response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "account_id": 1,
                "name": "Main Checking",
                "type": "checking",
                "category": "liquidity",
                "balance": 5000.00,
                "percent": 22.22,
                "currency": "EUR",
            }
        }
    )

    account_id: int = Field(..., description="Unique account identifier.")
    name: str = Field(..., description="Account display name.")
    type: str = Field(..., description="Raw account type (e.g. 'checking', 'retirement').")
    category: str = Field(
        ..., description="Asset category: 'liquidity', 'investments', or 'other'."
    )
    balance: float = Field(..., description="Current balance for this account.")
    percent: float = Field(..., description="Percentage of total balance represented by this account.")
    currency: str = Field(..., description="ISO 4217 currency code.")


class AccountBreakdownDetailResponse(BaseModel):
    """Detailed account breakdown grouped by asset type with individual account entries."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_balance": 22500.00,
                "by_type": {
                    "liquidity": {"amount": 5000.00, "percent": 22.22},
                    "investments": {"amount": 17000.00, "percent": 75.56},
                    "other": {"amount": 500.00, "percent": 2.22},
                },
                "accounts": [
                    {
                        "account_id": 2,
                        "name": "Retirement Fund",
                        "type": "retirement",
                        "category": "investments",
                        "balance": 17000.00,
                        "percent": 75.56,
                        "currency": "EUR",
                    },
                    {
                        "account_id": 1,
                        "name": "Main Checking",
                        "type": "checking",
                        "category": "liquidity",
                        "balance": 5000.00,
                        "percent": 22.22,
                        "currency": "EUR",
                    },
                ],
            }
        }
    )

    total_balance: float = Field(..., description="Total balance across all active accounts.")
    by_type: Dict[str, TypeBreakdownItem] = Field(
        ...,
        description="Breakdown by asset category. Keys are 'liquidity', 'investments', and 'other'.",
    )
    accounts: List[AccountItem] = Field(
        ..., description="Individual account entries sorted by balance descending."
    )
