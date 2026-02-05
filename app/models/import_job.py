"""
Import job models for tracking async import operations.
"""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, ForeignKey
from sqlalchemy import Enum as SAEnum
from sqlmodel import JSON, Field
from sqlmodel import Column as SQLModelColumn

from app.core.time_utils import utc_now
from app.models.base import BaseModel
from app.models.enums import ImportSourceType, JobStatus


class ImportJob(BaseModel, table=True):
    """
    Track import job progress and results.

    Import jobs are created for various sources (file uploads, external integrations)
    and processed asynchronously.
    """
    __tablename__ = "import_jobs"

    # Foreign key to user who initiated the import
    user_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        )
    )

    # Optional foreign key to entry (used by Immich imports)
    entry_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(
            ForeignKey("entry.id", ondelete="CASCADE"),
            nullable=True,
            index=True
        )
    )

    # Job status and progress
    status: JobStatus = Field(
        default=JobStatus.PENDING,
        sa_column=Column(
            SAEnum(JobStatus, name="job_status_enum", values_callable=lambda x: [e.value for e in x]),
            nullable=False,
            index=True
        )
    )
    progress: int = Field(default=0, ge=0, le=100, description="Progress percentage 0-100")

    # Source information
    source_type: ImportSourceType = Field(
        sa_column=Column(
            SAEnum(ImportSourceType, name="import_source_type_enum", values_callable=lambda x: [e.value for e in x]),
            nullable=False
        )
    )
    file_path: Optional[str] = Field(default=None, description="Path to uploaded file (if applicable)")

    # Progress tracking
    total_items: int = Field(default=0, description="Total number of items to import")
    processed_items: int = Field(default=0, description="Number of items processed so far")
    failed_items: int = Field(default=0, description="Number of items that failed to import")

    # Results and errors
    result_data: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=SQLModelColumn(JSON),
        description="Final import statistics (journals, entries, media counts) or extra metadata"
    )
    errors: Optional[List[str]] = Field(
        default=None,
        sa_column=SQLModelColumn(JSON),
        description="List of error messages"
    )
    warnings: Optional[List[str]] = Field(
        default=None,
        sa_column=SQLModelColumn(JSON),
        description="List of warning messages"
    )

    # Timing
    started_at: Optional[datetime] = Field(default=None, description="When the job started processing")
    completed_at: Optional[datetime] = Field(default=None, description="When the job completed or failed")

    def __repr__(self) -> str:
        return f"<ImportJob(id={self.id}, user_id={self.user_id}, status={self.status}, progress={self.progress}%)>"

    def mark_running(self):
        """Mark job as running."""
        self.status = JobStatus.RUNNING
        self.progress = 0
        self.started_at = utc_now()

    def update_progress(self, processed: int, total: int, failed: int = 0):
        """Update progress based on processed/total items."""
        if self.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.PARTIAL}:
            return
        self.processed_items = processed
        self.total_items = total
        self.failed_items = failed
        if total > 0:
            self.progress = min(100, int(((processed + failed) / total) * 100))

        # Update status based on progress if it's an async job tracking individual items
        if processed + failed >= total and total > 0:
            if failed == 0:
                self.status = JobStatus.COMPLETED
            elif processed == 0:
                self.status = JobStatus.FAILED
            else:
                self.status = JobStatus.PARTIAL
            self.completed_at = utc_now()
        elif processed + failed > 0:
            self.status = JobStatus.RUNNING

    def set_progress(self, percent: int):
        """Set progress percentage directly."""
        self.progress = max(0, min(100, percent))

    def mark_completed(self, result_data: Optional[Dict[str, Any]] = None):
        """Mark job as completed with results."""
        self.status = JobStatus.COMPLETED
        self.progress = 100
        if result_data:
            self.result_data = result_data
        self.completed_at = utc_now()

    def mark_failed(self, error_message: str):
        """Mark job as failed with error."""
        self.status = JobStatus.FAILED
        if self.errors is None:
            self.errors = []
        self.errors.append(error_message)
        self.completed_at = utc_now()

    def mark_cancelled(self):
        """Mark job as cancelled."""
        self.status = JobStatus.CANCELLED
        self.completed_at = utc_now()

    def add_warning(self, warning: str):
        """Add a warning message."""
        if self.warnings is None:
            self.warnings = []
        self.warnings.append(warning)
