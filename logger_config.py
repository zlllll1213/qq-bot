from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional


BASE_DIR = Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / "app.log"


class GuiCallbackHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.callback: Optional[Callable[[str], None]] = None

    def emit(self, record: logging.LogRecord) -> None:
        if not self.callback:
            return
        try:
            message = self.format(record)
            self.callback(message)
        except Exception:
            self.handleError(record)


_configured = False
_gui_handler = GuiCallbackHandler()


def configure_logging(gui_callback: Optional[Callable[[str], None]] = None) -> logging.Logger:
    global _configured

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    if not _configured:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

        _gui_handler.setFormatter(formatter)
        root.addHandler(_gui_handler)
        _configured = True

    if gui_callback is not None:
        _gui_handler.callback = gui_callback

    return root


def set_gui_callback(gui_callback: Optional[Callable[[str], None]]) -> None:
    _gui_handler.callback = gui_callback

