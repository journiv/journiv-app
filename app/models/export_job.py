"""
Export job model for tracking async export operations.
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
from app.models.enums import ExportType, JobStatus


class ExportJob(BaseModel, table=True):
    """
    Track export job progress and results.

    Export jobs are created when a user requests a data export
    and processed asynchronously by Celery workers.
    """
    __tablename__ = "export_jobs"

    # Foreign key to user who initiated the export
    user_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
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

    # Export configuration
    export_type: ExportType = Field(
        sa_column=Column(
            SAEnum(ExportType, name="export_type_enum", values_callable=lambda x: [e.value for e in x]),
            nullable=False
        )
    )
    journal_ids: Optional[List[str]] = Field(
        default=None,
        sa_column=SQLModelColumn(JSON),
        description="Specific journal IDs to export (for selective export)"
    )
    include_media: bool = Field(default=True, description="Whether to include media files")

    # Progress tracking
    total_items: int = Field(default=0, description="Total number of items to export")
    processed_items: int = Field(default=0, description="Number of items processed so far")

    # Output file information
    file_path: Optional[str] = Field(default=None, description="Path to generated export ZIP file")
    file_size: Optional[int] = Field(default=None, description="Size of export file in bytes")

    # Results and errors
    result_data: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=SQLModelColumn(JSON),
        description="Export statistics (journal count, entry count, media count)"
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

    # Completion timestamp
    completed_at: Optional[datetime] = Field(default=None, description="When the job completed or failed")

    def __repr__(self) -> str:
        return f"<ExportJob(id={self.id}, user_id={self.user_id}, status={self.status}, progress={self.progress}%)>"

    def mark_running(self):
        """Mark job as running."""
        self.status = JobStatus.RUNNING
        self.progress = 0

    def update_progress(self, processed: int, total: int):
        """Update progress based on processed/total items."""
        self.processed_items = processed
        self.total_items = total
        if total > 0:
            self.progress = min(100, int((processed / total) * 100))

    def set_progress(self, percent: int):
        """Set progress without touching processed/total counters."""
        self.progress = max(0, min(100, percent))

    def mark_completed(self, file_path: str, file_size: int, result_data: Dict[str, Any]):
        """Mark job as completed with results."""
        self.status = JobStatus.COMPLETED
        self.progress = 100
        self.file_path = file_path
        self.file_size = file_size
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
