"""Integration test to verify the financial data endpoint works."""

import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database.models import Base, Account, MonthlyAccountSnapshot
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
        
        # Create test snapshots for 2024
        snapshots_data = [
            # January
            (1, 2024, 1, 5000, 5200, 500, 300),  # checking
            (2, 2024, 1, 10000, 10500, 0, 0),    # investment
            (3, 2024, 1, 3000, 3100, 200, 100),  # savings
            # February
            (1, 2024, 2, 5200, 5400, 600, 400),
            (2, 2024, 2, 10500, 11000, 0, 0),
            (3, 2024, 2, 3100, 3200, 300, 200),
            # March
            (1, 2024, 3, 5400, 5800, 700, 300),
            (2, 2024, 3, 11000, 11500, 0, 0),
            (3, 2024, 3, 3200, 3400, 400, 200),
        ]
        
        for account_id, year, month, start_bal, end_bal, income, expense in snapshots_data:
            snapshot = MonthlyAccountSnapshot(
                account_id=account_id,
                year=year,
                month=month,
                starting_balance=start_bal,
                ending_balance=end_bal,
                total_income=income,
                total_expense=expense
            )
            session.add(snapshot)
        
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
        assert result['currentNetWorth'] == 20700.0  # March totals: 5800 + 11500 + 3400
        
        # Check January data
        jan_data = result['monthlyData'][0]
        assert jan_data['month'] == 'Jan'
        assert jan_data['netWorth'] == 18800.0  # 5200 + 10500 + 3100
        assert jan_data['income'] == 700.0  # 500 + 0 + 200
        assert jan_data['expenses'] == 400.0  # 300 + 0 + 100
        assert jan_data['net'] == 300.0  # 700 - 400
        
        # Check account breakdown (March values)
        assert breakdown['liquidity'] == 9200.0  # checking + savings: 5800 + 3400
        assert breakdown['investments'] == 11500.0  # investment
        assert breakdown['otherAssets'] == 0.0
        
        print("\n✅ All assertions passed! The financial data endpoint is working correctly.\n")
        
    finally:
        session.close()


if __name__ == "__main__":
    test_financial_data_endpoint()
