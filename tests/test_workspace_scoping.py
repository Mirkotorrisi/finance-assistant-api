"""A workspace-scoped session cannot see or write another workspace's rows."""

import pytest
from sqlalchemy import func

from src.database import init as db_init
from src.database.models import Account, MerchantRule, Transaction
from src.database.workspaces import create_workspace, default_workspace_id
from datetime import date


@pytest.fixture
def two_workspaces():
    db_init.init_database()
    admin = db_init.get_unscoped_session()
    a = create_workspace(admin, "A")
    b = create_workspace(admin, "B")
    a_id, b_id = a.id, b.id
    admin.close()
    sa, sb = db_init.get_db_session(a_id), db_init.get_db_session(b_id)
    for session, amount in ((sa, -10.0), (sb, -1000.0)):
        session.add(Transaction(date=date(2026, 1, 1), amount=amount, category="x", description="row"))
        session.add(Account(name="acc", type="checking"))
        session.add(MerchantRule(pattern="shop", category="x"))  # same pattern in both: allowed
        session.commit()
    yield a_id, b_id, sa, sb
    sa.close(), sb.close()
    db_init.close_database()


def test_reads_only_see_their_own_workspace(two_workspaces):
    _, _, sa, sb = two_workspaces
    assert [t.amount for t in sa.query(Transaction).all()] == [-10.0]
    assert [t.amount for t in sb.query(Transaction).all()] == [-1000.0]
    assert sa.query(func.sum(Transaction.amount)).scalar() == -10.0  # aggregates too
    assert sb.query(Account).count() == 1


def test_ids_from_another_workspace_are_not_reachable(two_workspaces):
    _, _, sa, sb = two_workspaces
    other_id = sb.query(Transaction).first().id
    assert sa.query(Transaction).filter(Transaction.id == other_id).first() is None
    assert sa.get(Transaction, other_id) is None


def test_writes_are_stamped_and_cross_workspace_writes_refused(two_workspaces):
    a_id, b_id, sa, _ = two_workspaces
    assert {t.workspace_id for t in sa.query(Transaction).all()} == {a_id}
    sa.add(Transaction(workspace_id=b_id, date=date(2026, 1, 2), amount=1.0, category="x", description="smuggled"))
    with pytest.raises(ValueError, match="Cannot write a row of workspace"):
        sa.commit()
    sa.rollback()


def test_bulk_update_and_delete_are_scoped(two_workspaces):
    _, _, sa, sb = two_workspaces
    sa.query(Transaction).update({"category": "changed"})
    sa.commit()
    assert [t.category for t in sb.query(Transaction).all()] == ["x"]
    sa.query(Transaction).delete()
    sa.commit()
    assert sb.query(Transaction).count() == 1


def test_default_workspace_prefers_owner_then_shared(two_workspaces):
    admin = db_init.get_unscoped_session()
    mine = create_workspace(admin, "Mine", owner_user_id="u1")
    assert default_workspace_id(admin, "u1") == mine.id
    assert default_workspace_id(admin, "someone-else") == default_workspace_id(admin)  # falls back to a shared one
    admin.close()
