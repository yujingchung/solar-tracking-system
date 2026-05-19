#!/bin/bash
# 實驗組1 啟動腳本（手動測試用）
# 用法：bash start.sh

cd "$(dirname "$0")"
echo "=== 實驗組 I｜ANFIS 智慧追日 啟動 ==="
echo "工作目錄：$(pwd)"
echo "Python  ：$(which python3)"
echo "system_id：1"
echo ""
# ANFIS：確認模型檔案存在
if [ ! -f "models/anfis_with_illumination.keras" ]; then
    echo "[警告] 缺 models/anfis_with_illumination.keras"
    echo "       缺少模型時控制器會 fallback 到模擬預測（不可正式部署）"
fi

python3 anfis_controller.py