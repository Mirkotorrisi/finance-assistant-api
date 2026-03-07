"""Unit tests for database models."""

import pytest
from datetime import date
from unittest.mock import MagicMock


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    mock_session = MagicMock()
    return mock_session


class TestAccountModel:
    """Tests for Account model."""
    
    def test_account_model_exists(self):
        """Test that Account model exists and has required fields."""
        from src.database.models import Account
        
        assert hasattr(Account, 'id')
        assert hasattr(Account, 'name')
        assert hasattr(Account, 'type')
        assert hasattr(Account, 'currency')
        assert hasattr(Account, 'is_active')
        assert hasattr(Account, 'created_at')
        assert hasattr(Account, 'updated_at')
    
    def test_account_relationships(self):
        """Test that Account has the transactions relationship."""
        from src.database.models import Account
        
        assert hasattr(Account, 'transactions')
    
    def test_account_to_dict(self):
        """Test Account to_dict method."""
        from src.database.models import Account
        
        account = Account(
            id=1,
            name="Checking Account",
            type="checking",
            currency="USD",
            is_active=True
        )
        
        result = account.to_dict()
        
        assert result['id'] == 1
        assert result['name'] == "Checking Account"
        assert result['type'] == "checking"
        assert result['currency'] == "USD"
        assert result['is_active'] is True


class TestCategoryModelUpdates:
    """Tests for updated Category model."""
    
    def test_category_has_type_field(self):
        """Test that Category model has type field."""
        from src.database.models import Category
        
        assert hasattr(Category, 'type')
    
    def test_category_has_color_field(self):
        """Test that Category model has color field."""
        from src.database.models import Category
        
        assert hasattr(Category, 'color')
    
    def test_category_to_dict(self):
        """Test Category to_dict method includes new fields."""
        from src.database.models import Category
        
        category = Category(
            id=1,
            name="groceries",
            type="expense",
            color="#FF5733"
        )
        
        result = category.to_dict()
        
        assert result['id'] == 1
        assert result['name'] == "groceries"
        assert result['type'] == "expense"
        assert result['color'] == "#FF5733"


class TestTransactionModelUpdates:
    """Tests for updated Transaction model."""
    
    def test_transaction_has_account_id(self):
        """Test that Transaction model has account_id field."""
        from src.database.models import Transaction
        
        assert hasattr(Transaction, 'account_id')
    
    def test_transaction_to_dict_includes_account_id(self):
        """Test Transaction to_dict includes account_id and currency."""
        from src.database.models import Transaction
        
        transaction = Transaction(
            id=1,
            account_id=1,
            date=date(2026, 1, 12),
            amount=-50.0,
            category="food",
            description="Grocery shopping",
            currency="USD"
        )
        
        result = transaction.to_dict()
        
        assert result['id'] == 1
        assert result['account_id'] == 1
        assert result['date'] == "2026-01-12"
        assert result['amount'] == -50.0
        assert result['category'] == 'food'
        assert result['description'] == 'Grocery shopping'
        assert result['currency'] == 'USD'


class TestDatabaseExports:
    """Tests for database module exports."""
    
    def test_database_module_exports_account(self):
        """Test that database module exports Account."""
        from src.database import Account
        assert Account is not None
    
    def test_database_module_exports_category(self):
        """Test that database module exports Category."""
        from src.database import Category
        assert Category is not None
    
    def test_database_module_exports_transaction(self):
        """Test that database module exports Transaction."""
        from src.database import Transaction
        assert Transaction is not None


class TestDataModelDesignPrinciples:
    """Tests to verify adherence to core design principles."""
    
    def test_transaction_is_source_of_truth(self):
        """Test that Transaction is the single source of truth for financial data."""
        from src.database.models import Transaction
        
        # Verify Transaction has required fields for aggregation
        assert hasattr(Transaction, 'account_id')
        assert hasattr(Transaction, 'date')
        assert hasattr(Transaction, 'amount')
    
    def test_no_snapshot_model(self):
        """Test that MonthlyAccountSnapshot model no longer exists."""
        import src.database.models as models
        assert not hasattr(models, 'MonthlyAccountSnapshot')
    
    def test_account_has_no_snapshots_relationship(self):
        """Test that Account no longer has a snapshots relationship."""
        from src.database.models import Account
        assert not hasattr(Account, 'snapshots')
