"""Statement imports: idempotent row-level dedup, undoable batches, and transfer detection."""

import datetime
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.database.models import Account, ImportBatch, Transaction, Workspace
from src.services.fingerprint import compute_fingerprint

# A transfer between own accounts shows up as an outflow on one and an inflow on the other, a few days apart.
MAX_TRANSFER_DAY_GAP = 3
TRANSFER_HINTS = (
    "bonifico", "giroconto", "trasferimento", "trasf.", "giro ", "ricarica", "pagamento carta", "addebito carta",
    "saldo carta", "carta di credito", "estratto conto carta", "transfer", "payment thank you", "credit card payment",
)
_IN_CHUNK = 500


class ImportRequestError(Exception):
    """Invalid import request (maps to HTTP 4xx)."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _has_transfer_hint(description: Optional[str]) -> bool:
    text = (description or "").lower()
    return any(hint in text for hint in TRANSFER_HINTS)


def _parse_row(index: int, row: Dict[str, Any]) -> Dict[str, Any]:
    try:
        day = datetime.date.fromisoformat(str(row["date"])[:10])
        amount = float(row["amount"])
        description = str(row["description"]).strip()
    except (KeyError, ValueError, TypeError) as e:
        raise ValueError(f"row {index}: {e!r}")
    if not description:
        raise ValueError(f"row {index}: empty description")
    return {
        "date": day,
        "amount": amount,
        "description": description[:500],
        "category": (str(row.get("category") or "other").strip() or "other")[:100],
        "currency": (str(row.get("currency") or "EUR").strip() or "EUR")[:3].upper(),
    }


class ImportService:
    def __init__(self, session: Session):
        self.session = session
        self.workspace_id: int = session.info["workspace_id"]

    # ------------------------------------------------------------------ import

    def import_transactions(
        self,
        account_id: int,
        rows: List[Dict[str, Any]],
        filename: Optional[str] = None,
        file_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add the rows that are not already in the account; return what happened.

        Rows are compared as a multiset: if a statement lists two identical rows and one is already stored, one is
        added. Re-importing an overlapping statement therefore never duplicates, and two real identical purchases
        are never collapsed into one.
        """
        account = self.session.get(Account, account_id)
        if account is None:
            raise ImportRequestError(404, f"Account {account_id} not found in this workspace")

        parsed: List[Dict[str, Any]] = []
        invalid: List[str] = []
        for index, raw in enumerate(rows):
            try:
                parsed.append(_parse_row(index, raw))
            except ValueError as e:
                invalid.append(str(e))
        for item in parsed:
            item["fingerprint"] = compute_fingerprint(
                self.workspace_id, account_id, item["date"], item["amount"], item["description"]
            )

        stored = self._stored_counts({p["fingerprint"] for p in parsed})
        seen: Counter = Counter()
        to_add: List[Dict[str, Any]] = []
        for item in parsed:
            seen[item["fingerprint"]] += 1
            if seen[item["fingerprint"]] > stored.get(item["fingerprint"], 0):
                to_add.append(item)

        duplicate_file = bool(
            file_hash
            and self.session.query(ImportBatch).filter(ImportBatch.file_hash == file_hash, ImportBatch.account_id == account_id).first()
        )

        result: Dict[str, Any] = {
            "batch_id": None,
            "row_count": len(parsed),
            "added_count": len(to_add),
            "skipped_count": len(parsed) - len(to_add),
            "invalid_rows": invalid,
            "duplicate_file": duplicate_file,
            "transfers_detected": 0,
            "transactions": [],
        }
        if not to_add:
            return result

        batch = ImportBatch(
            account_id=account_id, filename=filename, file_hash=file_hash,
            row_count=len(parsed), added_count=len(to_add), skipped_count=len(parsed) - len(to_add),
        )
        self.session.add(batch)
        self.session.flush()
        transactions = [
            Transaction(
                account_id=account_id, date=i["date"], amount=i["amount"], category=i["category"],
                description=i["description"], currency=i["currency"], fingerprint=i["fingerprint"],
                import_batch_id=batch.id,
            )
            for i in to_add
        ]
        self.session.add_all(transactions)
        self.session.commit()

        if self._detect_enabled():
            result["transfers_detected"] = len(self.detect_transfers(only_ids={t.id for t in transactions}))
        for t in transactions:
            self.session.refresh(t)
        result["batch_id"] = batch.id
        result["transactions"] = [t.to_dict() for t in transactions]
        return result

    def _stored_counts(self, fingerprints: Iterable[str]) -> Dict[str, int]:
        wanted = list(fingerprints)
        counts: Dict[str, int] = {}
        for start in range(0, len(wanted), _IN_CHUNK):
            chunk = wanted[start : start + _IN_CHUNK]
            for fp, n in (
                self.session.query(Transaction.fingerprint, func.count(Transaction.id))
                .filter(Transaction.fingerprint.in_(chunk))
                .group_by(Transaction.fingerprint)
            ):
                counts[fp] = n
        return counts

    def _detect_enabled(self) -> bool:
        workspace = self.session.get(Workspace, self.workspace_id)
        settings = (workspace.blueprint or {}).get("settings", {}) if workspace else {}
        return bool(settings.get("detect_transfers", True))

    # ------------------------------------------------------------------ batches

    def list_batches(self) -> List[Dict[str, Any]]:
        return [b.to_dict() for b in self.session.query(ImportBatch).order_by(ImportBatch.id.desc()).all()]

    def undo_batch(self, batch_id: int) -> Dict[str, Any]:
        batch = self.session.get(ImportBatch, batch_id)
        if batch is None:
            raise ImportRequestError(404, f"Import {batch_id} not found")
        rows = self.session.query(Transaction).filter(Transaction.import_batch_id == batch_id).all()
        removed_ids = {t.id for t in rows}
        for partner in self.session.query(Transaction).filter(Transaction.transfer_pair_id.in_(removed_ids or {-1})).all():
            if partner.id not in removed_ids:  # a transfer loses its other half
                partner.is_transfer, partner.transfer_pair_id = False, None
        for t in rows:
            self.session.delete(t)
        self.session.delete(batch)
        self.session.commit()
        return {"batch_id": batch_id, "transactions_removed": len(removed_ids)}

    # ------------------------------------------------------------------ transfers

    def detect_transfers(
        self,
        only_ids: Optional[set] = None,
        include_unhinted: bool = False,
        dry_run: bool = False,
    ) -> List[Dict[str, Any]]:
        """Pair outflows with matching inflows on another account (same amount, within a few days).

        Only unambiguous pairs are made: the outflow has exactly one candidate and so does the inflow. By default a
        pair also needs a transfer keyword (bonifico, giroconto, pagamento carta, ...) in either description;
        ``include_unhinted`` also returns keyword-less pairs (use with ``dry_run`` to suggest them to the user).
        ``only_ids`` keeps the pairs that involve at least one of those transactions.
        """
        rows = (
            self.session.query(Transaction)
            .filter(Transaction.is_transfer.is_(False), Transaction.account_id.isnot(None))
            .all()
        )
        outs = [t for t in rows if t.amount < 0]
        ins_by_cents: Dict[int, List[Transaction]] = defaultdict(list)
        for t in rows:
            if t.amount > 0:
                ins_by_cents[round(t.amount * 100)].append(t)

        def near(a: Transaction, b: Transaction) -> bool:
            return b.account_id != a.account_id and abs((b.date - a.date).days) <= MAX_TRANSFER_DAY_GAP

        out_candidates = {a.id: [b for b in ins_by_cents.get(round(-a.amount * 100), []) if near(a, b)] for a in outs}
        in_candidates: Dict[int, List[Transaction]] = defaultdict(list)
        for a in outs:
            for b in out_candidates[a.id]:
                in_candidates[b.id].append(a)

        pairs: List[Dict[str, Any]] = []
        for a in outs:
            candidates = out_candidates[a.id]
            if len(candidates) != 1:
                continue
            b = candidates[0]
            if len(in_candidates[b.id]) != 1:
                continue
            if only_ids is not None and a.id not in only_ids and b.id not in only_ids:
                continue
            hinted = _has_transfer_hint(a.description) or _has_transfer_hint(b.description)
            if not hinted and not include_unhinted:
                continue
            pairs.append({
                "out_id": a.id, "in_id": b.id, "amount": abs(a.amount),
                "out_date": a.date.isoformat(), "in_date": b.date.isoformat(),
                "out_description": a.description, "in_description": b.description, "hinted": hinted,
            })
            if not dry_run:
                a.is_transfer, a.transfer_pair_id = True, b.id
                b.is_transfer, b.transfer_pair_id = True, a.id
        if pairs and not dry_run:
            self.session.commit()
        return pairs

    def pair_transfer(self, first_id: int, second_id: int) -> Dict[str, Any]:
        first, second = self.session.get(Transaction, first_id), self.session.get(Transaction, second_id)
        if first is None or second is None or first.id == second.id:
            raise ImportRequestError(404, "Both transactions must exist and be different")
        first.is_transfer, first.transfer_pair_id = True, second.id
        second.is_transfer, second.transfer_pair_id = True, first.id
        self.session.commit()
        return {"paired": [first.id, second.id]}

    def unmark_transfer(self, transaction_id: int) -> Dict[str, Any]:
        transaction = self.session.get(Transaction, transaction_id)
        if transaction is None:
            raise ImportRequestError(404, f"Transaction {transaction_id} not found")
        cleared = [transaction.id]
        partner = self.session.get(Transaction, transaction.transfer_pair_id) if transaction.transfer_pair_id else None
        transaction.is_transfer, transaction.transfer_pair_id = False, None
        if partner is not None:
            partner.is_transfer, partner.transfer_pair_id = False, None
            cleared.append(partner.id)
        self.session.commit()
        return {"cleared": cleared}
