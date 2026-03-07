"""Integration tests for FinancialSummaryService endpoints."""

import sys
import os
from datetime import date

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database.models import Base, Account, Transaction
from src.services.financial_summary_service import FinancialSummaryService


def test_get_monthly_summary():
    """Test get_monthly_summary with in-memory database."""
    # Create in-memory SQLite database
    engine = create_engine('sqlite:///:memory:', echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Create test account
        checking = Account(id=1, name="Checking", type="checking", currency="EUR")
        session.add(checking)
        session.commit()
        
        # Create transactions for January 2024
        # Income: 1500, Expenses: 800
        transactions = [
            Transaction(account_id=1, date=date(2024, 1, 1), amount=1500, category="Salary", description="Monthly salary"),
            Transaction(account_id=1, date=date(2024, 1, 5), amount=-200, category="Groceries", description="Shopping"),
            Transaction(account_id=1, date=date(2024, 1, 10), amount=-150, category="Groceries", description="More shopping"),
            Transaction(account_id=1, date=date(2024, 1, 12), amount=-300, category="Transportation", description="Gas"),
            Transaction(account_id=1, date=date(2024, 1, 15), amount=-100, category="Dining", description="Restaurant"),
            Transaction(account_id=1, date=date(2024, 1, 20), amount=-50, category="Entertainment", description="Movies"),
        ]
        session.add_all(transactions)
        session.commit()
        
        # Test the service
        service = FinancialSummaryService(session)
        result = service.get_monthly_summary("2024-01")
        
        print("\n" + "=" * 80)
        print("MONTHLY SUMMARY TEST: January 2024")
        print("=" * 80)
        print(f"Month: {result['month']}")
        print(f"Income: ${result['income']:,.2f}")
        print(f"Expenses: ${result['expenses']:,.2f}")
        print(f"Net: ${result['net']:,.2f}")
        print("\nTop Categories:")
        for i, cat in enumerate(result['top_categories'], 1):
            print(f"  {i}. {cat['category']}: ${cat['amount']:,.2f} ({cat['count']} transactions)")
        print("=" * 80 + "\n")
        
        # Verify results (income/expenses now come from transactions)
        assert result['month'] == "2024-01"
        assert result['income'] == 1500.0
        assert result['expenses'] == 800.0
        assert result['net'] == 700.0
        assert len(result['top_categories']) > 0
        assert result['top_categories'][0]['category'] == "Groceries"
        assert result['top_categories'][0]['amount'] == 350.0
        
        print("✅ Monthly summary test passed!\n")
        
    finally:
        session.close()


def test_get_spending_distribution():
    """Test get_spending_distribution with in-memory database."""
    engine = create_engine('sqlite:///:memory:', echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Create test accounts
        checking = Account(id=1, name="Checking", type="checking", currency="EUR")
        credit = Account(id=2, name="Credit Card", type="credit", currency="EUR")
        session.add_all([checking, credit])
        session.commit()
        
        # Create transactions for different categories
        transactions = [
            Transaction(account_id=1, date=date(2024, 1, 5), amount=-200, category="Groceries", description="Food"),
            Transaction(account_id=1, date=date(2024, 1, 10), amount=-300, category="Groceries", description="More food"),
            Transaction(account_id=1, date=date(2024, 1, 12), amount=-400, category="Transportation", description="Gas"),
            Transaction(account_id=2, date=date(2024, 1, 15), amount=-100, category="Dining", description="Restaurant"),
            Transaction(account_id=2, date=date(2024, 1, 20), amount=-150, category="Dining", description="Another restaurant"),
            Transaction(account_id=1, date=date(2024, 1, 25), amount=-50, category="Entertainment", description="Movies"),
        ]
        session.add_all(transactions)
        session.commit()
        
        # Test category grouping
        service = FinancialSummaryService(session)
        result = service.get_spending_distribution("2024-01-01", "2024-01-31", "category")
        
        print("\n" + "=" * 80)
        print("SPENDING DISTRIBUTION TEST: Category Grouping")
        print("=" * 80)
        print(f"Date Range: {result['start_date']} to {result['end_date']}")
        print(f"Total Spending: ${result['total_amount']:,.2f}")
        print(f"\nDistribution by {result['group_by']}:")
        for item in result['distribution']:
            print(f"  {item['name']:<20} ${item['amount']:>8,.2f}  ({item['percent']:>5.1f}%)  {item['count']} txns")
        print("=" * 80 + "\n")
        
        # Verify results
        assert result['total_amount'] == 1200.0
        assert len(result['distribution']) == 4
        assert result['distribution'][0]['name'] == "Groceries"  # Highest amount
        assert result['distribution'][0]['amount'] == 500.0
        assert result['distribution'][0]['percent'] == round(500/1200*100, 2)
        
        # Test account grouping
        result_account = service.get_spending_distribution("2024-01-01", "2024-01-31", "account")
        
        print("SPENDING DISTRIBUTION TEST: Account Grouping")
        print("=" * 80)
        print(f"Total Spending: ${result_account['total_amount']:,.2f}")
        print(f"\nDistribution by {result_account['group_by']}:")
        for item in result_account['distribution']:
            print(f"  {item['name']:<20} ${item['amount']:>8,.2f}  ({item['percent']:>5.1f}%)  {item['count']} txns")
        print("=" * 80 + "\n")
        
        # Verify account grouping
        assert len(result_account['distribution']) == 2
        assert result_account['total_amount'] == 1200.0
        
        print("✅ Spending distribution test passed!\n")
        
    finally:
        session.close()


def test_get_account_breakdown():
    """Test get_account_breakdown with in-memory database."""
    engine = create_engine('sqlite:///:memory:', echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Create test accounts
        checking = Account(id=1, name="Checking", type="checking", currency="EUR", is_active=True)
        savings = Account(id=2, name="Savings", type="savings", currency="EUR", is_active=True)
        investment = Account(id=3, name="Investment", type="investment", currency="EUR", is_active=True)
        retirement = Account(id=4, name="Retirement", type="retirement", currency="EUR", is_active=True)
        session.add_all([checking, savings, investment, retirement])
        session.commit()
        
        # Create transactions per account
        transactions = [
            # Checking: net 5000
            Transaction(account_id=1, date=date(2024, 1, 1), amount=6000, category="Salary", description="Salary"),
            Transaction(account_id=1, date=date(2024, 1, 15), amount=-1000, category="Rent", description="Rent"),
            # Savings: net 10500
            Transaction(account_id=2, date=date(2024, 1, 1), amount=10500, category="Transfer", description="Deposit"),
            # Investment: net 52000
            Transaction(account_id=3, date=date(2024, 1, 1), amount=52000, category="Investment", description="Buy"),
            # Retirement: net 105000
            Transaction(account_id=4, date=date(2024, 1, 1), amount=105000, category="Retirement", description="Contribution"),
        ]
        session.add_all(transactions)
        session.commit()
        
        # Test the service
        service = FinancialSummaryService(session)
        result = service.get_account_breakdown()
        
        print("\n" + "=" * 80)
        print("ACCOUNT BREAKDOWN TEST")
        print("=" * 80)
        print(f"Total Balance: ${result['total_balance']:,.2f}")
        print("\nBreakdown by Type:")
        for type_name, data in result['by_type'].items():
            print(f"  {type_name.capitalize():<15} ${data['amount']:>12,.2f}  ({data['percent']:>5.1f}%)")
        print("\nIndividual Accounts:")
        for acc in result['accounts']:
            print(f"  {acc['name']:<20} [{acc['category']:<12}] ${acc['balance']:>10,.2f}  ({acc['percent']:>5.1f}%)")
        print("=" * 80 + "\n")
        
        # Verify results: balances are cumulative transaction sums per account
        assert result['total_balance'] == 172500.0  # 5000 + 10500 + 52000 + 105000
        assert result['by_type']['liquidity']['amount'] == 15500.0   # checking(5000) + savings(10500)
        assert result['by_type']['investments']['amount'] == 157000.0  # investment(52000) + retirement(105000)
        assert result['by_type']['other']['amount'] == 0.0
        
        # Verify percentages add up to 100
        total_percent = sum(data['percent'] for data in result['by_type'].values())
        assert abs(total_percent - 100.0) < 0.1  # Allow small floating point differences
        
        # Verify accounts are sorted by balance (descending)
        assert result['accounts'][0]['name'] == "Retirement"  # Highest balance
        assert result['accounts'][0]['balance'] == 105000.0
        
        print("✅ Account breakdown test passed!\n")
        
    finally:
        session.close()


def test_edge_cases():
    """Test edge cases and error handling."""
    engine = create_engine('sqlite:///:memory:', echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        service = FinancialSummaryService(session)
        
        print("\n" + "=" * 80)
        print("EDGE CASES TEST")
        print("=" * 80)
        
        # Test with no data
        result = service.get_monthly_summary("2024-12")
        assert result['income'] == 0.0
        assert result['expenses'] == 0.0
        print("✓ No data case handled correctly")
        
        # Test invalid month format
        try:
            service.get_monthly_summary("invalid")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Invalid month format" in str(e)
            print("✓ Invalid month format error handled")
        
        # Test invalid date format
        try:
            service.get_spending_distribution("2024/01/01", "2024-01-31", "category")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Invalid date format" in str(e)
            print("✓ Invalid date format error handled")
        
        # Test invalid group_by
        try:
            service.get_spending_distribution("2024-01-01", "2024-01-31", "invalid")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "group_by must be" in str(e)
            print("✓ Invalid group_by error handled")
        
        # Test empty account breakdown
        result = service.get_account_breakdown()
        assert result['total_balance'] == 0.0
        assert result['accounts'] == []
        print("✓ Empty account breakdown handled correctly")
        
        print("=" * 80 + "\n")
        print("✅ All edge cases passed!\n")
        
    finally:
        session.close()


if __name__ == "__main__":
    test_get_monthly_summary()
    test_get_spending_distribution()
    test_get_account_breakdown()
    test_edge_cases()
    print("\n" + "=" * 80)
    print("ALL INTEGRATION TESTS PASSED! ✅")
    print("=" * 80 + "\n")
