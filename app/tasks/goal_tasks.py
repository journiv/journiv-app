"""
Celery tasks for goal period maintenance.
"""
from sqlmodel import Session, select

from app.core.celery_app import celery_app
from app.core.database import engine
from app.core.logging_config import log_error, log_info
from app.models.user import User
from app.services.goal_service import GoalService


@celery_app.task(name="app.tasks.goal_tasks.close_goal_periods", bind=True)
def close_goal_periods(self) -> dict:
    """Close avoidance goal periods that have ended."""
    processed = 0
    try:
        with Session(engine) as session:
            user_ids = list(session.exec(select(User.id)).all())
        for user_id in user_ids:
            try:
                with Session(engine) as session:
                    service = GoalService(session)
                    processed += service.close_avoidance_periods_for_user(user_id)
            except Exception as exc:  # keep one user from stopping the task
                log_error(exc, task_id=self.request.id, user_id=str(user_id))
        log_info(
            "Goal period close task completed",
            task_id=self.request.id,
            processed=processed,
        )
        return {"status": "success", "processed": processed}
    except Exception as exc:
        log_error(exc, task_id=self.request.id)
        self.update_state(
            state="FAILURE",
            meta={"processed": processed, "error": str(exc)},
        )
        raise
