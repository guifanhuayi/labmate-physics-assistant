"""Purge expired assignment recovery data; keep active and recoverable work untouched."""

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import (
    Assignment, AuditLog, DraftMutation, ExperimentGroup, GroupMember,
    SharedDataRevision, SharedDataset, SubmissionDraft,
)


def purge_expired_assignments(db: Session, now: datetime | None = None) -> int:
    cutoff = now or datetime.now(UTC)
    expired = db.scalars(select(Assignment).where(
        Assignment.deleted_at.is_not(None), Assignment.purge_after.is_not(None), Assignment.purge_after <= cutoff,
    )).all()
    for assignment in expired:
        draft_ids = db.scalars(select(SubmissionDraft.id).where(SubmissionDraft.assignment_id == assignment.id)).all()
        dataset_ids = db.scalars(select(SharedDataset.id).where(SharedDataset.assignment_id == assignment.id)).all()
        if draft_ids:
            db.execute(delete(DraftMutation).where(DraftMutation.draft_id.in_(draft_ids)))
        if dataset_ids:
            db.execute(delete(SharedDataRevision).where(SharedDataRevision.dataset_id.in_(dataset_ids)))
        db.execute(delete(SubmissionDraft).where(SubmissionDraft.assignment_id == assignment.id))
        db.execute(delete(SharedDataset).where(SharedDataset.assignment_id == assignment.id))
        db.execute(delete(GroupMember).where(GroupMember.assignment_id == assignment.id))
        db.execute(delete(ExperimentGroup).where(ExperimentGroup.assignment_id == assignment.id))
        db.delete(assignment)
        db.add(AuditLog(actor_id=None, action="assignment.purged", resource_type="assignment",
                        resource_id=str(assignment.id), metadata_json={}, created_at=cutoff))
    db.commit()
    return len(expired)
