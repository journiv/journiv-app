"""
Progress callback utilities for import/export operations.
"""
from typing import Callable

from sqlalchemy.orm import Session


def create_throttled_progress_callback(
    job,
    db: Session,
    start_progress: int = 0,
    end_progress: int = 90,
    commit_interval: int = 10,
    percentage_threshold: int = 5,
) -> Callable[[int, int], None]:
    """
    Create a throttled progress callback that commits to DB efficiently.

    Progress is guaranteed to be monotonic (never decreases) and works within
    the specified range [start_progress, end_progress].

    Args:
        job: Job object with processed_items, total_items, and set_progress method
        db: Database session
        start_progress: Starting progress percentage (default 0)
        end_progress: Ending progress percentage (default 90)
        commit_interval: Commit every N entries (default 10)
        percentage_threshold: Commit on N% progress changes (default 5)

    Returns:
        Progress callback function that ensures monotonic progress
    """
    last_committed_progress = 0
    last_committed_percentage = start_progress
    progress_range = end_progress - start_progress
    zero_total_committed = False

    def handle_progress(processed: int, total: int):
        nonlocal last_committed_progress, last_committed_percentage, zero_total_committed
        job.processed_items = processed
        job.total_items = total

        if total > 0:
            # Reset zero_total flag when we have a valid total
            zero_total_committed = False

            # Calculate progress within the range [start_progress, end_progress]
            ratio = processed / total
            calculated_progress = start_progress + int(ratio * progress_range)

            # Ensure progress never decreases (monotonic guarantee)
            current_progress = job.progress or start_progress
            new_progress = max(current_progress, calculated_progress)

            # Clamp to end_progress to avoid exceeding range
            new_progress = min(new_progress, end_progress)

            job.set_progress(new_progress)

            should_commit = (
                (processed - last_committed_progress) >= commit_interval or
                (new_progress - last_committed_percentage) >= percentage_threshold or
                processed == total
            )

            if should_commit:
                db.commit()
                last_committed_progress = processed
                last_committed_percentage = new_progress
        else:
            # No total yet, ensure we're at least at start_progress
            # Only commit once for zero-total case to avoid repeated commits
            if not zero_total_committed:
                current_progress = job.progress or start_progress
                if current_progress < start_progress:
                    job.set_progress(start_progress)
                db.commit()
                zero_total_committed = True

    return handle_progress

