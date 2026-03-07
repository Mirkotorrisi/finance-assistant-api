"""Integration test to verify the financial data endpoint works."""

import sys
import os
from datetime import date

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database.models import Base, Account, Transaction
from src.services.financial_data_service import FinancialDataService


def test_financial_data_endpoint():
    """Test the financial data service with in-memory database."""
    # Create in-memory SQLite database
    engine = create_engine('sqlite:///:memory:', echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Create test accounts
        checking = Account(id=1, name="Checking", type="checking", currency="EUR")
        investment = Account(id=2, name="Investment", type="investment", currency="EUR")
        savings = Account(id=3, name="Savings", type="savings", currency="EUR")
        
        session.add_all([checking, investment, savings])
        session.commit()
        
        # Create test transactions for 2024 (income = positive, expense = negative)
        transactions = [
            # January
            Transaction(account_id=1, date=date(2024, 1, 15), amount=500, category="Salary", description="Salary"),
            Transaction(account_id=1, date=date(2024, 1, 20), amount=-300, category="Rent", description="Rent"),
            Transaction(account_id=3, date=date(2024, 1, 15), amount=200, category="Interest", description="Interest"),
            Transaction(account_id=3, date=date(2024, 1, 20), amount=-100, category="Fee", description="Fee"),
            # February
            Transaction(account_id=1, date=date(2024, 2, 15), amount=600, category="Salary", description="Salary"),
            Transaction(account_id=1, date=date(2024, 2, 20), amount=-400, category="Rent", description="Rent"),
            Transaction(account_id=3, date=date(2024, 2, 15), amount=300, category="Interest", description="Interest"),
            Transaction(account_id=3, date=date(2024, 2, 20), amount=-200, category="Fee", description="Fee"),
            # March
            Transaction(account_id=1, date=date(2024, 3, 15), amount=700, category="Salary", description="Salary"),
            Transaction(account_id=1, date=date(2024, 3, 20), amount=-300, category="Rent", description="Rent"),
            Transaction(account_id=3, date=date(2024, 3, 15), amount=400, category="Interest", description="Interest"),
            Transaction(account_id=3, date=date(2024, 3, 20), amount=-200, category="Fee", description="Fee"),
        ]
        session.add_all(transactions)
        session.commit()
        
        # Test the service
        service = FinancialDataService(session)
        result = service.get_financial_data(2024)
        
        print("=" * 80)
        print("FINANCIAL DATA TEST RESULTS FOR 2024")
        print("=" * 80)
        
        print(f"\nYear: {result['year']}")
        print(f"Current Net Worth: ${result['currentNetWorth']:,.2f}")
        print(f"Net Savings: ${result['netSavings']:,.2f}")
        
        print("\n" + "-" * 80)
        print("MONTHLY DATA")
        print("-" * 80)
        print(f"{'Month':<6} {'Net Worth':>12} {'Income':>12} {'Expenses':>12} {'Net':>12}")
        print("-" * 80)
        
        for month_data in result['monthlyData'][:3]:  # Show first 3 months
            print(f"{month_data['month']:<6} ${month_data['netWorth']:>11,.2f} "
                  f"${month_data['income']:>11,.2f} ${month_data['expenses']:>11,.2f} "
                  f"${month_data['net']:>11,.2f}")
        
        print("\n" + "-" * 80)
        print("ACCOUNT BREAKDOWN (as of most recent month)")
        print("-" * 80)
        breakdown = result['accountBreakdown']
        print(f"Liquidity (checking, savings):  ${breakdown['liquidity']:>12,.2f}")
        print(f"Investments:                    ${breakdown['investments']:>12,.2f}")
        print(f"Other Assets:                   ${breakdown['otherAssets']:>12,.2f}")
        print("=" * 80)
        
        # Verify calculations
        assert result['year'] == 2024
        # currentNetWorth = sum of all transactions up to end of March
        # checking: 500-300 + 600-400 + 700-300 = 200+200+400 = 800
        # savings:  200-100 + 300-200 + 400-200 = 100+100+200 = 400
        # investment: 0 (no transactions)
        assert result['currentNetWorth'] == 1200.0
        
        # Check January data
        jan_data = result['monthlyData'][0]
        assert jan_data['month'] == 'Jan'
        # netWorth for Jan = cumulative sum through Jan = 200 + 100 = 300
        assert jan_data['netWorth'] == 300.0
        assert jan_data['income'] == 700.0   # 500 + 200
        assert jan_data['expenses'] == 400.0  # 300 + 100
        assert jan_data['net'] == 300.0       # 700 - 400
        
        # Check account breakdown (cumulative through March)
        # checking: 800, savings: 400, investment: 0
        assert breakdown['liquidity'] == 1200.0   # checking + savings: 800 + 400
        assert breakdown['investments'] == 0.0    # no investment transactions
        assert breakdown['otherAssets'] == 0.0
        
        print("\n✅ All assertions passed! The financial data endpoint is working correctly.\n")
        
    finally:
        session.close()


if __name__ == "__main__":
    test_financial_data_endpoint()
