訓練結果: run10_ds02_20260506_含照度
訓練日期: 2026-05-14 14:52

使用資料集: ds02_20260506_含照度
模型版本: v5

模型配置:
    特徵維度    = 9
    MF 數量     = 7
    照度特徵    = 是
    特徵列表    = hour_sin, hour_cos, day_sin, day_cos, tilt_sin, tilt_cos, azimuth_sin, azimuth_cos, clearness

測試集結果:
    RMSE  = 38.32 W
    MAE   = 26.56 W
    R²    = 0.7921
    MAPE  = 38.03 %

輸出檔案:
    anfis_with_illumination.keras
    scaler_X_with_illumination.save
    model_config_with_illumination.json
    best_anfis.keras

備註:
