# QQ Bot 优化开发文档 V2

> 基于第一轮优化完成后的代码（2026-05-18）二次审查，按优先级排列。

---

## 一、高优先级（并发安全 / 正确性）

### 1. `gui.py` — `test_send` 读取 settings 未加锁

**位置：** `gui.py:487`

`scheduler.py` 的后台线程会写 `self.store.settings`，而 `test_send` 的工作线程裸读它，存在竞争条件。

```python
# 当前：无锁读，可能读到调度器正在写的中间态
status = send_message(task, dict(self.store.settings))
```

**修复方案：** 在工作线程内先加锁复制快照，再释放锁执行耗时操作：

```python
def worker() -> None:
    with self.store.lock:
        settings_snapshot = dict(self.store.settings)
    try:
        status = send_message(task, settings_snapshot)
    ...
```

对比：`scheduler.py:101` 里取 settings 已经正确加锁，保持两处一致。

---

## 二、中优先级（逻辑隐患 / 用户体验）

### 2. `storage.py` — `if settings:` 无法区分 `None` 和 `{}`

**位置：** `storage.py:87`

```python
# 当前：空字典 {} 会被当作 False，settings 内容不会写入 payload
if settings:
    payload["settings"].update(settings)
```

目前 `TaskStore.save()` 传入的 `self.settings` 不会为空字典，但这是一个隐患：如果将来有其他调用路径传入 `{}`，本意是"清空自定义设置、使用全默认值"，实际上却静默地保留了 `payload["settings"]` 中的旧值。

**修复方案：**

```python
if settings is not None:
    payload["settings"].update(settings)
```

---

### 3. `scheduler.py` — `_cleanup_old_slots` 使用魔法数字 `-16`

**位置：** `scheduler.py:70`

```python
# 当前：依赖 uuid hex 恰好 32 字节、日期格式恰好 16 字节，脆弱
self._attempted_slots = {
    slot for slot in self._attempted_slots if slot[-16:].startswith(today)
}
```

slot key 的格式是 `"{task_id}:{YYYY-MM-DD HH:MM}"`，用 `split` 语义更清晰：

**修复方案：**

```python
def _cleanup_old_slots(self, today: str) -> None:
    self._attempted_slots = {
        slot for slot in self._attempted_slots
        if slot.split(":", 1)[-1].startswith(today)
    }
```

不依赖任何长度假设，将来即使 `task_id` 生成方式改变也不会静默出错。

---

### 4. `gui.py` — `last_error` 有颜色但错误内容不可见

**位置：** `gui.py:350-362`

任务发送失败时，列表行变红，但用户无法在 GUI 中直接看到出错原因，只能翻日志。

**修复方案 A（最简单）：** 在"状态"列里追加错误摘要：

```python
if task.last_error:
    # 截断到 25 字，避免列过宽
    short_err = task.last_error[:25] + ("…" if len(task.last_error) > 25 else "")
    status = f"失败: {short_err}"
    tags = ("error",)
```

**修复方案 B（更优雅）：** 为 Treeview 每行绑定 tooltip，鼠标悬停时显示完整 `last_error`：

```python
# 绑定 Motion 事件，识别当前行并弹出 Tooltip
self.tree.bind("<Motion>", self._on_tree_motion)
```

方案 A 改动最小，方案 B 体验更好，按需选择。

---

## 三、低优先级（代码质量 / 可维护性）

### 5. `gui.py` — `delete_task` 中多余的 `_load_settings_into_form()` 调用

**位置：** `gui.py:451`

```python
self.current_task_id = None
self.new_task()
self._load_settings_into_form()  # 删除任务不影响 settings，此行无效
self.refresh_task_list()
```

删除任务不会改变 settings，`_load_settings_into_form()` 在这里毫无作用。直接删除该行即可。

---

### 6. `models.py` — `from_dict` 中每个字段都手写了相同的防御性转换

**位置：** `models.py:40-52`

```python
# 当前：9 个字段各自写一遍 str(data.get(...) or "")，未来新增字段容易漏
id=str(data.get("id") or _default_id()),
name=str(data.get("name") or ""),
target=str(data.get("target") or ""),
...
```

**修复方案：** 提取两个小辅助函数统一处理：

```python
def _s(data: dict, key: str, default: str = "") -> str:
    return str(data.get(key) or default)

def _b(data: dict, key: str, default: bool = False) -> bool:
    return bool(data.get(key, default))
```

然后 `from_dict` 变为：

```python
@classmethod
def from_dict(cls, data: Dict[str, Any]) -> "Task":
    return cls(
        id=_s(data, "id") or _default_id(),
        name=_s(data, "name"),
        target=_s(data, "target"),
        time=_s(data, "time") or "09:00",
        message=_s(data, "message"),
        repeat_daily=_b(data, "repeat_daily"),
        enabled=_b(data, "enabled", True),
        send_enter=_b(data, "send_enter", True),
        last_sent_date=_s(data, "last_sent_date"),
        last_error=_s(data, "last_error"),
    )
```

新增字段时只需加一行，不会遗漏转换。

---

## 四、可选功能扩展（非必须）

| 功能 | 说明 | 涉及文件 |
|------|------|----------|
| 任务列表列点击排序 | 点击"时间"列标题按时间升序/降序排列 | `gui.py` |
| 错误任务 Tooltip | 鼠标悬停失败行时弹出完整错误信息 | `gui.py` |
| 应用启动时加载失败提示 | `TaskStore.__init__` 若 JSON 损坏，在 GUI 启动后弹出警告 | `storage.py` / `gui.py` |
| 任务历史记录 | 每次发送结果（成功/失败/dry-run）写入 `history.json` | `scheduler.py` |
| 失败后系统通知 | 任务发送失败时弹出 macOS 系统通知 | `scheduler.py` |

---

## 五、建议修改顺序

```
第一轮（5 分钟内可完成，风险极低）：
  ✦ 第 1 条：test_send 加锁读 settings
  ✦ 第 2 条：if settings is not None
  ✦ 第 5 条：删除多余的 _load_settings_into_form() 调用

第二轮（需要小测试）：
  ✦ 第 3 条：_cleanup_old_slots 改用 split
  ✦ 第 4 条：last_error 在 GUI 中展示（选方案 A 或 B）

第三轮（重构，选做）：
  ✦ 第 6 条：models.py from_dict 提取辅助函数
```
