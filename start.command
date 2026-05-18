#!/bin/zsh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
  echo "未找到 .venv 虚拟环境。"
  echo "请先在终端执行："
  echo "python3 -m venv .venv"
  echo "source .venv/bin/activate"
  echo "pip install -r requirements.txt"
  read -r "reply?按回车退出..."
  exit 1
fi

source ".venv/bin/activate"
python main.py

