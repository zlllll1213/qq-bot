# QQ 定时发送助手

一个面向 macOS / Windows 的本地 Python 桌面自动化工具。它通过 `tkinter` 提供图形界面，借助 `pyautogui`、`pyperclip` 和系统窗口自动化能力，在指定时间打开 QQ、搜索联系人或群聊，并发送预设消息。

> 本项目只做本地 UI 自动化，不接入 QQ 协议，不使用非官方 QQ API，也不绕过平台安全限制。

## 功能特性

- 新增、编辑、删除、启用/禁用定时任务
- 支持单次任务和每天重复任务
- 支持立即测试发送
- 支持 Dry-run 模式，模拟流程但不实际发送
- 支持只填入消息、不按 Enter 的安全测试模式
- 支持任务失败原因展示和清除错误状态
- 支持任务列表排序、右键菜单、隔行背景色
- 支持消息字数统计、日志面板、状态栏反馈
- 支持本地配置持久化

## 环境要求

- macOS 或 Windows
- Python 3.10 或更高版本
- 已安装并登录 QQ
- macOS 需要给运行 Python 的终端或应用开启辅助功能权限：
  - 系统设置 -> 隐私与安全性 -> 辅助功能
- Windows 建议使用普通桌面版 QQ，并保持 QQ 已登录；如果无法激活窗口，可尝试用管理员权限启动终端或填写 QQ 可执行文件完整路径。

基础功能不需要屏幕录制权限。只有后续扩展到截图识别时，才可能需要额外开启屏幕录制权限。

## 安装与运行

### macOS / Linux shell

```bash
git clone https://github.com/zlllll1213/qq-bot.git
cd qq-bot

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python main.py
```

macOS 也可以双击项目根目录下的 `start.command` 启动。首次使用前仍需要先安装依赖。

如果第一次双击没有反应，可以右键 `start.command`，选择“打开”，再确认 macOS 的安全提示。

### Windows PowerShell

```powershell
git clone https://github.com/zlllll1213/qq-bot.git
cd qq-bot

py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

python main.py
```

Windows 也可以双击 `start.bat` 启动。脚本会自动创建虚拟环境并安装依赖。

## 使用方式

1. 启动应用。
2. 新增任务。
3. 填写任务名称、目标联系人或群聊、发送时间和消息内容。
4. 按需勾选“每天重复”“启用”“发送 Enter”。
5. 点击“保存”。
6. 保持电脑开机、QQ 已登录、程序持续运行。

时间格式使用 24 小时制 `HH:MM`：

- 半夜十二点：`00:00`
- 中午十二点：`12:00`
- 晚上十一点五十九：`23:59`

如果任务没有勾选“每天重复”，执行成功一次后会自动禁用。需要每天发送时，请同时勾选“每天重复”和“启用”。

## 界面快捷键

- 新增任务：macOS `Command + N`，Windows `Ctrl + N`
- 保存任务：macOS `Command + S`，Windows `Ctrl + S`
- 测试发送：macOS `Command + T`，Windows `Ctrl + T`
- `Delete`：删除任务

## 配置文件

运行后会在项目根目录生成本地配置文件：

```text
tasks.json
app.log
```

这两个文件可能包含联系人、群聊名称、消息内容或运行日志，默认已被 `.gitignore` 忽略，不建议提交到公开仓库。

仓库中提供了 `tasks.example.json` 作为配置格式示例。

## 自动化流程

程序会按以下方式操作 QQ：

1. macOS 使用 `open -a QQ` 打开 QQ；Windows 使用系统启动命令或配置的 QQ 路径打开 QQ。
2. 等待 QQ 成为前台应用。
3. 使用搜索快捷键，macOS 默认 `command+f`，Windows 默认 `ctrl+f`。
4. 粘贴目标联系人或群聊名称。
5. 根据“搜索结果序号”选择匹配项。
6. 进入聊天窗口。
7. 粘贴消息内容。
8. 根据任务设置决定是否按 Enter 发送。
9. 可选：发送后切回原前台应用。

## 配置项说明

- `QQ App 名称`：默认 `QQ`。Windows 如无法启动，可填写 QQ.exe 的完整路径。
- `搜索快捷键`：macOS 默认 `command+f`，Windows 默认 `ctrl+f`
- `打开后等待`：打开 QQ 后等待秒数
- `搜索后等待`：搜索目标后等待秒数
- `聊天后等待`：进入聊天窗口后等待秒数
- `发送前延迟`：粘贴消息后、按 Enter 前的等待秒数
- `结果序号`：搜索结果中要选择第几个
- `关闭搜索浮层`：选择结果后是否关闭搜索浮层
- `Dry-run`：只模拟流程，不实际操作发送
- `发送后切回前台应用`：发送后尝试恢复原应用焦点

如果联系人或群聊名称比较常见，搜索结果可能不止一个。可以把“结果序号”改成第 2 个、第 3 个等。

## 常见问题

### 没有反应

- 确认 QQ 已登录。
- 确认 Python/终端已开启辅助功能权限。
- 确认程序仍在运行。
- Windows 如果默认 `QQ` 无法打开，请在“QQ App 名称”里填写 `QQ.exe` 完整路径，例如 `C:\Program Files\Tencent\QQNT\QQ.exe`。
- Windows 如果 QQ 已打开但无法激活，请把“QQ App 名称”改成 QQ 窗口标题中能看到的关键字，例如 `QQ`。

### 搜索框没打开

- 检查 QQ 当前版本的搜索快捷键是否仍是默认值。
- macOS 通常是 `command+f`，Windows 通常是 `ctrl+f`。
- 尝试在设置里修改“搜索快捷键”。

### 消息没发出去

- 检查目标名称是否准确。
- 增大“打开后等待”“搜索后等待”“聊天后等待”。
- 先开启 Dry-run 或关闭“发送 Enter”测试流程。

### 定时没触发

- 确认任务处于启用状态。
- 确认时间格式是 `HH:MM`。
- 确认脚本一直在运行。
- 检查 `app.log`。

### 想紧急停止

把鼠标移动到屏幕左上角，`pyautogui.FAILSAFE = True` 会触发 PyAutoGUI 的紧急停止。

## 注意事项

- 发送时会短暂激活 QQ。
- QQ UI、窗口标题或快捷键变化可能导致自动化流程失效。
- Windows 窗口激活依赖当前 QQ 窗口标题匹配，“QQ App 名称”可填 `QQ`、窗口标题关键字或 QQ.exe 路径。
- 建议先使用 Dry-run 或不勾选“发送 Enter”进行测试。
- 本工具无法确认 QQ 服务端是否真正投递成功，只能确认本地自动化动作是否执行。
- 请遵守 QQ 平台规则，不要用于骚扰、垃圾消息或任何违法违规用途。

## 许可证

本项目使用 MIT License 开源，详见 [LICENSE](LICENSE)。
