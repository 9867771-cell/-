import asyncio
import base64
import json
from types import SimpleNamespace

from src.core import register as register_module
from src.web import scheduler as scheduler_module
from src.web.routes import registration as registration_module


def _encode_payload(payload):
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def test_extract_workspace_id_from_workspaces_payload():
    cookie = f"{_encode_payload({'workspaces': [{'id': 'ws_123'}]})}.sig"

    workspace_id, source, path = register_module._extract_workspace_id_from_auth_cookie(cookie)

    assert workspace_id == "ws_123"
    assert source == "segment[0]"
    assert path == "auth.workspaces[0].id"


def test_extract_workspace_id_from_orgs_payload_in_later_segment():
    payload = {"orgs": {"data": [{"id": "org_456", "settings": {"workspace_plan_type": "team"}}]}}
    cookie = f"invalid.{_encode_payload(payload)}.sig"

    workspace_id, source, path = register_module._extract_workspace_id_from_auth_cookie(cookie)

    assert workspace_id == "org_456"
    assert source == "segment[1]"
    assert path == "auth.orgs.data[0].id"


def test_run_batch_parallel_returns_summary_and_schedules_cleanup(monkeypatch):
    registration_module.batch_tasks.clear()
    cleanup_calls = []
    statuses = {
        "task-1": "completed",
        "task-2": "failed",
    }

    class DummyTaskManager:
        def init_batch(self, batch_id, total):
            return None

        def add_batch_log(self, batch_id, log_message):
            return None

        def update_batch_status(self, batch_id, **kwargs):
            return None

        def is_batch_cancelled(self, batch_id):
            return False

        def cleanup_finished_tasks(self, task_uuids):
            return None

        def cleanup_finished_batch(self, batch_id):
            return None

    class DummyDBContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    async def fake_run_registration_task(*args, **kwargs):
        return None

    def fake_get_registration_task(db, task_uuid):
        return SimpleNamespace(status=statuses[task_uuid], error_message="boom")

    def fake_queue_batch_cleanup(batch_id, task_uuids, delay_seconds=registration_module.BATCH_CLEANUP_DELAY_SECONDS):
        cleanup_calls.append((batch_id, list(task_uuids), delay_seconds))

    monkeypatch.setattr(registration_module, "task_manager", DummyTaskManager())
    monkeypatch.setattr(registration_module, "get_db", lambda: DummyDBContext())
    monkeypatch.setattr(registration_module, "run_registration_task", fake_run_registration_task)
    monkeypatch.setattr(registration_module, "_queue_batch_cleanup", fake_queue_batch_cleanup)
    monkeypatch.setattr(registration_module.crud, "get_registration_task", fake_get_registration_task)

    summary = asyncio.run(
        registration_module.run_batch_parallel(
            batch_id="batch-1",
            task_uuids=["task-1", "task-2"],
            email_service_type="tempmail",
            proxy=None,
            email_service_config=None,
            email_service_id=None,
            concurrency=2,
        )
    )

    assert summary["status"] == "completed"
    assert summary["success"] == 1
    assert summary["failed"] == 1
    assert summary["finished"] is True
    assert cleanup_calls == [
        ("batch-1", ["task-1", "task-2"], registration_module.BATCH_CLEANUP_DELAY_SECONDS)
    ]

    registration_module.batch_tasks.clear()


def test_execute_scheduled_task_uses_batch_summary(monkeypatch):
    updated_history = {}
    scheduled_task = SimpleNamespace(
        id=7,
        enabled=True,
        count=2,
        email_service_type="tempmail",
        proxy=None,
        email_service_id=None,
        interval_min=5,
        interval_max=10,
        concurrency=1,
        mode="pipeline",
        auto_upload_cpa=False,
        cpa_service_ids=[],
        auto_upload_sub2api=False,
        sub2api_service_ids=[],
        sub2api_group_id=None,
        auto_upload_tm=False,
        tm_service_ids=[],
    )

    class DummyDBContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    async def fake_run_batch_registration(**kwargs):
        return {
            "status": "completed",
            "success": 1,
            "failed": 1,
            "finished": True,
        }

    def fake_create_history(db, **kwargs):
        updated_history["created"] = kwargs
        return SimpleNamespace(id=99)

    def fake_update_history(db, history_id, **kwargs):
        updated_history["updated"] = {
            "history_id": history_id,
            **kwargs,
        }
        return SimpleNamespace(id=history_id)

    monkeypatch.setattr(scheduler_module, "get_db", lambda: DummyDBContext())
    monkeypatch.setattr(scheduler_module.crud, "get_scheduled_task_by_id", lambda db, task_id: scheduled_task)
    monkeypatch.setattr(scheduler_module.crud, "update_scheduled_task", lambda db, task_id, **kwargs: scheduled_task)
    monkeypatch.setattr(scheduler_module.crud, "bulk_create_registration_tasks", lambda db, task_uuids, proxy=None: len(task_uuids))
    monkeypatch.setattr(scheduler_module.crud, "create_scheduled_task_history", fake_create_history)
    monkeypatch.setattr(scheduler_module.crud, "update_scheduled_task_history", fake_update_history)
    monkeypatch.setattr(registration_module, "run_batch_registration", fake_run_batch_registration)

    asyncio.run(scheduler_module.execute_scheduled_task(7))

    assert updated_history["created"]["total"] == 2
    assert updated_history["updated"]["status"] == "completed"
    assert updated_history["updated"]["success_count"] == 1
    assert updated_history["updated"]["failed_count"] == 1
