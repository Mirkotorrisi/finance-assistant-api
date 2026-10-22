"""Row-level scoping by workspace, enforced at the session.

A session opened with ``session.info["workspace_id"] = N`` can only see rows of workspace N (selects, updates
and deletes get the filter added automatically) and stamps N on every row it inserts. Code written against
accounts/transactions/rules therefore cannot reach another project's data, even by guessing an id.
"""

from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

from src.database.models import Account, ImportBatch, MerchantRule, Transaction

SCOPED_MODELS = (Account, Transaction, MerchantRule, ImportBatch)


@event.listens_for(Session, "do_orm_execute")
def _filter_by_workspace(state) -> None:
    workspace_id = state.session.info.get("workspace_id")
    if workspace_id is None or not (state.is_select or state.is_update or state.is_delete):
        return
    for model in SCOPED_MODELS:
        state.statement = state.statement.options(
            with_loader_criteria(model, model.workspace_id == workspace_id, include_aliases=True)
        )


@event.listens_for(Session, "before_flush")
def _stamp_workspace(session: Session, flush_context, instances) -> None:
    workspace_id = session.info.get("workspace_id")
    if workspace_id is None:
        return
    for obj in session.new:
        if isinstance(obj, SCOPED_MODELS):
            if obj.workspace_id is None:
                obj.workspace_id = workspace_id
            elif obj.workspace_id != workspace_id:
                raise ValueError(
                    f"Cannot write a row of workspace {obj.workspace_id} from a session scoped to {workspace_id}"
                )
