"""Client profile and decision log: the advisor's persistent memory of one workspace."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from src.database.models import AdvisorDecision, ClientProfileVersion
from src.database.models import ClientProfile as ProfileRow
from src.profile import ClientProfile, merge_profile

DECISION_STATUSES = ("proposed", "accepted", "rejected", "done")


class ProfileService:
    def __init__(self, session: Session):
        self.session = session
        self.workspace_id: int = session.info["workspace_id"]

    # ------------------------------------------------------------------ profile

    def _row(self) -> ProfileRow | None:
        return self.session.query(ProfileRow).filter(ProfileRow.workspace_id == self.workspace_id).one_or_none()

    def current(self) -> ClientProfile:
        row = self._row()
        return ClientProfile.model_validate(row.document) if row else ClientProfile()

    def get(self) -> dict[str, Any]:
        return self._response(self._row())

    def replace(self, profile: ClientProfile, source: str = "user") -> dict[str, Any]:
        """Store ``profile`` as the new version (the previous one is kept in the history)."""
        row = self._row()
        if row is None:
            row = ProfileRow(workspace_id=self.workspace_id, document=profile.to_json(), version=1, updated_by=source)
            self.session.add(row)
        else:
            if row.document == profile.to_json():
                return self._response(row)
            row.document = profile.to_json()
            row.version = (row.version or 1) + 1
            row.updated_by = source
            row.updated_at = datetime.utcnow()
        self.session.flush()
        self.session.add(
            ClientProfileVersion(workspace_id=self.workspace_id, version=row.version, document=row.document, source=source)
        )
        self.session.commit()
        return self._response(row)

    def patch(self, patch: dict[str, Any], source: str = "agent") -> dict[str, Any]:
        """Merge a partial update into the current profile (validation errors raise ``ValueError``)."""
        try:
            merged = merge_profile(self.current(), patch)
        except ValueError as exc:  # pydantic ValidationError is a ValueError
            raise ValueError(str(exc))
        return self.replace(merged, source)

    def approve_ips(self) -> dict[str, Any]:
        row = self._row()
        if row is None:
            raise ValueError("There is no profile yet")
        profile = ClientProfile.model_validate(row.document)
        if profile.ips.is_empty():
            raise ValueError("The profile has no investment policy to approve")
        row.ips_approved_hash = profile.ips.fingerprint()
        row.ips_approved_at = datetime.utcnow()
        self.session.commit()
        return self._response(row)

    def versions(self) -> list[dict[str, Any]]:
        rows = (
            self.session.query(ClientProfileVersion)
            .filter(ClientProfileVersion.workspace_id == self.workspace_id)
            .order_by(ClientProfileVersion.version.desc())
            .all()
        )
        return [
            {"version": r.version, "source": r.source, "created_at": r.created_at.isoformat() if r.created_at else None, "profile": r.document}
            for r in rows
        ]

    @staticmethod
    def ips_status(row: ProfileRow | None, profile: ClientProfile) -> str:
        if profile.ips.is_empty():
            return "none"
        if row is not None and row.ips_approved_hash == profile.ips.fingerprint():
            return "approved"
        return "pending"

    def _response(self, row: ProfileRow | None) -> dict[str, Any]:
        profile = ClientProfile.model_validate(row.document) if row else ClientProfile()
        status = self.ips_status(row, profile)
        return {
            "workspace_id": self.workspace_id,
            "version": row.version if row else 0,
            "updated_by": row.updated_by if row else "nobody",
            "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
            "profile": profile.to_json(),
            "completeness": profile.completeness(),
            "ips_status": status,
            "ips_approved_at": row.ips_approved_at.isoformat() if row and row.ips_approved_at and status == "approved" else None,
        }

    # ------------------------------------------------------------------ decisions

    def list_decisions(self, status: str | None = None) -> list[dict[str, Any]]:
        query = self.session.query(AdvisorDecision)
        if status:
            if status not in DECISION_STATUSES:
                raise ValueError(f"status must be one of {', '.join(DECISION_STATUSES)}")
            query = query.filter(AdvisorDecision.status == status)
        rows = query.order_by(AdvisorDecision.date.desc(), AdvisorDecision.id.desc()).all()
        return [r.to_dict() for r in rows]

    def log_decision(
        self,
        title: str,
        rationale: str,
        data_refs: list[str],
        ips_refs: list[str] | None = None,
        day: date | None = None,
        status: str = "proposed",
    ) -> dict[str, Any]:
        refs = [r.strip() for r in data_refs if r and r.strip()]
        if not refs:
            raise ValueError("A decision needs at least one data reference: say which figures it rests on")
        if not rationale.strip():
            raise ValueError("A decision needs a rationale")
        if status not in DECISION_STATUSES:
            raise ValueError(f"status must be one of {', '.join(DECISION_STATUSES)}")
        row = self._row()
        decision = AdvisorDecision(
            workspace_id=self.workspace_id,
            date=day or date.today(),
            title=title.strip(),
            rationale=rationale.strip(),
            data_refs=refs,
            ips_refs=[r.strip() for r in (ips_refs or []) if r and r.strip()],
            status=status,
            profile_version=row.version if row else None,
        )
        self.session.add(decision)
        self.session.commit()
        return decision.to_dict()

    def update_decision(self, decision_id: int, changes: dict[str, Any]) -> dict[str, Any]:
        row = self.session.get(AdvisorDecision, decision_id)
        if row is None or row.workspace_id != self.workspace_id:
            raise LookupError(f"Decision {decision_id} not found")
        if "status" in changes and changes["status"] is not None:
            if changes["status"] not in DECISION_STATUSES:
                raise ValueError(f"status must be one of {', '.join(DECISION_STATUSES)}")
            row.status = changes["status"]
        for field in ("outcome", "title", "rationale"):
            if changes.get(field) is not None:
                setattr(row, field, changes[field].strip())
        row.updated_at = datetime.utcnow()
        self.session.commit()
        return row.to_dict()
