訓練結果: run05_ds02_20260506_含照度
訓練日期: 2026-05-06 17:22

使用資料集: ds02_20260506_含照度

模型配置:
    特徵維度    = 9
    MF 數量     = 7
    照度特徵    = 是
    特徵列表    = hour_sin, hour_cos, day_sin, day_cos, tilt_sin, tilt_cos, azimuth_sin, azimuth_cos, illumination

測試集結果:
    RMSE  = 32.43 W
    MAE   = 20.98 W
    R²    = 0.8442
    MAPE  = 36.56 %

輸出檔案:
    anfis_with_illumination.keras
    scaler_X_with_illumination.save
    model_config_with_illumination.json
    best_anfis.keras

備註:
