"""Statement imports: idempotent row-level dedup, undoable batches, and transfer detection."""

import datetime
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.database.models import Account, ImportBatch, Transaction, Workspace
from src.blueprint import Blueprint
from src.services.fingerprint import compute_fingerprint
from src.services.merchant import merchant_key

# A transfer between own accounts shows up as an outflow on one and an inflow on the other, a few days apart.
MAX_TRANSFER_DAY_GAP = 3
TRANSFER_HINTS = (
    "bonifico", "giroconto", "trasferimento", "trasf.", "giro ", "ricarica", "pagamento carta", "addebito carta",
    "saldo carta", "carta di credito", "estratto conto carta", "transfer", "payment thank you", "credit card payment",
)
_IN_CHUNK = 500
# 'user' and 'rule' decisions are confirmed; the rest are suggestions waiting for review
SOURCES = ("file", "rule", "ai", "fallback", "user")
CONFIRMED_SOURCES = ("user", "rule")
# where a row came from: a statement the user uploaded, a bank API sync, a manual entry
ROW_SOURCES = ("statement", "bank", "manual")
# a bank-synced row with the same amount within this many days of a statement row is a suspect twin
SUSPECT_DAY_GAP = 3


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
    source = str(row.get("category_source") or "file")
    if source not in SOURCES:
        raise ValueError(f"row {index}: category_source must be one of {', '.join(SOURCES)}")
    confidence = row.get("confidence")
    external_id = row.get("external_id")
    return {
        "date": day,
        "amount": amount,
        "description": description[:500],
        "category": (str(row.get("category") or "other").strip() or "other")[:100],
        "currency": (str(row.get("currency") or "EUR").strip() or "EUR")[:3].upper(),
        "category_source": source,
        "confidence": float(confidence) if confidence is not None else None,
        "external_id": (str(external_id).strip()[:128] or None) if external_id is not None else None,
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
        source: str = "statement",
    ) -> Dict[str, Any]:
        """Add the rows that are not already in the account; return what happened.

        Rows are compared as a multiset: if a statement lists two identical rows and one is already stored, one is
        added. Re-importing an overlapping statement therefore never duplicates, and two real identical purchases
        are never collapsed into one.

        Rows that carry the bank's ``external_id`` are matched on it first (exact), then by fingerprint. A bank row
        that matches neither but has the same amount as a stored row without external_id within a few days is
        still added and marked ``duplicate_of`` that row: the bank and the statement may word the same movement
        differently, and only the user can tell.
        """
        account = self.session.get(Account, account_id)
        if account is None:
            raise ImportRequestError(404, f"Account {account_id} not found in this workspace")
        if source not in ROW_SOURCES:
            raise ImportRequestError(400, f"source must be one of {', '.join(ROW_SOURCES)}")

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

        known_external = self._stored_external_ids(account_id, {p["external_id"] for p in parsed if p["external_id"]})
        stored = self._stored_counts({p["fingerprint"] for p in parsed})
        seen: Counter = Counter()
        seen_external: set = set()
        to_add: List[Dict[str, Any]] = []
        for item in parsed:
            if item["external_id"]:
                if item["external_id"] in known_external or item["external_id"] in seen_external:
                    continue
                seen_external.add(item["external_id"])
            seen[item["fingerprint"]] += 1
            if seen[item["fingerprint"]] > stored.get(item["fingerprint"], 0):
                to_add.append(item)
        suspects = self._suspect_twins(account_id, [i for i in to_add if i["external_id"]])

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
            "suspect_duplicates": len(suspects),
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
        blueprint = self._blueprint()
        transactions = [
            Transaction(
                account_id=account_id, date=i["date"], amount=i["amount"],
                # stored under the blueprint's stable key when it knows the name
                category=(blueprint.resolve_category(i["category"]) if blueprint else None) or i["category"],
                description=i["description"], currency=i["currency"], fingerprint=i["fingerprint"],
                import_batch_id=batch.id, merchant_key=merchant_key(i["description"]),
                category_source=i["category_source"], confidence=i["confidence"],
                reviewed=i["category_source"] in CONFIRMED_SOURCES,
                source=source, external_id=i["external_id"], duplicate_of=suspects.get(id(i)),
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

    def _stored_external_ids(self, account_id: int, external_ids: Iterable[str]) -> set:
        wanted = list(external_ids)
        found: set = set()
        for start in range(0, len(wanted), _IN_CHUNK):
            chunk = wanted[start:start + _IN_CHUNK]
            rows = (
                self.session.query(Transaction.external_id)
                .filter(Transaction.account_id == account_id, Transaction.external_id.in_(chunk))
                .all()
            )
            found.update(r[0] for r in rows)
        return found

    def _suspect_twins(self, account_id: int, items: List[Dict[str, Any]]) -> Dict[int, int]:
        """For bank rows about to be added: the id of a stored row of the same account and amount, without an
        external_id, within SUSPECT_DAY_GAP days, not already claimed. Keyed by ``id(item)``."""
        if not items:
            return {}
        first = min(i["date"] for i in items) - datetime.timedelta(days=SUSPECT_DAY_GAP)
        last = max(i["date"] for i in items) + datetime.timedelta(days=SUSPECT_DAY_GAP)
        candidates = (
            self.session.query(Transaction)
            .filter(
                Transaction.account_id == account_id,
                Transaction.external_id.is_(None),
                Transaction.date >= first,
                Transaction.date <= last,
            )
            .all()
        )
        claimed = {
            r[0] for r in self.session.query(Transaction.duplicate_of).filter(Transaction.duplicate_of.isnot(None)).all()
        }
        by_amount: Dict[float, List[Transaction]] = defaultdict(list)
        for c in candidates:
            if c.id not in claimed:
                by_amount[round(c.amount, 2)].append(c)
        out: Dict[int, int] = {}
        for item in sorted(items, key=lambda i: i["date"]):
            pool = by_amount.get(round(item["amount"], 2)) or []
            match = min(
                (c for c in pool if abs((c.date - item["date"]).days) <= SUSPECT_DAY_GAP),
                key=lambda c: (abs((c.date - item["date"]).days), c.id),
                default=None,
            )
            if match is not None:
                out[id(item)] = match.id
                pool.remove(match)
        return out

    def list_suspects(self) -> List[Dict[str, Any]]:
        """Bank rows pointing at a statement row they may duplicate, with both sides."""
        rows = self.session.query(Transaction).filter(Transaction.duplicate_of.isnot(None)).order_by(Transaction.date.desc()).all()
        out = []
        for row in rows:
            twin = self.session.get(Transaction, row.duplicate_of)
            if twin is None:
                row.duplicate_of = None
                continue
            out.append({"transaction": row.to_dict(), "twin": twin.to_dict()})
        self.session.commit()
        return out

    def resolve_suspect(self, transaction_id: int, action: str) -> Dict[str, Any]:
        """``keep_both`` (two real movements), ``delete_this`` (the bank row is the twin: drop it) or
        ``delete_twin`` (drop the statement row, keep the bank row with its external_id)."""
        row = self.session.get(Transaction, transaction_id)
        if row is None or row.duplicate_of is None:
            raise ImportRequestError(404, f"Transaction {transaction_id} is not a suspect duplicate")
        twin = self.session.get(Transaction, row.duplicate_of)
        if action == "keep_both":
            row.duplicate_of = None
        elif action == "delete_this":
            # the statement row IS that bank movement: give it the bank's reference so later syncs recognise it
            if twin is not None and row.external_id and not twin.external_id:
                twin.external_id = row.external_id
            self.session.delete(row)
        elif action == "delete_twin":
            if twin is not None:
                # the statement row may carry the user's category decision: keep it on the surviving row
                if twin.reviewed and not row.reviewed:
                    row.category, row.category_source, row.reviewed, row.confidence = twin.category, twin.category_source, True, None
                self.session.delete(twin)
            row.duplicate_of = None
        else:
            raise ImportRequestError(400, "action must be keep_both, delete_this or delete_twin")
        self.session.commit()
        return {"resolved": transaction_id, "action": action}

    def resolve_suspects_bulk(self, action: str, max_day_gap: int = 0) -> Dict[str, Any]:
        """Settle every suspect pair whose dates are at most ``max_day_gap`` days apart with the same ``action``.
        Same-day, same-amount pairs after a first sync over an already-imported period are the statement's own
        rows in the bank's words: this is the one-click way to say so."""
        if action not in ("keep_both", "delete_this", "delete_twin"):
            raise ImportRequestError(400, "action must be keep_both, delete_this or delete_twin")
        done = 0
        for item in self.list_suspects():
            a, b = item["transaction"], item["twin"]
            gap = abs((datetime.date.fromisoformat(a["date"]) - datetime.date.fromisoformat(b["date"])).days)
            if gap <= max_day_gap:
                self.resolve_suspect(a["id"], action)
                done += 1
        return {"resolved": done, "action": action, "max_day_gap": max_day_gap, "remaining": len(self.list_suspects())}

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

    def _blueprint(self) -> Optional[Blueprint]:
        workspace = self.session.get(Workspace, self.workspace_id)
        try:
            return Blueprint.model_validate(workspace.blueprint) if workspace else None
        except ValueError:
            return None

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
