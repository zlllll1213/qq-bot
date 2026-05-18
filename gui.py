from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import datetime
from queue import Empty, Queue
from typing import Callable
from uuid import uuid4

import tkinter as tk
from tkinter import messagebox, ttk

from logger_config import configure_logging
from models import Task
from scheduler import TaskScheduler
from sender import send_message
from storage import DEFAULT_SETTINGS, TaskStore


class QQSenderApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("QQ 定时发送助手")
        self.root.geometry("1240x780")
        self.root.minsize(1120, 700)

        self.log_queue: Queue[str] = Queue()
        configure_logging(self.enqueue_log)
        self.logger = logging.getLogger(__name__)

        self.store = TaskStore()
        self.state_changed_event = threading.Event()
        self.scheduler = TaskScheduler(
            self.store,
            send_func=send_message,
            state_changed_callback=self.state_changed_event.set,
        )

        self.current_task_id: str | None = None
        self.log_lines = deque(maxlen=100)
        self.status_clear_job: str | None = None
        self._sort_col: str = "time"
        self._sort_reverse: bool = False

        self._build_ui()
        self._load_settings_into_form()
        self.refresh_task_list()
        self.scheduler.start()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(200, self._poll_logs)
        self.root.after(1000, self._poll_state_changes)

    def enqueue_log(self, message: str) -> None:
        self.log_queue.put(message)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=0, minsize=120)
        self.root.rowconfigure(2, weight=0)

        container = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        container.grid(row=0, column=0, sticky="nsew")

        left = ttk.Frame(container, padding=8)
        right = ttk.Frame(container, padding=8)
        container.add(left, weight=2)
        container.add(right, weight=3)

        self._build_task_list(left)
        self._build_editor(right)
        self._build_log_panel()
        self._build_status_bar()
        self._bind_shortcuts()

    def _build_task_list(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)

        list_frame = ttk.LabelFrame(parent, text="任务列表")
        list_frame.grid(row=0, column=0, sticky="nsew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        columns = ("time", "target", "name", "repeat", "enabled")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "time": "时间",
            "target": "目标",
            "name": "任务名称",
            "repeat": "重复",
            "enabled": "状态",
        }
        for column, text in headings.items():
            self.tree.heading(column, text=text, command=lambda col=column: self._sort_by_col(col))
        self.tree.column("time", width=90, anchor="center", stretch=False)
        self.tree.column("target", width=150, anchor="w")
        self.tree.column("name", width=130, anchor="w")
        self.tree.column("repeat", width=55, anchor="center", stretch=False)
        self.tree.column("enabled", width=150, anchor="w", stretch=False)
        self.tree.tag_configure("disabled", foreground="#999999")
        self.tree.tag_configure("done", foreground="#4a90d9")
        self.tree.tag_configure("error", foreground="#d9534f")
        self.tree.tag_configure("row_odd", background="#f5f5f5")
        self.tree.tag_configure("row_even", background="#ffffff")
        self.tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<Button-2>", self._show_context_menu)
        self.tree.bind("<Button-3>", self._show_context_menu)
        self._build_context_menu()

    def _build_editor(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=0)
        parent.rowconfigure(1, weight=1)
        parent.rowconfigure(2, weight=0)
        self._build_settings_frame(parent)
        self._build_task_frame(parent)
        self._build_button_row(parent)

    def _build_settings_frame(self, parent: ttk.Frame) -> None:
        settings_frame = ttk.LabelFrame(parent, text="自动化设置")
        settings_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        for idx in range(6):
            settings_frame.columnconfigure(idx, weight=1 if idx in (1, 3, 5) else 0)

        self.qq_app_name_var = tk.StringVar()
        self.search_hotkey_var = tk.StringVar()
        self.open_wait_var = tk.StringVar()
        self.search_wait_var = tk.StringVar()
        self.chat_wait_var = tk.StringVar()
        self.pre_send_delay_var = tk.StringVar()
        self.search_result_index_var = tk.StringVar()
        self.close_search_overlay_var = tk.BooleanVar()
        self.dry_run_var = tk.BooleanVar()
        self.restore_front_app_var = tk.BooleanVar()

        self._add_labeled_entry(settings_frame, 0, 0, "QQ App 名称", self.qq_app_name_var)
        self._add_labeled_entry(settings_frame, 0, 2, "搜索快捷键", self.search_hotkey_var)
        self._add_labeled_entry_with_unit(settings_frame, 0, 4, "打开后等待", self.open_wait_var)

        self._add_labeled_entry_with_unit(settings_frame, 1, 0, "搜索后等待", self.search_wait_var)
        self._add_labeled_entry_with_unit(settings_frame, 1, 2, "聊天后等待", self.chat_wait_var)
        self._add_labeled_entry_with_unit(settings_frame, 1, 4, "发送前延迟", self.pre_send_delay_var)

        self._add_labeled_entry(settings_frame, 2, 0, "结果序号", self.search_result_index_var, width=10)

        ttk.Checkbutton(settings_frame, text="关闭搜索浮层", variable=self.close_search_overlay_var).grid(
            row=2, column=2, sticky="w", padx=4, pady=(4, 2)
        )
        ttk.Checkbutton(
            settings_frame,
            text="发送后切回前台应用",
            variable=self.restore_front_app_var,
        ).grid(row=2, column=4, sticky="w", padx=4, pady=(4, 2))
        self.dry_run_check = ttk.Checkbutton(settings_frame, text="Dry-run", variable=self.dry_run_var)
        self.dry_run_check.grid(
            row=3, column=0, sticky="w", padx=4, pady=(4, 2)
        )
        self.dry_run_var.trace_add("write", self._on_dry_run_changed)

    def _build_task_frame(self, parent: ttk.Frame) -> None:
        task_frame = ttk.LabelFrame(parent, text="任务编辑")
        task_frame.grid(row=1, column=0, sticky="nsew")
        task_frame.columnconfigure(1, weight=1)
        task_frame.columnconfigure(3, weight=1)

        self.name_var = tk.StringVar()
        self.target_var = tk.StringVar()
        self.time_var = tk.StringVar()
        self.repeat_daily_var = tk.BooleanVar()
        self.enabled_var = tk.BooleanVar()
        self.send_enter_var = tk.BooleanVar()

        self._name_entry = self._add_labeled_entry(task_frame, 0, 0, "任务名称", self.name_var, columnspan=3)
        self._add_labeled_entry(task_frame, 1, 0, "目标联系人/群聊", self.target_var, columnspan=3)
        self.time_entry = self._add_labeled_entry(
            task_frame,
            2,
            0,
            "发送时间(HH:MM)",
            self.time_var,
            columnspan=1,
            width=14,
        )
        self.time_entry.bind("<FocusOut>", self._validate_time_field)

        flags = ttk.Frame(task_frame)
        flags.grid(row=2, column=2, columnspan=2, sticky="w", padx=4, pady=4)
        ttk.Checkbutton(flags, text="每天重复", variable=self.repeat_daily_var).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(flags, text="启用", variable=self.enabled_var).grid(row=0, column=1, sticky="w", padx=(16, 0))
        ttk.Checkbutton(flags, text="发送 Enter", variable=self.send_enter_var).grid(row=0, column=2, sticky="w", padx=(16, 0))

        message_label = ttk.Label(task_frame, text="消息内容")
        message_label.grid(row=3, column=0, sticky="nw", padx=4, pady=(4, 0))
        message_wrap = ttk.Frame(task_frame)
        message_wrap.grid(row=3, column=1, columnspan=3, sticky="nsew", padx=4, pady=(4, 0))
        task_frame.rowconfigure(3, weight=1)
        message_wrap.rowconfigure(0, weight=1)
        message_wrap.columnconfigure(0, weight=1)
        self.message_text = tk.Text(message_wrap, height=12, wrap="word")
        self.message_text.grid(row=0, column=0, sticky="nsew")
        message_scroll = ttk.Scrollbar(message_wrap, orient="vertical", command=self.message_text.yview)
        self.message_text.configure(yscrollcommand=message_scroll.set)
        message_scroll.grid(row=0, column=1, sticky="ns")
        self.char_count_var = tk.StringVar(value="0 字")
        ttk.Label(message_wrap, textvariable=self.char_count_var, foreground="#999999").grid(
            row=1, column=0, sticky="e", padx=4, pady=(2, 0)
        )
        self.message_text.bind("<KeyRelease>", self._update_char_count)
        self.message_text.bind("<<Paste>>", lambda _event: self.root.after(0, self._update_char_count))

    def _build_button_row(self, parent: ttk.Frame) -> None:
        actions = ttk.Frame(parent)
        actions.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        actions.columnconfigure(0, weight=4)
        actions.columnconfigure(1, weight=1)

        task_actions = ttk.LabelFrame(actions, text="任务操作")
        task_actions.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        for column in range(3):
            task_actions.columnconfigure(column, weight=1)

        config_actions = ttk.LabelFrame(actions, text="配置")
        config_actions.grid(row=0, column=1, sticky="ew")
        config_actions.columnconfigure(0, weight=1)

        self._add_action_button(task_actions, "新增", self.new_task, 0, 0)
        self._add_action_button(task_actions, "保存", self.save_task, 0, 1)
        self._add_action_button(task_actions, "删除", self.delete_task, 0, 2)
        self._toggle_btn = self._add_action_button(task_actions, "禁用", self.toggle_enabled, 1, 0)
        self._test_send_btn = self._add_action_button(task_actions, "测试", self.test_send, 1, 1)
        self._clear_error_btn = self._add_action_button(task_actions, "清错", self.clear_task_error, 1, 2)
        self._clear_error_btn.configure(state="disabled")

        self._add_action_button(config_actions, "保存", self.save_config, 0, 0)
        self._add_action_button(config_actions, "重载", self.load_config, 1, 0)

    def _add_action_button(
        self,
        parent: ttk.Frame,
        text: str,
        command: Callable[[], None],
        row: int,
        column: int,
    ) -> ttk.Button:
        button = ttk.Button(parent, text=text, command=command, width=6)
        button.grid(row=row, column=column, sticky="ew", padx=4, pady=4)
        return button

    def _build_log_panel(self) -> None:
        log_frame = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        log_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)

        log_header = ttk.Frame(log_frame)
        log_header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        log_header.columnconfigure(0, weight=1)
        ttk.Label(log_header, text="最近日志").grid(row=0, column=0, sticky="w")
        ttk.Button(log_header, text="清空", width=6, command=self._clear_log).grid(row=0, column=1, sticky="e")

        self.log_text = tk.Text(log_frame, height=10, wrap="none", state="disabled")
        self.log_text.grid(row=1, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        log_scroll.grid(row=1, column=1, sticky="ns")
        log_h_scroll = ttk.Scrollbar(log_frame, orient="horizontal", command=self.log_text.xview)
        self.log_text.configure(xscrollcommand=log_h_scroll.set)
        log_h_scroll.grid(row=2, column=0, sticky="ew")

    def _build_status_bar(self) -> None:
        self.status_var = tk.StringVar()
        status_bar = ttk.Label(self.root, textvariable=self.status_var, anchor="w", padding=(8, 3))
        status_bar.grid(row=2, column=0, sticky="ew")

    def _add_labeled_entry(
        self,
        parent: ttk.Frame,
        row: int,
        column: int,
        label: str,
        variable: tk.StringVar,
        columnspan: int = 1,
        width: int = 20,
    ) -> ttk.Entry:
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", padx=4, pady=4)
        entry = ttk.Entry(parent, textvariable=variable, width=width)
        entry.grid(row=row, column=column + 1, columnspan=columnspan, sticky="ew", padx=4, pady=4)
        return entry

    def _add_labeled_entry_with_unit(
        self,
        parent: ttk.Frame,
        row: int,
        column: int,
        label: str,
        variable: tk.StringVar,
        unit: str = "s",
        width: int = 10,
    ) -> ttk.Entry:
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", padx=4, pady=4)
        entry_wrap = ttk.Frame(parent)
        entry_wrap.grid(row=row, column=column + 1, sticky="ew", padx=4, pady=4)
        entry_wrap.columnconfigure(0, weight=1)
        entry = ttk.Entry(entry_wrap, textvariable=variable, width=width)
        entry.grid(row=0, column=0, sticky="ew")
        ttk.Label(entry_wrap, text=unit, foreground="#666666").grid(row=0, column=1, sticky="e", padx=(4, 0))
        return entry

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Command-s>", lambda _event: self.save_task())
        self.root.bind("<Command-n>", lambda _event: self.new_task())
        self.root.bind("<Command-t>", lambda _event: self.test_send())
        self.root.bind("<Control-s>", lambda _event: self.save_task())
        self.root.bind("<Control-n>", lambda _event: self.new_task())
        self.root.bind("<Control-t>", lambda _event: self.test_send())
        self.root.bind("<Delete>", lambda _event: self.delete_task())

    def _build_context_menu(self) -> None:
        self._context_menu = tk.Menu(self.root, tearoff=0)
        self._context_menu.add_command(label="启用/禁用", command=self.toggle_enabled)
        self._context_menu.add_command(label="测试发送", command=self.test_send)
        self._context_menu.add_command(label="清除错误", command=self.clear_task_error)
        self._context_menu.add_separator()
        self._context_menu.add_command(label="删除", command=self.delete_task)

    def _show_context_menu(self, event) -> None:
        row = self.tree.identify_row(event.y)
        if not row:
            return
        self.tree.selection_set(row)
        self.tree.focus(row)
        with self.store.lock:
            task = next((item for item in self.store.tasks if item.id == row), None)
        if task is not None:
            self._load_task_into_form(task)
        self._context_menu.post(event.x_root, event.y_root)

    def _set_status(self, message: str, duration_ms: int = 2000) -> None:
        if self.status_clear_job is not None:
            self.root.after_cancel(self.status_clear_job)
            self.status_clear_job = None
        self.status_var.set(message)
        if duration_ms > 0:
            self.status_clear_job = self.root.after(duration_ms, self._clear_status)

    def _clear_status(self) -> None:
        self.status_clear_job = None
        if self.dry_run_var.get():
            self.status_var.set("Dry-run 模式：发送操作仅模拟，不会真正执行")
        else:
            self.status_var.set("")

    def _on_dry_run_changed(self, *_args) -> None:
        if self.dry_run_var.get():
            self._set_status("Dry-run 模式：发送操作仅模拟，不会真正执行", duration_ms=0)
        else:
            self._clear_status()

    def _update_char_count(self, _event=None) -> None:
        content = self.message_text.get("1.0", "end-1c")
        self.char_count_var.set(f"{len(content)} 字")

    def _sort_by_col(self, col: str) -> None:
        if self._sort_col == col:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_col = col
            self._sort_reverse = False

        def sort_key(task: Task) -> str:
            if col == "repeat":
                return "1" if task.repeat_daily else "0"
            if col == "enabled":
                if task.last_error:
                    return f"0:{task.last_error}"
                if not task.enabled:
                    return "1:禁用"
                return "2:启用"
            return str(getattr(task, col, ""))

        with self.store.lock:
            self.store.tasks.sort(key=sort_key, reverse=self._sort_reverse)
            self.store.save()
        self.refresh_task_list()
        self._set_status("任务列表已排序")

    def _load_settings_into_form(self) -> None:
        with self.store.lock:
            settings = dict(self.store.settings)

        self.qq_app_name_var.set(str(settings.get("qq_app_name", DEFAULT_SETTINGS["qq_app_name"])))
        self.search_hotkey_var.set(str(settings.get("search_hotkey", DEFAULT_SETTINGS["search_hotkey"])))
        self.open_wait_var.set(str(settings.get("open_wait", DEFAULT_SETTINGS["open_wait"])))
        self.search_wait_var.set(str(settings.get("search_wait", DEFAULT_SETTINGS["search_wait"])))
        self.chat_wait_var.set(str(settings.get("chat_wait", DEFAULT_SETTINGS["chat_wait"])))
        self.pre_send_delay_var.set(str(settings.get("pre_send_delay", DEFAULT_SETTINGS["pre_send_delay"])))
        self.search_result_index_var.set(str(settings.get("search_result_index", DEFAULT_SETTINGS["search_result_index"])))
        self.close_search_overlay_var.set(
            bool(settings.get("close_search_overlay", DEFAULT_SETTINGS["close_search_overlay"]))
        )
        self.dry_run_var.set(bool(settings.get("dry_run", DEFAULT_SETTINGS["dry_run"])))
        self.restore_front_app_var.set(
            bool(settings.get("restore_front_app", DEFAULT_SETTINGS["restore_front_app"]))
        )
        self._on_dry_run_changed()

    def _collect_settings_from_form(self) -> dict:
        def _to_float(value: str, default: float) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        def _to_int(value: str, default: int) -> int:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                return default
            return parsed if parsed > 0 else default

        settings = {
            "qq_app_name": self.qq_app_name_var.get().strip() or DEFAULT_SETTINGS["qq_app_name"],
            "search_hotkey": self.search_hotkey_var.get().strip() or DEFAULT_SETTINGS["search_hotkey"],
            "open_wait": _to_float(self.open_wait_var.get().strip(), DEFAULT_SETTINGS["open_wait"]),
            "search_wait": _to_float(self.search_wait_var.get().strip(), DEFAULT_SETTINGS["search_wait"]),
            "chat_wait": _to_float(self.chat_wait_var.get().strip(), DEFAULT_SETTINGS["chat_wait"]),
            "pre_send_delay": _to_float(
                self.pre_send_delay_var.get().strip(), DEFAULT_SETTINGS["pre_send_delay"]
            ),
            "search_result_index": _to_int(
                self.search_result_index_var.get().strip(), DEFAULT_SETTINGS["search_result_index"]
            ),
            "close_search_overlay": bool(self.close_search_overlay_var.get()),
            "dry_run": bool(self.dry_run_var.get()),
            "restore_front_app": bool(self.restore_front_app_var.get()),
        }
        return settings

    def _task_from_form(self, task_id: str | None = None) -> Task:
        task = Task(
            id=task_id or self.current_task_id or uuid4().hex,
            name=self.name_var.get().strip(),
            target=self.target_var.get().strip(),
            time=self.time_var.get().strip(),
            message=self.message_text.get("1.0", "end-1c"),
            repeat_daily=bool(self.repeat_daily_var.get()),
            enabled=bool(self.enabled_var.get()),
            send_enter=bool(self.send_enter_var.get()),
            last_sent_date="",
        )

        if task_id or self.current_task_id:
            with self.store.lock:
                existing = next(
                    (item for item in self.store.tasks if item.id == (task_id or self.current_task_id)),
                    None,
                )
            if existing is not None:
                task.last_error = existing.last_error
                if task.time == existing.time:
                    task.last_sent_date = existing.last_sent_date
        return task

    def _validate_time_field(self, _event=None) -> bool:
        try:
            datetime.strptime(self.time_var.get().strip(), "%H:%M")
        except ValueError:
            self.time_entry.configure(foreground="red")
            return False
        self.time_entry.configure(foreground="")
        return True

    def _validate_task(self, task: Task) -> None:
        if not task.target:
            raise ValueError("目标不能为空")
        if not task.message.strip():
            raise ValueError("消息不能为空")
        try:
            datetime.strptime(task.time, "%H:%M")
        except ValueError as exc:
            raise ValueError("时间必须是 00:00 到 23:59 的 HH:MM 格式") from exc

    def _validate_task_for_send(self, task: Task) -> None:
        if not task.target:
            raise ValueError("目标不能为空")
        if not task.message.strip():
            raise ValueError("消息不能为空")

    def _apply_settings_to_store(self) -> None:
        with self.store.lock:
            self.store.settings.update(self._collect_settings_from_form())

    def refresh_task_list(self) -> None:
        selected = self.tree.selection()
        selected_id = selected[0] if selected else self.current_task_id
        today = datetime.now().strftime("%Y-%m-%d")

        for item in self.tree.get_children():
            self.tree.delete(item)

        with self.store.lock:
            tasks = list(self.store.tasks)

        for index, task in enumerate(tasks):
            row_tag = "row_odd" if index % 2 else "row_even"
            if task.last_error:
                short_error = task.last_error[:25]
                if len(task.last_error) > 25:
                    short_error += "..."
                status = f"失败: {short_error}"
                tags = ("error", row_tag)
            elif not task.enabled:
                status = "禁用"
                tags = ("disabled", row_tag)
            elif task.last_sent_date == today:
                status = "已发送"
                tags = ("done", row_tag)
            else:
                status = "启用"
                tags = (row_tag,)
            self.tree.insert(
                "",
                "end",
                iid=task.id,
                values=(
                    task.time,
                    task.target,
                    task.name,
                    "每日" if task.repeat_daily else "单次",
                    status,
                ),
                tags=tags,
            )

        if selected_id and self.tree.exists(selected_id):
            self.tree.selection_set(selected_id)
            self.tree.focus(selected_id)

    def _load_task_into_form(self, task: Task) -> None:
        self.current_task_id = task.id
        self.name_var.set(task.name)
        self.target_var.set(task.target)
        self.time_var.set(task.time)
        self.repeat_daily_var.set(task.repeat_daily)
        self.enabled_var.set(task.enabled)
        self.send_enter_var.set(task.send_enter)
        self.message_text.delete("1.0", "end")
        self.message_text.insert("1.0", task.message)
        self._validate_time_field()
        self._update_char_count()
        self._update_action_buttons(task)

    def _update_action_buttons(self, task: Task | None = None) -> None:
        if task is None and self.current_task_id:
            with self.store.lock:
                task = next((item for item in self.store.tasks if item.id == self.current_task_id), None)
        if task is None:
            self._toggle_btn.configure(text="禁用")
            self._clear_error_btn.configure(state="disabled")
            return
        self._toggle_btn.configure(text="禁用" if task.enabled else "启用")
        self._clear_error_btn.configure(state="normal" if task.last_error else "disabled")

    def on_tree_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        task_id = selection[0]
        with self.store.lock:
            task = next((item for item in self.store.tasks if item.id == task_id), None)
        if task is not None:
            self._load_task_into_form(task)

    def new_task(self) -> None:
        self.current_task_id = None
        self.name_var.set("")
        self.target_var.set("")
        self.time_var.set("09:00")
        self.repeat_daily_var.set(False)
        self.enabled_var.set(True)
        self.send_enter_var.set(True)
        self.message_text.delete("1.0", "end")
        self.tree.selection_remove(self.tree.selection())
        self._validate_time_field()
        self._update_char_count()
        self._toggle_btn.configure(text="禁用")
        self._clear_error_btn.configure(state="disabled")
        self._name_entry.focus_set()

    def save_task(self) -> None:
        try:
            self._apply_settings_to_store()
            task = self._task_from_form()
            self._validate_task(task)
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))
            return

        with self.store.lock:
            existing_index = next((i for i, item in enumerate(self.store.tasks) if item.id == task.id), None)
            if existing_index is None:
                self.store.tasks.append(task)
            else:
                self.store.tasks[existing_index] = task
            self.store.save()

        self.current_task_id = task.id
        self.refresh_task_list()
        self.tree.selection_set(task.id)
        self.tree.focus(task.id)
        self._set_status("任务已保存")

    def delete_task(self) -> None:
        task_id = self.current_task_id or (self.tree.selection()[0] if self.tree.selection() else None)
        if not task_id:
            messagebox.showwarning("删除失败", "请先选择一个任务。")
            return
        if not messagebox.askyesno("确认删除", "确定要删除选中的任务吗？"):
            return

        with self.store.lock:
            self.store.tasks = [task for task in self.store.tasks if task.id != task_id]
            self.store.save()

        self.current_task_id = None
        self.new_task()
        self.refresh_task_list()

    def toggle_enabled(self) -> None:
        task_id = self.current_task_id or (self.tree.selection()[0] if self.tree.selection() else None)
        if not task_id:
            messagebox.showwarning("操作失败", "请先选择一个任务。")
            return

        with self.store.lock:
            task = next((item for item in self.store.tasks if item.id == task_id), None)
            if task is None:
                messagebox.showerror("操作失败", "未找到任务。")
                return
            task.enabled = not task.enabled
            self.store.save()

        self.refresh_task_list()
        with self.store.lock:
            task = next((item for item in self.store.tasks if item.id == task_id), None)
        if task is not None:
            self._load_task_into_form(task)
            self._set_status("任务已启用" if task.enabled else "任务已禁用")

    def clear_task_error(self) -> None:
        task_id = self.current_task_id or (self.tree.selection()[0] if self.tree.selection() else None)
        if not task_id:
            self._set_status("请先选择一个任务")
            return

        with self.store.lock:
            task = next((item for item in self.store.tasks if item.id == task_id), None)
            if task is None:
                messagebox.showerror("操作失败", "未找到任务。")
                return
            task.last_error = ""
            self.store.save()

        self.refresh_task_list()
        with self.store.lock:
            task = next((item for item in self.store.tasks if item.id == task_id), None)
        if task is not None:
            self._load_task_into_form(task)
        self._set_status("错误状态已清除")

    def test_send(self) -> None:
        try:
            self._apply_settings_to_store()
            task = self._task_from_form(task_id=self.current_task_id)
            self._validate_task_for_send(task)
        except Exception as exc:
            messagebox.showerror("测试失败", str(exc))
            return

        self._set_busy_state(True)
        self._test_send_btn.configure(text="测试中...")
        self._set_status("正在执行测试发送...", duration_ms=0)

        def worker() -> None:
            with self.store.lock:
                settings_snapshot = dict(self.store.settings)
            try:
                status = send_message(task, settings_snapshot)
            except Exception as exc:
                error_text = str(exc)
                self.root.after(
                    0,
                    lambda text=error_text: messagebox.showerror("测试发送失败", text),
                )
            else:
                if status == "attempted-send":
                    text = "测试动作已执行，请到 QQ 确认是否发出"
                elif status == "prepared":
                    text = "消息已填入，未按 Enter"
                else:
                    text = f"测试完成：{status}"
                self.root.after(0, lambda body=text: self._set_status(body))
            finally:
                self.root.after(0, self._finish_test_send)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_test_send(self) -> None:
        self._test_send_btn.configure(text="测试")
        self._set_busy_state(False)
        self._update_action_buttons()
        if not self.dry_run_var.get():
            self._set_status("测试发送已结束")

    def _set_busy_state(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self._configure_child_buttons(self.root, state)

    def _configure_child_buttons(self, widget: tk.Widget, state: str) -> None:
        for child in widget.winfo_children():
            if isinstance(child, ttk.Button):
                child.configure(state=state)
            self._configure_child_buttons(child, state)

    def save_config(self) -> None:
        try:
            self._apply_settings_to_store()
            with self.store.lock:
                self.store.save()
        except Exception as exc:
            messagebox.showerror("保存配置失败", str(exc))
            return
        self._set_status("配置已保存")

    def load_config(self) -> None:
        if not messagebox.askyesno("加载配置", "这将从 tasks.json 重新加载配置并覆盖当前界面内容，继续吗？"):
            return
        try:
            self.store.reload()
        except Exception as exc:
            messagebox.showerror("加载配置失败", str(exc))
            return

        self._load_settings_into_form()
        self.refresh_task_list()
        if self.store.tasks:
            self._load_task_into_form(self.store.tasks[0])
        else:
            self.new_task()
        self._set_status("配置已重新加载")

    def _append_log_text(self, lines: list[str]) -> None:
        self.log_text.configure(state="normal")
        if lines:
            self.log_text.insert("end", "\n".join(lines) + "\n")
            line_count = int(self.log_text.index("end-1c").split(".", 1)[0]) - 1
            overflow = line_count - len(self.log_lines)
            if overflow > 0:
                self.log_text.delete("1.0", f"{overflow + 1}.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_lines.clear()
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self._set_status("日志已清空")

    def _poll_logs(self) -> None:
        new_lines = []
        while True:
            try:
                message = self.log_queue.get_nowait()
            except Empty:
                break
            self.log_lines.append(message)
            new_lines.append(message)
        if new_lines:
            self._append_log_text(new_lines)
        self.root.after(200, self._poll_logs)

    def _poll_state_changes(self) -> None:
        if self.state_changed_event.is_set():
            self.state_changed_event.clear()
            self.refresh_task_list()
        self.root.after(1000, self._poll_state_changes)

    def on_close(self) -> None:
        try:
            self._apply_settings_to_store()
            with self.store.lock:
                self.store.save()
        except Exception:
            self.logger.debug("Failed to save config on close", exc_info=True)
        try:
            self.scheduler.stop()
        except Exception:
            self.logger.debug("Failed to stop scheduler cleanly", exc_info=True)
        self.root.destroy()
