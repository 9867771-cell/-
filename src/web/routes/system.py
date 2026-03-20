"""
系统状态 API — 实时进程监控
"""
import os
import logging
import threading
from datetime import datetime

from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger(__name__)

# 应用启动时间
_start_time = datetime.now()


@router.get("/status")
async def get_system_status():
    """获取系统实时状态"""
    from ..task_manager import (
        _task_status, _batch_status, _ws_connections, _executor,
    )
    from ..scheduler import get_scheduler

    # 1) 活跃注册任务
    running_tasks = []
    for uuid, info in list(_task_status.items()):
        if info.get("status") == "running":
            running_tasks.append({
                "task_uuid": uuid[:8],
                "status": "running",
                "email": info.get("email", ""),
                "step": info.get("step", ""),
            })

    # 2) 活跃批量任务
    running_batches = []
    for bid, info in list(_batch_status.items()):
        if not info.get("finished", False):
            running_batches.append({
                "batch_id": bid[:8],
                "total": info.get("total", 0),
                "completed": info.get("completed", 0),
                "success": info.get("success", 0),
                "failed": info.get("failed", 0),
            })

    # 3) 线程池
    pool_active = _executor._work_queue.qsize() if hasattr(_executor, '_work_queue') else 0
    pool_threads = len(_executor._threads) if hasattr(_executor, '_threads') else 0
    pool_max = _executor._max_workers if hasattr(_executor, '_max_workers') else 0

    # 4) WebSocket 连接数
    ws_count = sum(len(v) for v in _ws_connections.values())

    # 5) 定时任务调度器
    sched = get_scheduler()
    sched_running = sched.running if sched else False
    jobs = sched.get_jobs() if sched and sched.running else []
    next_jobs = []
    for job in jobs:
        nrt = job.next_run_time
        next_jobs.append({
            "id": job.id,
            "next_run": nrt.strftime("%H:%M:%S") if nrt else "未知",
            "next_run_full": nrt.isoformat() if nrt else None,
        })
    next_jobs.sort(key=lambda x: x.get("next_run_full") or "9999")

    # 6) 系统信息
    uptime_seconds = int((datetime.now() - _start_time).total_seconds())
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    return {
        "uptime": f"{hours}h {minutes}m {seconds}s",
        "uptime_seconds": uptime_seconds,
        "thread_pool": {
            "active_threads": pool_threads,
            "max_workers": pool_max,
            "queued": pool_active,
        },
        "websocket_connections": ws_count,
        "scheduler": {
            "running": sched_running,
            "job_count": len(jobs),
            "next_jobs": next_jobs[:5],
        },
        "running_tasks": running_tasks,
        "running_task_count": len(running_tasks),
        "running_batches": running_batches,
        "running_batch_count": len(running_batches),
        "idle": len(running_tasks) == 0 and len(running_batches) == 0,
    }

