from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc
from src.database.models import MonthlyAccountSnapshot

class SnapshotRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_account_year_month(self, account_id: int, year: int, month: int) -> Optional[MonthlyAccountSnapshot]:
        return self.session.query(MonthlyAccountSnapshot).filter(
            and_(
                MonthlyAccountSnapshot.account_id == account_id,
                MonthlyAccountSnapshot.year == year,
                MonthlyAccountSnapshot.month == month
            )
        ).first()

    def create(self, snapshot: MonthlyAccountSnapshot) -> MonthlyAccountSnapshot:
        self.session.add(snapshot)
        self.session.commit()
        self.session.refresh(snapshot)
        return snapshot

    def update(self, snapshot: MonthlyAccountSnapshot) -> MonthlyAccountSnapshot:
        self.session.commit()
        self.session.refresh(snapshot)
        return snapshot

    def list_by_account(self, account_id: int, 
                       start_year: Optional[int] = None, 
                       start_month: Optional[int] = None, 
                       end_year: Optional[int] = None, 
                       end_month: Optional[int] = None) -> List[MonthlyAccountSnapshot]:
        query = self.session.query(MonthlyAccountSnapshot).filter(
            MonthlyAccountSnapshot.account_id == account_id
        )
        
        if start_year is not None and start_month is not None:
             query = query.filter(
                (MonthlyAccountSnapshot.year > start_year) |
                (
                    (MonthlyAccountSnapshot.year == start_year) &
                    (MonthlyAccountSnapshot.month >= start_month)
                )
            )
        
        if end_year is not None and end_month is not None:
            query = query.filter(
                (MonthlyAccountSnapshot.year < end_year) |
                (
                    (MonthlyAccountSnapshot.year == end_year) &
                    (MonthlyAccountSnapshot.month <= end_month)
                )
            )
            
        return query.order_by(
            desc(MonthlyAccountSnapshot.year),
            desc(MonthlyAccountSnapshot.month)
        ).all()

    def get_total_balance_for_month(self, year: int, month: int) -> float:
        result = self.session.query(
            func.sum(MonthlyAccountSnapshot.ending_balance)
        ).filter(
            and_(
                MonthlyAccountSnapshot.year == year,
                MonthlyAccountSnapshot.month == month
            )
        ).scalar()
        return result or 0.0

    def get_current_total_balance(self) -> float:
        # Get the most recent snapshot for each account
        subquery = self.session.query(
            MonthlyAccountSnapshot.account_id,
            func.max(MonthlyAccountSnapshot.year * 100 + MonthlyAccountSnapshot.month).label('max_period')
        ).group_by(MonthlyAccountSnapshot.account_id).subquery()
        
        # Join with snapshots to get the actual ending balances
        result = self.session.query(
            func.sum(MonthlyAccountSnapshot.ending_balance)
        ).join(
            subquery,
            and_(
                MonthlyAccountSnapshot.account_id == subquery.c.account_id,
                MonthlyAccountSnapshot.year * 100 + MonthlyAccountSnapshot.month == subquery.c.max_period
            )
        ).scalar()
        
        return result or 0.0

    def get_total_expenses_for_month(self, year: int, month: int) -> float:
        result = self.session.query(
            func.sum(MonthlyAccountSnapshot.total_expense)
        ).filter(
            and_(
                MonthlyAccountSnapshot.year == year,
                MonthlyAccountSnapshot.month == month
            )
        ).scalar()
        return result or 0.0

    def get_total_income_for_month(self, year: int, month: int) -> float:
        result = self.session.query(
            func.sum(MonthlyAccountSnapshot.total_income)
        ).filter(
            and_(
                MonthlyAccountSnapshot.year == year,
                MonthlyAccountSnapshot.month == month
            )
        ).scalar()
        return result or 0.0

    def get_trend(self, account_id: Optional[int] = None, limit: int = 12) -> List[MonthlyAccountSnapshot]:
        query = self.session.query(MonthlyAccountSnapshot)
        if account_id is not None:
            query = query.filter(MonthlyAccountSnapshot.account_id == account_id)
        
        return query.order_by(
            desc(MonthlyAccountSnapshot.year),
            desc(MonthlyAccountSnapshot.month)
        ).limit(limit).all()
