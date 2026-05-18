from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Optional

try:
    from apscheduler.schedulers.background import BackgroundScheduler
except ImportError as exc:  # pragma: no cover - user-facing dependency error
    raise RuntimeError(
        "APScheduler is required. Please run: pip install -r requirements.txt"
    ) from exc

from sender import send_message
from storage import TaskStore


logger = logging.getLogger(__name__)


class TaskScheduler:
    def __init__(
        self,
        store: TaskStore,
        send_func: Callable = send_message,
        state_changed_callback: Optional[Callable[[], None]] = None,
    ) -> None:
        self.store = store
        self.send_func = send_func
        self.state_changed_callback = state_changed_callback
        self._attempted_slots: set[str] = set()
        self._scheduler = BackgroundScheduler(
            daemon=True,
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 30,
            },
        )
        self._scheduler.add_job(
            self._tick,
            "interval",
            seconds=5,
            id="task_tick",
            replace_existing=True,
        )

    def set_state_changed_callback(self, callback: Optional[Callable[[], None]]) -> None:
        self.state_changed_callback = callback

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("Scheduler started")

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")

    def _notify_state_changed(self) -> None:
        if self.state_changed_callback:
            try:
                self.state_changed_callback()
            except Exception:
                logger.debug("State changed callback failed", exc_info=True)

    def _cleanup_old_slots(self, today: str) -> None:
        date_marker = f":{today} "
        self._attempted_slots = {
            slot for slot in self._attempted_slots if date_marker in slot
        }

    def _tick(self) -> None:
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        current_time = now.strftime("%H:%M")
        minute_slot = now.strftime("%Y-%m-%d %H:%M")

        self._cleanup_old_slots(today)

        with self.store.lock:
            tasks = list(self.store.tasks)

        for task in tasks:
            if not task.enabled:
                continue
            if task.time != current_time:
                continue
            if task.last_sent_date == today:
                continue

            slot_key = f"{task.id}:{minute_slot}"
            if slot_key in self._attempted_slots:
                continue
            self._attempted_slots.add(slot_key)

            logger.info("Triggering scheduled task %s (%s)", task.name or task.id, task.target)

            try:
                with self.store.lock:
                    settings_snapshot = dict(self.store.settings)
                status = self.send_func(task, settings_snapshot)
            except Exception as exc:
                logger.exception("Scheduled send failed for task %s", task.name or task.id)
                with self.store.lock:
                    live_task = next((item for item in self.store.tasks if item.id == task.id), None)
                    if live_task is not None:
                        live_task.last_error = str(exc)[:200]
                        self.store.save()
                self._notify_state_changed()
                continue

            with self.store.lock:
                live_task = next((item for item in self.store.tasks if item.id == task.id), None)
                if live_task is None:
                    logger.warning("Task disappeared before it could be updated: %s", task.id)
                    continue
                live_task.last_sent_date = today
                live_task.last_error = ""
                if not live_task.repeat_daily:
                    live_task.enabled = False
                self.store.save()

            logger.info(
                "Scheduled task completed: name=%s status=%s repeat_daily=%s",
                task.name or task.id,
                status,
                task.repeat_daily,
            )
            self._notify_state_changed()
