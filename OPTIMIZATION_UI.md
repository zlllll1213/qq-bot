# QQ Bot UI 前端优化文档

> 基于当前 gui.py 代码（2026-05-18）的完整审查，按优先级排列。

---

## 一、高优先级（布局 Bug / 核心体验）

### 1. `_build_task_frame` — 消息框无法随窗口纵向拉伸

**位置：** `gui.py:150`

```python
# 当前：sticky="ew" 只允许横向伸展，纵向不跟随窗口变高
task_frame.grid(row=1, column=0, sticky="ew")
```

`_build_editor` 里对 row 1 设置了 `weight=1`，本意是让消息框随窗口增高而增高，但
`task_frame` 没有 `"ns"` sticky，所以框架本身不会纵向扩展，内部的 `rowconfigure(3, weight=1)` 也就失效了。

**修复方案：**

```python
task_frame.grid(row=1, column=0, sticky="nsew")
```

同时确认 `_build_editor` 里的权重设置：

```python
parent.rowconfigure(0, weight=0)   # 自动化设置：固定高度
parent.rowconfigure(1, weight=1)   # 任务编辑：随窗口拉伸
parent.rowconfigure(2, weight=0)   # 按钮行：固定高度
```

---

### 2. `_build_log_panel` — 日志面板缺少水平滚动条

**位置：** `gui.py:235`

日志文本设置了 `wrap="none"`（不自动换行），但只配了垂直滚动条，长行（如异常堆栈、完整路径）会被截断不可见。

**修复方案：** 补一条水平滚动条：

```python
log_h_scroll = ttk.Scrollbar(log_frame, orient="horizontal", command=self.log_text.xview)
self.log_text.configure(xscrollcommand=log_h_scroll.set)
log_h_scroll.grid(row=1, column=0, sticky="ew")
```

同时日志面板允许纵向收缩（当前 `rowconfigure(1, weight=0)` 完全固定），可改为小权重：

```python
self.root.rowconfigure(1, weight=0, minsize=120)
```

---

### 3. `save_task` / `save_config` — 保存成功弹窗打断操作流

**位置：** `gui.py:461`、`gui.py:558`

每次保存都弹出 `messagebox.showinfo`，用户需要点击"确定"才能继续，高频操作下非常干扰。

**修复方案：** 在窗口底部增加一个状态栏 Label，保存后短暂显示提示，2 秒后自动清空：

```python
# _build_ui 末尾增加状态栏
self.status_var = tk.StringVar()
status_bar = ttk.Label(self.root, textvariable=self.status_var, anchor="w", padding=(8, 2))
status_bar.grid(row=2, column=0, sticky="ew")

def _set_status(self, message: str, duration_ms: int = 2000) -> None:
    self.status_var.set(message)
    self.root.after(duration_ms, lambda: self.status_var.set(""))
```

用法替换：

```python
# 原来：messagebox.showinfo("已保存", "任务已保存。")
self._set_status("✓ 任务已保存")

# 原来：messagebox.showinfo("已保存", "配置已保存到 tasks.json。")
self._set_status("✓ 配置已保存")
```

错误和删除确认仍保留 `messagebox`（破坏性操作才需要阻断）。

---

### 4. `test_send` — 测试中无进度反馈

**位置：** `gui.py:499`

测试发送期间所有按钮被禁用，但没有任何视觉提示告诉用户程序正在工作，还是卡住了。

**修复方案：** 按钮文字改为"测试中…"，完成后还原：

```python
def test_send(self) -> None:
    ...
    self._set_busy_state(True)
    self._test_send_btn.configure(text="测试中…")   # 找到该按钮的引用

    def worker() -> None:
        ...
        finally:
            self.root.after(0, lambda: self._test_send_btn.configure(text="测试发送"))
            self.root.after(0, lambda: self._set_busy_state(False))
```

同时在 `_build_button_row` 里保存按钮引用：

```python
self._test_send_btn = ttk.Button(task_actions, text="测试发送", command=self.test_send, width=10)
self._test_send_btn.grid(row=0, column=4, sticky="ew", padx=4, pady=5)
```

---

## 二、中优先级（操作效率 / 信息展示）

### 5. 键盘快捷键缺失

**位置：** `_build_ui`

高频操作全靠鼠标点击，效率低。

**修复方案：** 在 `_build_ui` 末尾绑定全局快捷键：

```python
self.root.bind("<Command-s>", lambda _: self.save_task())   # macOS
self.root.bind("<Command-n>", lambda _: self.new_task())
self.root.bind("<Delete>",    lambda _: self.delete_task())
self.root.bind("<Command-t>", lambda _: self.test_send())
```

按钮文字也同步更新为带提示：

```python
"保存任务  ⌘S"
"新增  ⌘N"
"测试发送  ⌘T"
```

---

### 6. "启用/禁用" 按钮文字不反映当前状态

**位置：** `gui.py:212`、`gui.py:493`

按钮文字永远是"启用/禁用"，用户选中一个已禁用的任务时，不能一眼看出"点这个按钮会启用它"。

**修复方案：** 在 `_load_task_into_form` 里动态更新按钮文字：

```python
# _build_button_row 保存引用
self._toggle_btn = ttk.Button(task_actions, text="启用/禁用", command=self.toggle_enabled, width=10)

# _load_task_into_form 末尾增加
self._toggle_btn.configure(text="禁用" if task.enabled else "启用")

# new_task 末尾增加（新任务默认启用）
self._toggle_btn.configure(text="禁用")
```

---

### 7. 设置面板无单位提示，参数含义不直观

**位置：** `gui.py:126-134`

`open_wait`、`search_wait` 等输入框没有单位说明，用户不确定填的是秒、毫秒还是其他。

**修复方案：** 在每个数值输入框后面加单位 Label：

```python
def _add_labeled_entry_with_unit(
    self, parent, row, col, label, variable, unit="s", width=8
) -> ttk.Entry:
    ttk.Label(parent, text=label).grid(row=row, column=col,   sticky="w",  padx=4, pady=4)
    entry = ttk.Entry(parent, textvariable=variable, width=width)
    entry.grid(         row=row, column=col+1, sticky="ew", padx=(4,0), pady=4)
    ttk.Label(parent, text=unit, foreground="#666666").grid(
        row=row, column=col+1, sticky="e", padx=(0,4)
    )
    return entry
```

用于 `打开后等待`、`搜索后等待`、`聊天后等待`、`发送前延迟` 四个字段。

---

### 8. Dry-run 开启时缺乏全局视觉警告

**位置：** `gui.py:144`

Dry-run 勾选后，"测试发送"不会真正发送，但 UI 上除了那个勾选框外没有任何提醒，容易遗忘。

**修复方案：** Dry-run 开启时在状态栏持续显示警告，并给 Dry-run 勾选框加红色文字：

```python
self.dry_run_var.trace_add("write", self._on_dry_run_changed)

def _on_dry_run_changed(self, *_) -> None:
    if self.dry_run_var.get():
        self.status_var.set("⚠ Dry-run 模式：所有发送操作仅模拟，不会真正执行")
    else:
        self.status_var.set("")
```

---

### 9. 任务列表缺少隔行背景色

**位置：** `gui.py:80`

任务多时纯白背景难以对齐行，容易看串。

**修复方案：** 为奇偶行配置 tag：

```python
self.tree.tag_configure("row_odd",  background="#f5f5f5")
self.tree.tag_configure("row_even", background="#ffffff")

# refresh_task_list 里插入时：
for i, task in enumerate(tasks):
    row_tag = "row_odd" if i % 2 else "row_even"
    tags = (status_tag, row_tag) if status_tag else (row_tag,)
    self.tree.insert(..., tags=tags)
```

注意：tag 样式中 `foreground` 优先级高于 `background`，原有的 disabled/done/error 颜色不会受影响。

---

### 10. 任务列表支持列点击排序

**位置：** `gui.py:81-90`

点击"时间"列标题可以排序，方便管理多个任务。

**修复方案：**

```python
self._sort_col: str = "time"
self._sort_reverse: bool = False

for col in columns:
    self.tree.heading(col, text=..., command=lambda c=col: self._sort_by_col(c))

def _sort_by_col(self, col: str) -> None:
    if self._sort_col == col:
        self._sort_reverse = not self._sort_reverse
    else:
        self._sort_col = col
        self._sort_reverse = False
    with self.store.lock:
        self.store.tasks.sort(
            key=lambda t: getattr(t, col, ""),
            reverse=self._sort_reverse,
        )
    self.refresh_task_list()
```

---

### 11. `new_task` 后焦点未移到输入框

**位置：** `gui.py:428`

点击"新增"后，光标停留在原处，用户需要手动点击"任务名称"输入框才能开始输入。

**修复方案：** 在 `new_task` 末尾聚焦：

```python
# _build_task_frame 里保存引用
self._name_entry = self._add_labeled_entry(task_frame, 0, 0, "任务名称", self.name_var, columnspan=3)

# new_task 末尾
self._name_entry.focus_set()
```

---

## 三、低优先级（细节打磨）

### 12. 消息文本框缺少字数统计

**位置：** `gui.py:187`

**修复方案：** 在消息框右下角加字数 Label，随输入实时更新：

```python
self.char_count_var = tk.StringVar(value="0 字")
ttk.Label(message_wrap, textvariable=self.char_count_var,
          foreground="#999999").grid(row=1, column=0, sticky="e", padx=4)

self.message_text.bind("<KeyRelease>", self._update_char_count)
self.message_text.bind("<<Paste>>",    self._update_char_count)

def _update_char_count(self, _event=None) -> None:
    content = self.message_text.get("1.0", "end-1c")
    self.char_count_var.set(f"{len(content)} 字")
```

---

### 13. 日志面板增加"清空"按钮

**位置：** `gui.py:228`

日志最多保留 100 行（deque maxlen），但如果用户想快速清空看最新内容，目前只能等旧日志被自动覆盖。

**修复方案：**

```python
log_header = ttk.Frame(log_frame)
log_header.grid(row=0, column=0, columnspan=2, sticky="ew")
ttk.Label(log_header, text="最近日志").pack(side="left")
ttk.Button(log_header, text="清空", width=6,
           command=self._clear_log).pack(side="right", padx=4)

def _clear_log(self) -> None:
    self.log_lines.clear()
    self.log_text.configure(state="normal")
    self.log_text.delete("1.0", "end")
    self.log_text.configure(state="disabled")
```

注意 `_build_log_panel` 内的 LabelFrame 改为普通 Frame（LabelFrame 的标题不支持在内部放按钮），或把"最近日志"标题放进 `log_header`。

---

### 14. 任务列表支持右键菜单

**位置：** `gui.py:100`

常用操作（删除、启用/禁用、测试发送）目前只能通过底部按钮触发，右键菜单更直觉。

**修复方案：**

```python
self._context_menu = tk.Menu(self.root, tearoff=0)
self._context_menu.add_command(label="编辑",     command=lambda: None)
self._context_menu.add_command(label="启用/禁用", command=self.toggle_enabled)
self._context_menu.add_separator()
self._context_menu.add_command(label="删除",     command=self.delete_task)

self.tree.bind("<Button-2>", self._show_context_menu)   # macOS 右键

def _show_context_menu(self, event) -> None:
    row = self.tree.identify_row(event.y)
    if row:
        self.tree.selection_set(row)
        self._context_menu.post(event.x_root, event.y_root)
```

---

### 15. 无"清除任务错误"的快捷入口

**位置：** `gui.py:373`

任务进入"失败"状态后，唯一清除 `last_error` 的方式是点"保存任务"（`_task_from_form` 会保留现有 `last_error`，除非重新触发成功）。用户很可能不知道该怎么消红。

**修复方案：** 在按钮行增加"清除错误"按钮，仅在当前任务有错误时生效：

```python
self._clear_error_btn = ttk.Button(
    task_actions, text="清除错误", command=self.clear_task_error, width=10
)
self._clear_error_btn.grid(row=0, column=5, sticky="ew", padx=4, pady=5)

def clear_task_error(self) -> None:
    task_id = self.current_task_id
    if not task_id:
        return
    with self.store.lock:
        task = next((t for t in self.store.tasks if t.id == task_id), None)
        if task:
            task.last_error = ""
            self.store.save()
    self.refresh_task_list()
    self._set_status("✓ 错误状态已清除")
```

---

## 四、建议修改顺序

```
第一轮（布局 Bug，改完立刻见效）：
  ✦ 第 1 条：task_frame.grid sticky 改为 "nsew"
  ✦ 第 2 条：日志面板补水平滚动条
  ✦ 第 4 条：test_send 按钮文字反馈

第二轮（日常使用体验提升）：
  ✦ 第 3 条：状态栏替换保存弹窗
  ✦ 第 6 条：启用/禁用按钮动态文字
  ✦ 第 7 条：设置字段加单位 (s)
  ✦ 第 8 条：Dry-run 全局警告
  ✦ 第 11 条：新增任务自动聚焦

第三轮（锦上添花）：
  ✦ 第 5 条：键盘快捷键
  ✦ 第 9 条：任务列表隔行背景
  ✦ 第 10 条：列点击排序
  ✦ 第 12 条：消息字数统计
  ✦ 第 13 条：日志清空按钮
  ✦ 第 14 条：右键菜单
  ✦ 第 15 条：清除错误按钮
```
