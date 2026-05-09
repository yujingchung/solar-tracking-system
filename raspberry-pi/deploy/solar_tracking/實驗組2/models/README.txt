請將以下三個訓練好的模型檔案複製到此資料夾：

  anfis_with_illumination.keras         ← ANFIS 主模型
  scaler_X_with_illumination.save       ← 輸入特徵的 StandardScaler
  model_config_with_illumination.json   ← 模型設定（has_illumination 等參數）

這些檔案由 algorithms/train_pipeline.py 訓練產出，
位於 algorithms/runs/runXX_dsXX_.../  資料夾內。

沒有模型檔案時程式仍可運行（使用內建近似公式），
但追日效果將大幅降低，請務必在部署前放入模型。
