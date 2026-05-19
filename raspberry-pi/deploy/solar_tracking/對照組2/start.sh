#!/bin/bash
# 對照組2 啟動腳本（手動測試用）
# 用法：bash start.sh

cd "$(dirname "$0")"
echo "=== 對照組 II｜差分感測追日 啟動 ==="
echo "工作目錄：$(pwd)"
echo "Python  ：$(which python3)"
echo "system_id：4"
echo ""
python3 traditional_controller.py