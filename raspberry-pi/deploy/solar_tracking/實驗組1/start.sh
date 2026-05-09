#!/bin/bash
# 實驗組啟動腳本
# 用法：bash start.sh
# 或設定 systemd 開機自動執行（見 solar_tracking.service）

cd "$(dirname "$0")"

echo "=== 實驗組控制器啟動 ==="
echo "工作目錄：$(pwd)"
echo "Python：$(which python3)"

# 確認模型檔案存在
if [ ! -f "models/anfis_with_illumination.keras" ]; then
    echo "[警告] models/ 資料夾下找不到 anfis_with_illumination.keras"
    echo "       請先將訓練好的模型檔案複製到 models/ 資料夾："
    echo "         anfis_with_illumination.keras"
    echo "         scaler_X_with_illumination.save"
    echo "         model_config_with_illumination.json"
    echo "       程式仍會繼續（無模型時使用內建近似公式）"
fi

python3 anfis_controller.py
