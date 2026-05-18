from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, Iterable

from models import Task


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_STORAGE_FILE = BASE_DIR / "tasks.json"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "qq_app_name": "QQ",
    "search_hotkey": "command+f",
    "open_wait": 5.0,
    "search_wait": 1.0,
    "chat_wait": 1.0,
    "pre_send_delay": 0.5,
    "search_result_index": 1,
    "close_search_overlay": True,
    "dry_run": False,
    "restore_front_app": True,
}


def _normalize_loaded_payload(raw: Any) -> tuple[list[dict], dict, int]:
    if isinstance(raw, list):
        return raw, {}, 1
    if isinstance(raw, dict):
        try:
            version = int(raw.get("version", 1))
        except (TypeError, ValueError):
            version = 1
        tasks = raw.get("tasks")
        settings = raw.get("settings") or {}
        if tasks is None and "items" in raw:
            tasks = raw.get("items")
        if isinstance(tasks, list):
            return tasks, settings if isinstance(settings, dict) else {}, version
    return [], {}, 1


def load_tasks(path: str | Path = DEFAULT_STORAGE_FILE) -> tuple[list[Task], dict]:
    file_path = Path(path)
    if not file_path.exists():
        return [], dict(DEFAULT_SETTINGS)

    try:
        with file_path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except Exception:
        from logging import getLogger

        getLogger(__name__).exception("Failed to load task storage from %s", file_path)
        return [], dict(DEFAULT_SETTINGS)

    raw_tasks, raw_settings, _version = _normalize_loaded_payload(raw)
    tasks = []
    for item in raw_tasks:
        if isinstance(item, dict):
            tasks.append(Task.from_dict(item))

    settings = dict(DEFAULT_SETTINGS)
    if isinstance(raw_settings, dict):
        settings.update(raw_settings)

    return tasks, settings


def save_tasks(
    tasks: Iterable[Task],
    settings: dict | None = None,
    path: str | Path = DEFAULT_STORAGE_FILE,
) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "version": 1,
        "settings": dict(DEFAULT_SETTINGS),
        "tasks": [task.to_dict() for task in tasks],
    }
    if settings is not None:
        payload["settings"].update(settings)

    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            dir=file_path.parent,
            suffix=".tmp",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            json.dump(payload, tmp, ensure_ascii=False, indent=2)
            tmp.write("\n")
            tmp_path = tmp.name
        os.replace(tmp_path, file_path)
    except Exception:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise


class TaskStore:
    def __init__(self, path: str | Path = DEFAULT_STORAGE_FILE):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.tasks, self.settings = load_tasks(self.path)

    def reload(self) -> None:
        with self.lock:
            self.tasks, self.settings = load_tasks(self.path)

    def save(self) -> None:
        with self.lock:
            save_tasks(self.tasks, self.settings, self.path)

    def snapshot(self) -> tuple[list[Task], dict]:
        with self.lock:
            return [task.clone() for task in self.tasks], dict(self.settings)
