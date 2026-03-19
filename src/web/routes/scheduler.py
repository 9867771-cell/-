"""
定时任务调度 API 路由
"""
import logging
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from ...database.session import get_db
from ...database import crud
from ..scheduler import add_scheduled_job, remove_scheduled_job

logger = logging.getLogger(__name__)
router = APIRouter()


# ============== Request / Response Models ==============

class ScheduledTaskCreate(BaseModel):
    name: str
    hour: int = 3
    minute: int = 0
    email_service_type: str = "tempmail"
    email_service_id: Optional[int] = None
    count: int = 10
    concurrency: int = 5
    mode: str = "pipeline"
    interval_min: int = 5
    interval_max: int = 30
    proxy: Optional[str] = None
    auto_upload_cpa: bool = False
    cpa_service_ids: List[int] = []
    auto_upload_sub2api: bool = False
    sub2api_service_ids: List[int] = []
    sub2api_group_id: Optional[str] = None
    auto_upload_tm: bool = False
    tm_service_ids: List[int] = []
    enabled: bool = True


class ScheduledTaskUpdate(BaseModel):
    name: Optional[str] = None
    hour: Optional[int] = None
    minute: Optional[int] = None
    email_service_type: Optional[str] = None
    email_service_id: Optional[int] = None
    count: Optional[int] = None
    concurrency: Optional[int] = None
    mode: Optional[str] = None
    interval_min: Optional[int] = None
    interval_max: Optional[int] = None
    proxy: Optional[str] = None
    auto_upload_cpa: Optional[bool] = None
    cpa_service_ids: Optional[List[int]] = None
    auto_upload_sub2api: Optional[bool] = None
    sub2api_service_ids: Optional[List[int]] = None
    sub2api_group_id: Optional[str] = None
    auto_upload_tm: Optional[bool] = None
    tm_service_ids: Optional[List[int]] = None
    enabled: Optional[bool] = None


# ============== Endpoints ==============

@router.get("/tasks")
async def list_scheduled_tasks():
    """获取所有定时任务"""
    with get_db() as db:
        tasks = crud.get_scheduled_tasks(db)
        return [t.to_dict() for t in tasks]


@router.post("/tasks")
async def create_scheduled_task(request: ScheduledTaskCreate):
    """创建定时任务"""
    if not 0 <= request.hour <= 23 or not 0 <= request.minute <= 59:
        raise HTTPException(status_code=400, detail="时间格式无效")
    if request.count < 1 or request.count > 50000:
        raise HTTPException(status_code=400, detail="注册数量必须在 1-50000 之间")
    if request.mode not in ("parallel", "pipeline"):
        raise HTTPException(status_code=400, detail="模式必须为 parallel 或 pipeline")

    with get_db() as db:
        task = crud.create_scheduled_task(db, **request.model_dump())

    if task.enabled:
        add_scheduled_job(task.id, task.hour, task.minute)

    return task.to_dict()


@router.patch("/tasks/{task_id}")
async def update_scheduled_task(task_id: int, request: ScheduledTaskUpdate):
    """更新定时任务"""
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="没有需要更新的字段")

    if "hour" in updates and not 0 <= updates["hour"] <= 23:
        raise HTTPException(status_code=400, detail="小时必须在 0-23 之间")
    if "minute" in updates and not 0 <= updates["minute"] <= 59:
        raise HTTPException(status_code=400, detail="分钟必须在 0-59 之间")

    with get_db() as db:
        task = crud.update_scheduled_task(db, task_id, **updates)
        if not task:
            raise HTTPException(status_code=404, detail="定时任务不存在")
        result = task.to_dict()

    # 同步调度器
    if result["enabled"]:
        add_scheduled_job(task_id, result["hour"], result["minute"])
    else:
        remove_scheduled_job(task_id)

    return result


@router.delete("/tasks/{task_id}")
async def delete_scheduled_task(task_id: int):
    """删除定时任务"""
    remove_scheduled_job(task_id)
    with get_db() as db:
        ok = crud.delete_scheduled_task(db, task_id)
        if not ok:
            raise HTTPException(status_code=404, detail="定时任务不存在")
    return {"success": True}


@router.post("/tasks/{task_id}/toggle")
async def toggle_scheduled_task(task_id: int):
    """启用/禁用定时任务"""
    with get_db() as db:
        task = crud.get_scheduled_task_by_id(db, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="定时任务不存在")
        new_enabled = not task.enabled
        task = crud.update_scheduled_task(db, task_id, enabled=new_enabled)
        result = task.to_dict()

    if new_enabled:
        add_scheduled_job(task_id, result["hour"], result["minute"])
    else:
        remove_scheduled_job(task_id)

    return result


@router.get("/history")
async def list_all_history(limit: int = 100):
    """获取所有执行历史"""
    with get_db() as db:
        rows = crud.get_all_scheduled_task_history(db, limit=limit)
        return [_history_to_dict(r) for r in rows]


@router.get("/tasks/{task_id}/history")
async def list_task_history(task_id: int, limit: int = 50):
    """获取指定任务的执行历史"""
    with get_db() as db:
        task = crud.get_scheduled_task_by_id(db, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="定时任务不存在")
        rows = crud.get_scheduled_task_history(db, task_id, limit=limit)
        return [_history_to_dict(r) for r in rows]


def _history_to_dict(h) -> dict:
    return {
        "id": h.id,
        "scheduled_task_id": h.scheduled_task_id,
        "task_name": h.scheduled_task.name if h.scheduled_task else None,
        "batch_id": h.batch_id,
        "status": h.status,
        "total": h.total,
        "success_count": h.success_count,
        "failed_count": h.failed_count,
        "started_at": h.started_at.isoformat() if h.started_at else None,
        "completed_at": h.completed_at.isoformat() if h.completed_at else None,
    }

