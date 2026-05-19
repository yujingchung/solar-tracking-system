訓練結果: run07_ds02_20260506_含照度_v3_weighted
訓練日期: 2026-05-11 14:15

使用資料集: ds02_20260506_含照度
模型版本: v3

模型配置:
    特徵維度    = 12
    MF 數量     = 7
    照度特徵    = 是
    特徵列表    = hour_sin, hour_cos, day_sin, day_cos, tilt_sin, tilt_cos, azimuth_sin, azimuth_cos, illumination, theoretical_poa, solar_elev_sin, solar_elev_cos
    weight_alpha = 0.7

測試集結果:
    RMSE  = 35.17 W
    MAE   = 23.68 W
    R²    = 0.8246
    MAPE  = 38.76 %

輸出檔案:
    anfis_with_illumination.keras
    scaler_X_with_illumination.save
    model_config_with_illumination.json
    best_anfis.keras

備註:
