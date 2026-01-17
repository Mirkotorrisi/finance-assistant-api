#!/usr/bin/env python3
"""
Script to populate MonthlyAccountSnapshot data from existing transactions.

This script:
1. Finds all accounts
2. For each account, groups transactions by year/month
3. Calculates monthly aggregates (income, expenses, balances)
4. Creates or updates MonthlyAccountSnapshot records
"""

import os
import sys
from datetime import date
from collections import defaultdict

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func
from src.database.init import init_database, get_db_session
from src.database.models import Account, Transaction, MonthlyAccountSnapshot
from src.services.account_service import AccountService


def populate_snapshots_from_transactions(session, account_id: int, year: int, month: int, starting_balance: float = 0.0):
    """Calculate and create a snapshot from transaction data for a specific account/month.
    
    Args:
        session: Database session
        account_id: Account ID
        year: Year
        month: Month (1-12)
        starting_balance: Starting balance for the month (default 0.0)
    """
    # Get all transactions for this account/month
    transactions = session.query(Transaction).filter(
        Transaction.account_id == account_id,
        func.extract('year', Transaction.date) == year,
        func.extract('month', Transaction.date) == month
    ).all()
    
    # Calculate aggregates
    total_income = sum(t.amount for t in transactions if t.amount > 0)
    total_expense = abs(sum(t.amount for t in transactions if t.amount < 0))
    net_change = sum(t.amount for t in transactions)
    ending_balance = starting_balance + net_change
    
    # Check if snapshot already exists
    existing = session.query(MonthlyAccountSnapshot).filter(
        MonthlyAccountSnapshot.account_id == account_id,
        MonthlyAccountSnapshot.year == year,
        MonthlyAccountSnapshot.month == month
    ).first()
    
    if existing:
        # Update existing snapshot
        existing.starting_balance = starting_balance
        existing.ending_balance = ending_balance
        existing.total_income = total_income
        existing.total_expense = total_expense
        session.commit()
        print(f"   Updated snapshot for account {account_id}, {year}-{month:02d}")
    else:
        # Create new snapshot
        snapshot = MonthlyAccountSnapshot(
            account_id=account_id,
            year=year,
            month=month,
            starting_balance=starting_balance,
            ending_balance=ending_balance,
            total_income=total_income,
            total_expense=total_expense
        )
        session.add(snapshot)
        session.commit()
        print(f"   Created snapshot for account {account_id}, {year}-{month:02d}")
    
    return ending_balance


def main():
    """Main function to populate all snapshots."""
    print("=" * 70)
    print("Populating Monthly Account Snapshots from Transactions")
    print("=" * 70)
    print()
    
    # Initialize database
    init_database()
    session = get_db_session()
    
    try:
        # Get all accounts
        accounts = session.query(Account).filter(Account.is_active == True).all()
        
        if not accounts:
            print("No active accounts found. Please create accounts first.")
            return
        
        print(f"Found {len(accounts)} active account(s)")
        print()
        
        for account in accounts:
            print(f"Processing account: {account.name} (ID: {account.id})")
            
            # Get all unique year/month combinations for this account's transactions
            periods = session.query(
                func.extract('year', Transaction.date).label('year'),
                func.extract('month', Transaction.date).label('month')
            ).filter(
                Transaction.account_id == account.id
            ).distinct().order_by('year', 'month').all()
            
            if not periods:
                print(f"   No transactions found for this account")
                print()
                continue
            
            print(f"   Found {len(periods)} month(s) with transactions")
            
            # Track running balance
            running_balance = 0.0
            
            for year, month in periods:
                year = int(year)
                month = int(month)
                
                # Create/update snapshot for this period
                ending_balance = populate_snapshots_from_transactions(
                    session, account.id, year, month, running_balance
                )
                
                # Update running balance for next month
                running_balance = ending_balance
            
            print()
        
        print("=" * 70)
        print("Snapshot population complete!")
        print("=" * 70)
        
    finally:
        session.close()


if __name__ == "__main__":
    main()
