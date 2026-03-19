"""
定时任务调度器模块

使用 APScheduler 实现定时注册任务的调度
"""
import uuid
import logging
import asyncio
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ..database.session import get_db
from ..database import crud

logger = logging.getLogger(__name__)

# 全局调度器实例
scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    global scheduler
    if scheduler is None:
        scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    return scheduler


def _job_id(task_id: int) -> str:
    return f"scheduled_task_{task_id}"


async def execute_scheduled_task(task_id: int):
    """
    定时任务执行函数 — 由 APScheduler 触发

    1. 从 DB 读取 ScheduledTask 配置
    2. 创建 batch_id + task_uuids
    3. 写入执行历史
    4. 调用 run_batch_registration
    5. 等待完成后更新历史记录
    """
    from .routes.registration import (
        run_batch_registration,
    )

    logger.info(f"[调度器] 开始执行定时任务 #{task_id}")

    with get_db() as db:
        task = crud.get_scheduled_task_by_id(db, task_id)
        if not task or not task.enabled:
            logger.warning(f"[调度器] 任务 #{task_id} 不存在或已禁用，跳过")
            return

        # 更新 last_run_at
        crud.update_scheduled_task(db, task_id, last_run_at=datetime.utcnow())

        # 创建批量任务
        batch_id = str(uuid.uuid4())
        task_uuids = [str(uuid.uuid4()) for _ in range(task.count)]
        crud.bulk_create_registration_tasks(db, task_uuids, proxy=task.proxy)

        # 创建执行历史
        history = crud.create_scheduled_task_history(
            db,
            scheduled_task_id=task_id,
            batch_id=batch_id,
            status="running",
            total=task.count,
            started_at=datetime.utcnow()
        )
        history_id = history.id

        # 缓存配置（避免 session 关闭后访问）
        config = {
            "email_service_type": task.email_service_type,
            "proxy": task.proxy,
            "email_service_id": task.email_service_id,
            "count": task.count,
            "interval_min": task.interval_min or 5,
            "interval_max": task.interval_max or 30,
            "concurrency": task.concurrency or 5,
            "mode": task.mode or "pipeline",
            "auto_upload_cpa": task.auto_upload_cpa or False,
            "cpa_service_ids": task.cpa_service_ids or [],
            "auto_upload_sub2api": task.auto_upload_sub2api or False,
            "sub2api_service_ids": task.sub2api_service_ids or [],
            "sub2api_group_id": task.sub2api_group_id,
            "auto_upload_tm": task.auto_upload_tm or False,
            "tm_service_ids": task.tm_service_ids or [],
        }

    try:
        summary = await run_batch_registration(
            batch_id=batch_id,
            task_uuids=task_uuids,
            email_service_type=config["email_service_type"],
            proxy=config["proxy"],
            email_service_config=None,
            email_service_id=config["email_service_id"],
            interval_min=config["interval_min"],
            interval_max=config["interval_max"],
            concurrency=config["concurrency"],
            mode=config["mode"],
            auto_upload_cpa=config["auto_upload_cpa"],
            cpa_service_ids=config["cpa_service_ids"],
            auto_upload_sub2api=config["auto_upload_sub2api"],
            sub2api_service_ids=config["sub2api_service_ids"],
            sub2api_group_id=config["sub2api_group_id"],
            auto_upload_tm=config["auto_upload_tm"],
            tm_service_ids=config["tm_service_ids"],
        )
        success_count = int((summary or {}).get("success", 0))
        failed_count = int((summary or {}).get("failed", 0))
        status = str((summary or {}).get("status") or "已完成")
    except Exception as e:
        logger.error(f"[调度器] 任务 #{task_id} 执行异常: {e}")
        success_count = 0
        failed_count = config.get("count", 0)
        status = "执行失败"

    # 更新执行历史
    with get_db() as db:
        crud.update_scheduled_task_history(
            db, history_id,
            status=status,
            success_count=success_count,
            failed_count=failed_count,
            completed_at=datetime.utcnow()
        )

    logger.info(f"[调度器] 任务 #{task_id} 执行完毕: {status}, 成功={success_count}, 失败={failed_count}")


def add_scheduled_job(task_id: int, hour: int, minute: int):
    """添加或更新一个定时 job"""
    s = get_scheduler()
    job_id = _job_id(task_id)
    # 先移除旧的（如果存在）
    if s.get_job(job_id):
        s.remove_job(job_id)
    s.add_job(
        execute_scheduled_task,
        trigger=CronTrigger(hour=hour, minute=minute),
        id=job_id,
        args=[task_id],
        replace_existing=True,
        misfire_grace_time=300,
    )
    logger.info(f"[调度器] 已添加 job: {job_id} ({hour:02d}:{minute:02d})")


def remove_scheduled_job(task_id: int):
    """移除一个定时 job"""
    s = get_scheduler()
    job_id = _job_id(task_id)
    if s.get_job(job_id):
        s.remove_job(job_id)
        logger.info(f"[调度器] 已移除 job: {job_id}")


def sync_all_jobs():
    """从数据库加载所有已启用的定时任务，同步到调度器"""
    s = get_scheduler()
    # 先清除所有 scheduled_task_ 开头的 job
    for job in s.get_jobs():
        if job.id.startswith("scheduled_task_"):
            s.remove_job(job.id)

    with get_db() as db:
        tasks = crud.get_scheduled_tasks(db, enabled_only=True)
        for task in tasks:
            add_scheduled_job(task.id, task.hour, task.minute)
        logger.info(f"[调度器] 已同步 {len(tasks)} 个定时任务")


def start_scheduler():
    """启动调度器并加载所有任务"""
    s = get_scheduler()
    if not s.running:
        s.start()
        logger.info("[调度器] APScheduler 已启动")
    sync_all_jobs()


def stop_scheduler():
    """关闭调度器"""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[调度器] APScheduler 已关闭")
    scheduler = None
