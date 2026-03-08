"""Pydantic models for financial-data endpoints."""

from typing import List

from pydantic import BaseModel, ConfigDict, Field


class MonthlyDataResponse(BaseModel):
    """Aggregated financial data for a single month."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "month": "Jan",
                "netWorth": 25000.00,
                "expenses": 1200.50,
                "income": 3000.00,
                "net": 1799.50,
            }
        }
    )

    month: str = Field(..., description="Short month label (e.g. 'Jan', 'Feb').")
    netWorth: float = Field(..., description="Cumulative net worth at the end of the month.")
    expenses: float = Field(..., description="Total expenses for the month.")
    income: float = Field(..., description="Total income for the month.")
    net: float = Field(..., description="Net savings for the month (income minus expenses).")


class AccountBreakdownResponse(BaseModel):
    """High-level account breakdown by asset category."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "liquidity": 5000.00,
                "investments": 20000.00,
                "otherAssets": 500.00,
            }
        }
    )

    liquidity: float = Field(..., description="Total balance across liquid accounts (checking, savings, cash).")
    investments: float = Field(
        ..., description="Total balance across investment accounts (investment, brokerage, retirement)."
    )
    otherAssets: float = Field(..., description="Total balance across all other account types.")


class FinancialDataResponse(BaseModel):
    """Aggregated financial data for a full calendar year."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "year": 2024,
                "currentNetWorth": 25500.00,
                "netSavings": 5500.00,
                "monthlyData": [
                    {
                        "month": "Jan",
                        "netWorth": 20000.00,
                        "expenses": 1200.50,
                        "income": 3000.00,
                        "net": 1799.50,
                    }
                ],
                "accountBreakdown": {
                    "liquidity": 5000.00,
                    "investments": 20000.00,
                    "otherAssets": 500.00,
                },
            }
        }
    )

    year: int = Field(..., description="Calendar year for this dataset.")
    currentNetWorth: float = Field(..., description="Current total net worth across all accounts.")
    netSavings: float = Field(..., description="Total net savings accumulated during the year.")
    monthlyData: List[MonthlyDataResponse] = Field(
        ..., description="Month-by-month breakdown of income, expenses, and net worth."
    )
    accountBreakdown: AccountBreakdownResponse = Field(
        ..., description="Current balance split by asset category."
    )
