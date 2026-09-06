"""Cooperative cancellation for import/export worker loops."""
from __future__ import annotations

from typing import Any, Type

from sqlmodel import Session

from app.models.enums import JobStatus


class JobCancelledError(Exception):
    """Raised inside a worker loop when the job row has been marked cancelled."""


def raise_if_cancelled(db: Session, model: Type[Any], job_id: Any) -> None:
    """Re-read a job after a commit and abort when it is cancelled or gone.

    A missing row means the job record was deleted while the worker was still
    running (the delete endpoint allows removing a PENDING job). Treat that the
    same as a cancellation so the worker stops instead of finishing an archive
    that nothing will ever reference or clean up.
    """
    db.expire_all()
    fresh = db.get(model, job_id)
    if fresh is None or fresh.status == JobStatus.CANCELLED:
        raise JobCancelledError()
