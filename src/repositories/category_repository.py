from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from src.database.models import Category

class CategoryRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_name(self, name: str) -> Optional[Category]:
        return self.session.query(Category).filter(
            Category.name.ilike(name)
        ).first()

    def create(self, category: Category) -> Category:
        self.session.add(category)
        try:
            self.session.commit()
            self.session.refresh(category)
        except IntegrityError:
            self.session.rollback()
            raise
        return category

    def list_all(self, type_filter: Optional[str] = None) -> List[Category]:
        query = self.session.query(Category)
        if type_filter:
            query = query.filter(Category.type == type_filter)
        return query.order_by(Category.name).all()

    def get_existing_names(self) -> List[str]:
        categories = self.session.query(Category.name).distinct().order_by(Category.name).all()
        return [cat[0] for cat in categories]
