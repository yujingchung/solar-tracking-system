#!/bin/bash
# 對照組啟動腳本
# 用法：bash start.sh
# 或設定 systemd 開機自動執行（見 solar_tracking.service）

cd "$(dirname "$0")"

echo "=== 對照組控制器啟動 ==="
echo "工作目錄：$(pwd)"
echo "Python：$(which python3)"

python3 traditional_controller.py
