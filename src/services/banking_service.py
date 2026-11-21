"""Bank connections: the consents the user gave, the accounts behind them and the sync bookkeeping.

The secret that grants access (the aggregator's session id) lives in the gateway's encrypted store; here only
``session_ref`` points at it. Deleting a connection here does not revoke the consent: the gateway does both.
"""

from __future__ import annotations

import builtins
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from src.database.models import Account, BankAccountLink, BankConnection

STATUSES = ("active", "expired", "revoked", "error")


class BankingService:
    def __init__(self, session: Session):
        self.session = session
        self.workspace_id: int = session.info["workspace_id"]

    # ------------------------------------------------------------------ connections

    def list(self) -> builtins.list[dict[str, Any]]:
        rows = self.session.query(BankConnection).order_by(BankConnection.id).all()
        return [r.to_dict() for r in rows]

    def get(self, connection_id: int) -> BankConnection:
        row = self.session.get(BankConnection, connection_id)
        if row is None or row.workspace_id != self.workspace_id:
            raise LookupError(f"Bank connection {connection_id} not found")
        return row

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Register a consent. With ``renew_connection_id`` the existing row keeps its id and its account links
        (matched by identification_hash) and only the session, validity and per-session handles change."""
        accounts = data.get("accounts") or []
        renew_id = data.get("renew_connection_id")
        if renew_id is not None:
            row = self.get(renew_id)
            row.session_ref = data["session_ref"]
            row.valid_until = data.get("valid_until")
            row.status = "active"
            row.last_error = None
            row.updated_at = datetime.utcnow()
            by_hash = {link.identification_hash: link for link in row.links}
            for item in accounts:
                link = by_hash.get(item["identification_hash"])
                if link is None:
                    link = BankAccountLink(connection=row, identification_hash=item["identification_hash"])
                    self.session.add(link)
                self._fill_link(link, item)
        else:
            row = BankConnection(
                provider=data.get("provider") or "enablebanking",
                aspsp_name=data["aspsp_name"],
                aspsp_country=data["aspsp_country"].upper(),
                psu_type=data.get("psu_type") or "personal",
                session_ref=data["session_ref"],
                valid_until=data.get("valid_until"),
                status="active",
            )
            self.session.add(row)
            for item in accounts:
                link = BankAccountLink(connection=row, identification_hash=item["identification_hash"])
                self._fill_link(link, item)
                self.session.add(link)
        self.session.commit()
        self.session.refresh(row)
        return row.to_dict()

    @staticmethod
    def _fill_link(link: BankAccountLink, item: dict[str, Any]) -> None:
        link.bank_uid = item.get("bank_uid")
        link.iban_masked = item.get("iban_masked")
        link.label = item.get("label")
        link.currency = (item.get("currency") or None)
        link.cash_account_type = item.get("cash_account_type")
        link.updated_at = datetime.utcnow()

    def update(self, connection_id: int, changes: dict[str, Any]) -> dict[str, Any]:
        row = self.get(connection_id)
        for field in ("status", "sync_balances", "sync_transactions", "last_sync_at", "last_sync_status", "last_error", "valid_until"):
            if field in changes and changes[field] is not None or (field == "last_error" and "last_error" in changes):
                setattr(row, field, changes[field])
        if row.status not in STATUSES:
            raise ValueError(f"status must be one of {', '.join(STATUSES)}")
        row.updated_at = datetime.utcnow()
        self.session.commit()
        return row.to_dict()

    def delete(self, connection_id: int) -> None:
        row = self.get(connection_id)
        self.session.delete(row)
        self.session.commit()

    # ------------------------------------------------------------------ account links

    def update_link(self, connection_id: int, link_id: int, changes: dict[str, Any]) -> dict[str, Any]:
        row = self.get(connection_id)
        link = next((l for l in row.links if l.id == link_id), None)
        if link is None:
            raise LookupError(f"Account link {link_id} not found")
        if changes.get("create_account"):
            new = changes["create_account"]
            account = Account(name=new["name"], type=new.get("account_type") or "checking", currency=link.currency or "EUR")
            self.session.add(account)
            self.session.flush()
            link.account_id = account.id
        elif changes.get("unlink"):
            link.account_id = None
        elif changes.get("account_id") is not None:
            account = self.session.get(Account, changes["account_id"])
            if account is None:
                raise LookupError(f"Account {changes['account_id']} not found in this workspace")
            taken = (
                self.session.query(BankAccountLink)
                .filter(BankAccountLink.account_id == account.id, BankAccountLink.id != link.id)
                .first()
            )
            if taken is not None:
                raise ValueError(f"Account {account.id} is already fed by another bank account")
            link.account_id = account.id
        for field in ("enabled", "last_transaction_date", "last_balance", "last_balance_date"):
            if changes.get(field) is not None:
                setattr(link, field, changes[field])
        link.updated_at = datetime.utcnow()
        self.session.commit()
        return link.to_dict()

    # ------------------------------------------------------------------ scheduling

    @staticmethod
    def due(session: Session, max_age_hours: float = 12) -> builtins.list[dict[str, Any]]:
        """Across every workspace (unscoped session): active connections not synced in the last ``max_age_hours``.
        Used by the gateway's scheduler, which syncs them one by one."""
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        rows = (
            session.query(BankConnection)
            .filter(BankConnection.status == "active")
            .filter((BankConnection.last_sync_at.is_(None)) | (BankConnection.last_sync_at < cutoff))
            .order_by(BankConnection.last_sync_at.is_(None).desc(), BankConnection.last_sync_at)
            .all()
        )
        return [{"workspace_id": r.workspace_id, "connection_id": r.id, "last_sync_at": r.last_sync_at.isoformat() if r.last_sync_at else None} for r in rows]

    @staticmethod
    def expiring(session: Session, within_days: int = 14) -> builtins.list[dict[str, Any]]:
        limit = datetime.utcnow() + timedelta(days=within_days)
        rows = (
            session.query(BankConnection)
            .filter(BankConnection.status == "active", BankConnection.valid_until.isnot(None), BankConnection.valid_until <= limit)
            .all()
        )
        return [{"workspace_id": r.workspace_id, "connection_id": r.id, "aspsp_name": r.aspsp_name, "valid_until": r.valid_until.isoformat()} for r in rows]
