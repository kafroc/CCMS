from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.response import ok, NotFoundError
from app.models.user import User
from app.models.ai_task import AITask

router = APIRouter(prefix="/api/tasks", tags=["Task Management"])


@router.get("/{task_id}")
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Query asynchronous task status for frontend polling."""
    result = await db.exec(
        select(AITask).where(
            AITask.id == task_id,
            AITask.user_id == current_user.id,
        )
    )
    task = result.first()
    if not task:
        raise NotFoundError("Task not found")

    return ok(data={
        "id": task.id,
        "task_type": task.task_type,
        "status": task.status,
        "progress_message": task.progress_message,
        "result_summary": task.result_summary,
        "error_message": task.error_message,
        "download_url": task.download_url,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
    })
