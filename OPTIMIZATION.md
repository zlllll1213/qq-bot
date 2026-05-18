# QQ Bot 优化开发文档

> 基于当前代码库（2026-05-18）的全面分析，按优先级排列。

---

## 一、高优先级（可靠性 / 正确性）

### 1. `sender.py` — 双重等待冗余

**位置：** `sender.py:195-197`

```python
# 当前：wait_for_frontmost_app 之后又 sleep 整个 open_wait，等了两次
if not wait_for_frontmost_app(app_name, timeout=max(open_wait, 3.0)):
    logger.warning(...)
_sleep(open_wait)   # ← 冗余！wait 已经消耗了时间
```

**修复方案：** 去掉 `_sleep(open_wait)`，仅在 `wait_for_frontmost_app` 返回 `False` 时追加一个短暂固定等待。

```python
if not wait_for_frontmost_app(app_name, timeout=max(open_wait, 3.0)):
    logger.warning("QQ did not become frontmost within the expected time window")
    _sleep(1.0)   # 仅在超时后补一个小延迟
```

---

### 2. `sender.py` — 重复的按键别名表

**位置：** `parse_hotkey`（第 76-92 行）和 `_press_key_name`（第 96-110 行）各自维护一套映射。

**修复方案：** 提取为模块级常量，两个函数共用：

```python
_KEY_ALIASES: dict[str, str] = {
    "cmd": "command", "command": "command",
    "ctrl": "control", "control": "control",
    "alt": "option",   "option": "option",
    "shift": "shift",  "fn": "fn",
    "return": "enter", "enter": "enter",
    "esc": "esc",      "escape": "esc",
    "tab": "tab",
    "up": "up", "down": "down", "left": "left", "right": "right",
}
```

---

### 3. `scheduler.py` — `_attempted_slots` 按数量清理不可靠

**位置：** `scheduler.py:73-74`

```python
if len(self._attempted_slots) > 1000:
    self._attempted_slots.clear()  # 整体清空，可能让刚加的 slot 在同一分钟内重复触发
```

**修复方案：** 按日期前缀过期，只清理昨天及更早的记录：

```python
def _cleanup_old_slots(self, today: str) -> None:
    self._attempted_slots = {
        s for s in self._attempted_slots if s.startswith(today)
    }
```

在 `_tick` 开头每次调用 `_cleanup_old_slots(today)`。

---

### 4. `scheduler.py` — 调度器 tick 间隔为 10 秒，存在时间窗口遗漏

**位置：** `scheduler.py:39-45`

如果系统负载高或 GUI 线程阻塞，可能连续 3 次 tick 都跳过同一分钟。

**修复方案：** 将间隔降至 5 秒，并在 tick 内记录"当前分钟"是否已检查过（利用改造后的 `_attempted_slots`）。5 秒间隔仍很低开销。

```python
self._scheduler.add_job(self._tick, "interval", seconds=5, ...)
```

---

### 5. `sender.py` — 发送失败无重试

调用 `send_message` 失败时，`scheduler.py` 只记录日志并 `continue`，任务当天不会再次尝试。

**修复方案：** 在 `Task` 中增加 `last_error: str = ""` 字段，发送失败时写入错误摘要并持久化，方便在 GUI 中展示。

**models.py 改动：**
```python
last_error: str = ""
```
并在 `to_dict` / `from_dict` 中加入对应序列化。

**scheduler.py 改动（失败路径）：**
```python
except Exception as exc:
    logger.exception("Scheduled send failed for task %s", task.name or task.id)
    with self.store.lock:
        live_task = next((t for t in self.store.tasks if t.id == task.id), None)
        if live_task:
            live_task.last_error = str(exc)[:200]
            self.store.save()
    continue
```

---

## 二、中优先级（用户体验）

### 6. `gui.py` — `configure_logging` 被调用两次

**位置：** `main.py:10`（无回调）和 `gui.py:28`（带回调）

`_configured` 标志阻止了重复添加 handler，但 `main.py` 的调用毫无意义。

**修复方案：** 删除 `main.py` 中的 `configure_logging()` 调用，只保留 `gui.py` 里的那一次。

```python
# main.py 改为：
def main() -> None:
    root = tk.Tk()
    QQSenderApp(root)
    root.mainloop()
```

---

### 7. `gui.py` — `_append_log_text` 每次全量重写

**位置：** `gui.py:502-509`

每 200ms 删除全部日志文本再重新插入 100 行，造成不必要的闪烁。

**修复方案：** 改为增量追加，仅将新到的行 append 到末尾：

```python
def _poll_logs(self) -> None:
    new_lines = []
    while True:
        try:
            new_lines.append(self.log_queue.get_nowait())
        except Empty:
            break
    if new_lines:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", "\n".join(new_lines) + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        for line in new_lines:
            self.log_lines.append(line)
    self.root.after(200, self._poll_logs)
```

---

### 8. `gui.py` — `_set_busy_state` 只遍历两层子组件

**位置：** `gui.py:465-473`

PanedWindow 里的按钮在第三层嵌套，无法被禁用。

**修复方案：** 递归遍历所有子组件：

```python
def _set_busy_state(self, busy: bool) -> None:
    state = "disabled" if busy else "normal"
    def _walk(widget):
        for child in widget.winfo_children():
            if isinstance(child, ttk.Button):
                child.configure(state=state)
            _walk(child)
    _walk(self.root)
```

---

### 9. `gui.py` — 任务列表缺少"每天重复"列

当前列：时间、目标、任务名称、状态。用户无法一眼看出哪些任务是每日重复的。

**修复方案：** 在 Treeview 中增加 `repeat` 列（或在"状态"列中组合显示）：

```python
columns = ("time", "target", "name", "repeat", "enabled")
self.tree.heading("repeat", text="重复")
self.tree.column("repeat", width=55, anchor="center", stretch=False)
# 插入时：
values=(task.time, task.target, task.name, "每日" if task.repeat_daily else "单次", ...)
```

---

### 10. `gui.py` — 任务列表无颜色区分状态

禁用的任务和已发送的任务视觉上和正常任务一样。

**修复方案：** 为 Treeview 配置 tag 样式：

```python
self.tree.tag_configure("disabled", foreground="#999999")
self.tree.tag_configure("done", foreground="#4a90d9")
```

插入时按任务状态打 tag：
```python
tag = "disabled" if not task.enabled else ("done" if task.last_sent_date == today else "")
self.tree.insert("", "end", iid=task.id, values=(...), tags=(tag,))
```

---

### 11. `gui.py` — 时间字段无实时校验反馈

用户输入错误时间，只有点"保存"才能知道。

**修复方案：** 绑定 `<FocusOut>` 事件对时间输入框做即时验证，颜色提示：

```python
self.time_entry = ttk.Entry(task_frame, textvariable=self.time_var, width=14)
self.time_entry.bind("<FocusOut>", self._validate_time_field)

def _validate_time_field(self, _event=None) -> None:
    try:
        datetime.strptime(self.time_var.get().strip(), "%H:%M")
        self.time_entry.configure(foreground="")
    except ValueError:
        self.time_entry.configure(foreground="red")
```

---

## 三、低优先级（代码质量 / 可维护性）

### 12. `storage.py` — 写入前无备份

任何写入异常都会导致 `tasks.json` 损坏。

**修复方案：** 写入临时文件再原子替换：

```python
import os, tempfile

def save_tasks(...) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {...}
    with tempfile.NamedTemporaryFile(
        "w", dir=file_path.parent, suffix=".tmp", delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        tmp_path = tmp.name
    os.replace(tmp_path, file_path)   # 原子替换，防止写入中断导致文件损坏
```

---

### 13. `storage.py` — `version` 字段保存了但从不读取

**位置：** `storage.py:76`，保存时写入 `"version": 1`，但 `load_tasks` 完全忽略它。

**修复方案：** 在 `_normalize_loaded_payload` 中读取版本号，未来字段迁移时可在此处做 migration：

```python
def _normalize_loaded_payload(raw: Any) -> tuple[list[dict], dict, int]:
    version = 1
    if isinstance(raw, dict):
        version = int(raw.get("version", 1))
        ...
    return raw_tasks, raw_settings, version
```

---

### 14. `models.py` — `scheduled_date` 方法不属于数据模型

**位置：** `models.py:55-57`

`Task.scheduled_date()` 只是 `datetime.now().strftime(...)` 的包装，与任务数据无关。

**修复方案：** 删除该方法，在 `scheduler.py` 里直接调用 `datetime.now().strftime("%Y-%m-%d")`（目前 scheduler 已经这样做了，该方法实际没被调用）。

---

### 15. `scheduler.py` — `store` 参数无类型注解

**位置：** `scheduler.py:22`

```python
def __init__(self, store, send_func: Callable = send_message, ...):
```

**修复方案：** 导入 `TaskStore` 并标注：

```python
from storage import TaskStore

def __init__(self, store: TaskStore, ...):
```

---

### 16. `gui.py` — `_build_editor` 函数过长（约 90 行）

**位置：** `gui.py:97-184`

**修复方案：** 拆分为两个独立方法：

```python
def _build_settings_frame(self, parent: ttk.Frame) -> None: ...
def _build_task_frame(self, parent: ttk.Frame) -> None: ...
```

并在 `_build_editor` 中依次调用，减少单函数复杂度。

---

## 四、可选功能扩展（非必须）

| 功能 | 说明 |
|------|------|
| 任务排序 | 支持按时间列点击排序，方便管理多任务 |
| 多行消息预览 | 消息列表中预览消息前 20 字 |
| 导出/导入 | 将任务导出为 CSV，方便跨机器迁移 |
| 失败通知 | 任务发送失败时弹出系统通知（macOS `osascript display notification`） |
| 任务历史 | 记录每次发送结果（成功/失败/dry-run）到单独的 `history.json` |

---

## 五、建议改动优先顺序

```
第一轮（30 分钟内可完成）：
  ✦ 第 1 条：去掉冗余 _sleep(open_wait)
  ✦ 第 2 条：合并重复按键别名表
  ✦ 第 6 条：删除 main.py 的 configure_logging() 调用
  ✦ 第 12 条：save_tasks 改为原子写入

第二轮（需要测试验证）：
  ✦ 第 3 条：_attempted_slots 按日期过期
  ✦ 第 4 条：tick 间隔改为 5 秒
  ✦ 第 5 条：Task 增加 last_error 字段
  ✦ 第 8 条：_set_busy_state 递归遍历

第三轮（UI 打磨）：
  ✦ 第 7 条：日志增量追加
  ✦ 第 9 条：任务列表增加重复列
  ✦ 第 10 条：任务列表颜色区分
  ✦ 第 11 条：时间字段实时校验
```
