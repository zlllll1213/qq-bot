from __future__ import annotations

import logging
import os
import platform
import subprocess
import time
from typing import Any

import pyautogui
import pyperclip


logger = logging.getLogger(__name__)
pyautogui.FAILSAFE = True
_SYSTEM = platform.system()
_IS_DARWIN = _SYSTEM == "Darwin"
_IS_WINDOWS = _SYSTEM == "Windows"
_PRIMARY_MODIFIER = "command" if _IS_DARWIN else "ctrl"

_KEY_ALIASES: dict[str, str] = {
    "cmd": _PRIMARY_MODIFIER,
    "command": "command" if _IS_DARWIN else "ctrl",
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "option" if _IS_DARWIN else "alt",
    "option": "option" if _IS_DARWIN else "alt",
    "shift": "shift",
    "fn": "fn",
    "return": "enter",
    "enter": "enter",
    "esc": "esc",
    "escape": "esc",
    "tab": "tab",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
}


def _sleep(seconds: float) -> None:
    if seconds and seconds > 0:
        time.sleep(seconds)


def _safe_script_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _run_quiet(command: list[str]) -> None:
    subprocess.run(
        command,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _osascript(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["osascript", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )


def _app_matches(current: str, app_name: str) -> bool:
    current_norm = current.strip().lower()
    app_norm = app_name.strip().lower()
    if not app_norm:
        return False
    if current_norm == app_norm:
        return True
    if _IS_WINDOWS:
        return app_norm in current_norm
    return False


def _get_active_window_title() -> str | None:
    try:
        import pygetwindow as gw

        active = gw.getActiveWindow()
        if active is None:
            return None
        return active.title or None
    except Exception:
        logger.debug("Unable to determine the active Windows title", exc_info=True)
        return None


def _activate_windows_app(app_name: str) -> None:
    try:
        import pygetwindow as gw

        matches = [
            window
            for window in gw.getAllWindows()
            if window.title and _app_matches(window.title, app_name)
        ]
        if not matches:
            raise RuntimeError(f"No visible window title matched {app_name!r}")

        window = matches[0]
        if getattr(window, "isMinimized", False):
            window.restore()
            _sleep(0.2)
        window.activate()
    except Exception:
        logger.debug("Unable to activate Windows app: %s", app_name, exc_info=True)
        raise


def _open_windows_app(app_name: str) -> None:
    if os.path.exists(app_name):
        os.startfile(app_name)  # type: ignore[attr-defined]
        return

    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", app_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        logger.debug("Windows shell start failed for %s; trying direct Popen", app_name, exc_info=True)
        subprocess.Popen(
            [app_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def get_frontmost_app_name() -> str | None:
    if _IS_WINDOWS:
        return _get_active_window_title()
    if not _IS_DARWIN:
        return None
    try:
        result = _osascript(
            'tell application "System Events" to get name of first application process whose frontmost is true'
        )
        value = result.stdout.strip()
        return value or None
    except Exception:
        logger.debug("Unable to determine the current frontmost app", exc_info=True)
        return None


def activate_app(app_name: str) -> None:
    if _IS_WINDOWS:
        _activate_windows_app(app_name)
        return
    if not _IS_DARWIN:
        return
    script = f'tell application "{_safe_script_string(app_name)}" to activate'
    _osascript(script)


def wait_for_frontmost_app(app_name: str, timeout: float = 8.0, interval: float = 0.2) -> bool:
    deadline = time.time() + max(timeout, 0)
    while time.time() < deadline:
        current = get_frontmost_app_name()
        if current and _app_matches(current, app_name):
            return True
        time.sleep(interval)
    return False


def open_qq(app_name: str = "QQ") -> None:
    logger.info("Opening QQ app: %s", app_name)
    if _IS_DARWIN:
        _run_quiet(["open", "-a", app_name])
        return
    if _IS_WINDOWS:
        _open_windows_app(app_name)
        return
    _run_quiet([app_name])


def parse_hotkey(hotkey_text: str) -> list[str]:
    parts = [part.strip().lower() for part in hotkey_text.split("+") if part.strip()]
    keys = [_KEY_ALIASES.get(part, part) for part in parts]
    if len(keys) < 2:
        raise ValueError(f"Invalid hotkey: {hotkey_text!r}")
    return keys


def _press_key_name(key_name: str) -> None:
    key = key_name.strip().lower()
    pyautogui.press(_KEY_ALIASES.get(key, key))


def paste_text(text: str) -> None:
    pyperclip.copy(text)
    _sleep(0.15)
    pyautogui.hotkey(_PRIMARY_MODIFIER, "v")


def clear_active_text_field() -> None:
    """
    Clear the currently focused text field.

    Command/Ctrl+A followed by Backspace is a practical way to wipe
    whatever search text may still be in the QQ search box from a previous run.
    """

    pyautogui.hotkey(_PRIMARY_MODIFIER, "a")
    _sleep(0.1)
    pyautogui.press("backspace")
    _sleep(0.1)


def send_message(task, settings: dict[str, Any]) -> str:
    """
    Send a message using the QQ UI automation flow.

    Returns:
        "attempted-send" when Enter was pressed after pasting the message.
        "prepared" when the message is pasted but Enter is intentionally not pressed.
        "dry-run" when no UI actions are executed.
    """

    app_name = str(settings.get("qq_app_name") or "QQ")
    search_hotkey = str(settings.get("search_hotkey") or "command+f")
    open_wait = float(settings.get("open_wait", 5.0))
    search_wait = float(settings.get("search_wait", 1.0))
    chat_wait = float(settings.get("chat_wait", 1.0))
    pre_send_delay = float(settings.get("pre_send_delay", 0.5))
    search_result_index = int(settings.get("search_result_index", 1) or 1)
    close_search_overlay = bool(settings.get("close_search_overlay", True))
    dry_run = bool(settings.get("dry_run", False))
    restore_front_app = bool(settings.get("restore_front_app", True))

    target = (task.target or "").strip()
    message = task.message or ""
    task_label = task.name or task.id

    if not target:
        raise ValueError("目标联系人/群聊名称不能为空")
    if not message.strip():
        raise ValueError("消息内容不能为空")

    logger.info(
        "Task start: name=%s target=%s time=%s repeat_daily=%s enabled=%s",
        task_label,
        target,
        task.time,
        task.repeat_daily,
        task.enabled,
    )

    if dry_run:
        logger.info(
            "Dry-run: would open QQ app=%s, search_hotkey=%s, target=%s, send_enter=%s, message:\n%s",
            app_name,
            search_hotkey,
            target,
            task.send_enter,
            message,
        )
        return "dry-run"

    previous_app = get_frontmost_app_name() if restore_front_app else None
    should_restore = False
    result = "prepared"

    try:
        open_qq(app_name)
        _sleep(0.4)
        try:
            activate_app(app_name)
        except Exception:
            logger.debug("Initial activate failed for %s", app_name, exc_info=True)

        if not wait_for_frontmost_app(app_name, timeout=max(open_wait, 3.0)):
            logger.warning("QQ did not become frontmost within the expected time window")
            _sleep(1.0)

        keys = parse_hotkey(search_hotkey)
        logger.info("Opening search UI with hotkey: %s", search_hotkey)
        pyautogui.hotkey(*keys)
        _sleep(0.2)

        try:
            activate_app(app_name)
        except Exception:
            logger.debug("Re-activate after search hotkey failed for %s", app_name, exc_info=True)

        logger.info("Clearing search field before typing target")
        clear_active_text_field()
        logger.info("Pasting target: %s", target)
        paste_text(target)

        _sleep(0.2)
        if search_result_index > 1:
            logger.info("Selecting search result index: %s", search_result_index)
            for _ in range(search_result_index - 1):
                _press_key_name("down")
                _sleep(0.12)

        if close_search_overlay:
            pyautogui.press("enter")
        else:
            logger.info("Search overlay kept open by configuration")

        _sleep(search_wait)
        _sleep(chat_wait)

        logger.info("Pasting message for task %s", task_label)
        paste_text(message)
        _sleep(pre_send_delay)

        should_restore = bool(previous_app and restore_front_app)

        if task.send_enter:
            pyautogui.press("enter")
            result = "attempted-send"
        else:
            logger.info(
                "Safe mode: message pasted for task %s, Enter not pressed",
                task_label,
            )
            result = "prepared"

    except pyautogui.FailSafeException:
        logger.warning("PyAutoGUI fail-safe triggered while handling task %s", task_label)
        raise
    except Exception:
        logger.exception("Failed to send task %s", task_label)
        raise
    finally:
        if should_restore and previous_app and previous_app != app_name:
            _sleep(0.4)
            try:
                activate_app(previous_app)
            except Exception:
                logger.debug("Failed to restore previous app: %s", previous_app, exc_info=True)

    logger.info(
        "Task completed: name=%s target=%s status=%s (this reports automation progress, not delivery confirmation)",
        task_label,
        target,
        result,
    )
    return result
