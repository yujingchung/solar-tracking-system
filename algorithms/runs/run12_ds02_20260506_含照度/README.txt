訓練結果: run12_ds02_20260506_含照度
訓練日期: 2026-05-14 15:30

使用資料集: ds02_20260506_含照度
模型版本: v8

模型配置:
    特徵維度    = 10
    MF 數量     = 7
    照度特徵    = 是
    特徵列表    = hour_sin, hour_cos, day_sin, day_cos, tilt_sin, tilt_cos, azimuth_sin, azimuth_cos, clearness, panel_calib

測試集結果:
    RMSE  = 41.35 W
    MAE   = 28.91 W
    R²    = 0.7580
    MAPE  = 39.18 %

輸出檔案:
    anfis_with_illumination.keras
    scaler_X_with_illumination.save
    model_config_with_illumination.json
    best_anfis.keras

備註:
