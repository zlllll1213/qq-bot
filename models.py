from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict
from uuid import uuid4


def _default_id() -> str:
    return uuid4().hex


def _s(data: Dict[str, Any], key: str, default: str = "") -> str:
    return str(data.get(key) or default)


def _b(data: Dict[str, Any], key: str, default: bool = False) -> bool:
    return bool(data.get(key, default))


@dataclass
class Task:
    id: str = field(default_factory=_default_id)
    name: str = ""
    target: str = ""
    time: str = "09:00"
    message: str = ""
    repeat_daily: bool = False
    enabled: bool = True
    send_enter: bool = True
    last_sent_date: str = ""
    last_error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "target": self.target,
            "time": self.time,
            "message": self.message,
            "repeat_daily": self.repeat_daily,
            "enabled": self.enabled,
            "send_enter": self.send_enter,
            "last_sent_date": self.last_sent_date,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        return cls(
            id=_s(data, "id") or _default_id(),
            name=_s(data, "name"),
            target=_s(data, "target"),
            time=_s(data, "time", "09:00"),
            message=_s(data, "message"),
            repeat_daily=_b(data, "repeat_daily"),
            enabled=_b(data, "enabled", True),
            send_enter=_b(data, "send_enter", True),
            last_sent_date=_s(data, "last_sent_date"),
            last_error=_s(data, "last_error"),
        )

    def clone(self) -> "Task":
        return Task.from_dict(self.to_dict())
