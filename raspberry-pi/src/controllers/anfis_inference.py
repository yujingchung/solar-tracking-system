#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
anfis_inference.py
==================
ANFIS v5/v6/v8 推論模組（為控制器封裝）

提供統一 API：給定 timestamp + 候選角度集合 + 當前照度 (GHI)，
透過 pvlib 算各角度 POA，跑 ANFIS 預測 PR_norm，回推每個角度的預期功率，
並回傳最佳角度。

設計目標：
- 不依賴硬體（pure compute），可單獨單元測試
- 支援 v5 / v6 / v8 不同特徵集（從 model_config.json 推斷）
- 對 OOD 角度（超出資料集 12 角度範圍）合理推論（POA 物理項保證）

用法：
    inf = AnfisInference(model_dir='/path/to/run0X')
    result = inf.predict_best_angle(
        timestamp=datetime.now(),
        illumination_wm2=850.0,
        candidate_angles=[(20, 180), (15, 180), ...],
        panel_calib=None,  # v8 才需要
    )
    # result = {'best_angle': (20, 180), 'predicted_power': 245.3,
    #           'all_predictions': {(20, 180): 245.3, ...}}
"""
import os
import math
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Dict, Optional

import numpy as np

try:
    import tensorflow as tf
    import joblib
    TF_AVAILABLE = True

    # ── 必須帶進 SimpleFuzzyLayer 定義（與訓練端一致），否則 keras 無法還原模型
    @tf.keras.utils.register_keras_serializable(package='solar_anfis')
    class SimpleFuzzyLayer(tf.keras.layers.Layer):
        """模糊化層：每個輸入特徵 num_mfs 個 Gaussian MF（與 solar_anfis_model_vX.py 一致）"""

        def __init__(self, num_mfs, **kwargs):
            self.num_mfs = num_mfs
            super().__init__(**kwargs)

        def build(self, input_shape):
            self.centers = self.add_weight(
                name='centers',
                shape=(input_shape[-1], self.num_mfs),
                initializer=tf.keras.initializers.RandomUniform(-1.5, 1.5),
                trainable=True
            )
            self.sigmas = self.add_weight(
                name='sigmas',
                shape=(input_shape[-1], self.num_mfs),
                initializer=tf.keras.initializers.Constant(0.5),
                trainable=True
            )
            super().build(input_shape)

        def call(self, x):
            expanded_x = tf.expand_dims(x, -1)
            dist = tf.square(expanded_x - self.centers)
            return tf.exp(-dist / (2 * tf.square(tf.abs(self.sigmas) + 0.1)))

        def get_config(self):
            config = super().get_config()
            config.update({'num_mfs': self.num_mfs})
            return config

        def compute_output_shape(self, input_shape):
            return (input_shape[0], input_shape[1], self.num_mfs)
except ImportError:
    TF_AVAILABLE = False

try:
    import pandas as pd
    import pvlib
    PVLIB_AVAILABLE = True
except ImportError:
    PVLIB_AVAILABLE = False

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# Panel & site 常數（與訓練模型保持一致）
# ════════════════════════════════════════════════════════════════
PANEL_AREA_M2  = 1.948   # TS54-BMH-405 H1
PANEL_EFF_STC  = 0.208
SITE_LATITUDE  = 25.10   # 新北先鋒
SITE_LONGITUDE = 121.43
SITE_ALTITUDE  = 50


@dataclass
class InferenceResult:
    best_angle: Tuple[float, float]       # (tilt, azimuth)
    predicted_power: float                 # W
    predicted_pr: float                    # PR_norm
    poa_at_best: float                     # W/m²
    all_predictions: Dict[Tuple[float, float], float]  # 各角度的 predicted_power


class AnfisInference:
    """v5/v6/v8 統一推論介面"""

    def __init__(self, model_dir: str,
                 lat: float = SITE_LATITUDE,
                 lon: float = SITE_LONGITUDE,
                 altitude: float = SITE_ALTITUDE):
        self.model_dir = Path(model_dir)
        self.lat = lat
        self.lon = lon
        self.altitude = altitude

        self.model = None
        self.scaler = None
        self.config = None
        self.feature_columns: List[str] = []
        self.model_version: str = '?'
        self.default_panel_calib: float = 0.38   # v8 OOD fallback
        self._loaded = False

        if not TF_AVAILABLE:
            logger.warning("TensorFlow 未安裝，AnfisInference 無法工作")
            return
        if not PVLIB_AVAILABLE:
            logger.warning("pvlib 未安裝，AnfisInference 無法工作")
            return

        self._load()

    def _load(self):
        """自動偵測 v5/v6/v8 並載入模型"""
        # 尋找 .keras 模型檔（依序嘗試）
        candidates = ['anfis_v8.keras', 'anfis_v6.keras', 'anfis_v5.keras',
                      'best_anfis.keras']
        keras_path = None
        for name in candidates:
            p = self.model_dir / name
            if p.exists():
                keras_path = p
                break
        if keras_path is None:
            logger.error("找不到 ANFIS 模型檔於 %s（已嘗試 %s）",
                         self.model_dir, candidates)
            return

        # 對應的 scaler 與 config
        scaler_candidates = ['scaler_X_v8.save', 'scaler_X_v6.save',
                             'scaler_X_v5.save']
        config_candidates = ['model_config_v8.json', 'model_config_v6.json',
                             'model_config_v5.json']
        scaler_path = next((self.model_dir / n for n in scaler_candidates
                            if (self.model_dir / n).exists()), None)
        config_path = next((self.model_dir / n for n in config_candidates
                            if (self.model_dir / n).exists()), None)
        if scaler_path is None or config_path is None:
            logger.error("找不到 scaler 或 config 配對檔")
            return

        try:
            self.model = tf.keras.models.load_model(str(keras_path),
                                                     compile=False)
            self.scaler = joblib.load(str(scaler_path))
            with open(config_path, encoding='utf-8') as f:
                self.config = json.load(f)
            self.feature_columns = self.config.get('feature_columns', [])
            self.model_version = self.config.get('model_version', '?')
            self._loaded = True
            logger.info("AnfisInference 載入 %s（%d 維特徵：%s）",
                        keras_path.name, len(self.feature_columns),
                        ', '.join(self.feature_columns))
        except Exception as e:
            logger.exception("ANFIS 模型載入失敗: %s", e)

    # ─────────────────────────────────────────────────────────
    # POA 計算（pvlib）
    # ─────────────────────────────────────────────────────────
    def compute_poa(self, timestamp: datetime, ghi_wm2: float,
                    candidate_angles: List[Tuple[float, float]]) -> np.ndarray:
        """
        對候選角度集合計算 POA（W/m²）
        回傳 shape (N,) ndarray，順序與 candidate_angles 一致
        """
        if not PVLIB_AVAILABLE:
            raise RuntimeError("pvlib 未安裝")

        # 包裝 timestamp（pvlib 需要 DatetimeIndex）
        ts = pd.DatetimeIndex([pd.to_datetime(timestamp)])
        if ts.tz is None:
            ts = ts.tz_localize('Asia/Taipei', ambiguous='NaT',
                                 nonexistent='shift_forward')

        solpos = pvlib.solarposition.get_solarposition(
            ts, self.lat, self.lon, altitude=self.altitude
        )
        zenith  = float(np.asarray(solpos['apparent_zenith'])[0])
        sun_azi = float(np.asarray(solpos['azimuth'])[0])

        # Erbs decomposition
        ghi_arr = np.array([max(ghi_wm2, 0.0)], dtype=float)
        zenith_arr = np.array([zenith])
        dayofyear = np.array([ts.dayofyear[0]])
        erbs = pvlib.irradiance.erbs(ghi_arr, zenith_arr, dayofyear)
        dni = float(np.asarray(erbs['dni'])[0])
        dhi = float(np.asarray(erbs['dhi'])[0])
        dni_extra = float(np.asarray(
            pvlib.irradiance.get_extra_radiation(dayofyear))[0])

        # 對每個候選角度算 POA
        poa_arr = np.zeros(len(candidate_angles), dtype=float)
        for i, (tilt, azi) in enumerate(candidate_angles):
            poa = pvlib.irradiance.get_total_irradiance(
                surface_tilt=float(tilt),
                surface_azimuth=float(azi),
                solar_zenith=zenith,
                solar_azimuth=sun_azi,
                dni=dni, ghi=ghi_wm2, dhi=dhi,
                dni_extra=dni_extra,
                model='haydavies',
            )
            v = poa['poa_global']
            v = float(v) if not hasattr(v, '__iter__') else float(np.asarray(v).item())
            poa_arr[i] = max(v, 0.0)
        return poa_arr

    # ─────────────────────────────────────────────────────────
    # 特徵向量構造
    # ─────────────────────────────────────────────────────────
    def _build_features(self, timestamp: datetime,
                         tilt: float, azi: float,
                         illumination_wm2: float,
                         panel_calib: Optional[float] = None) -> np.ndarray:
        """根據 model_version 構造特徵向量（與訓練時一致）"""
        hour_dec = (timestamp.hour + timestamp.minute / 60.0
                    + timestamp.second / 3600.0)
        doy      = timestamp.timetuple().tm_yday

        feat = {}
        feat['hour_sin']    = math.sin(2 * math.pi * hour_dec / 24)
        feat['hour_cos']    = math.cos(2 * math.pi * hour_dec / 24)
        feat['day_sin']     = math.sin(2 * math.pi * doy / 365)
        feat['day_cos']     = math.cos(2 * math.pi * doy / 365)
        feat['tilt_sin']    = math.sin(math.radians(tilt))
        feat['tilt_cos']    = math.cos(math.radians(tilt))
        feat['azimuth_sin'] = math.sin(math.radians(azi))
        feat['azimuth_cos'] = math.cos(math.radians(azi))
        feat['clearness']   = max(0.0, min(1.5, illumination_wm2 / 1000.0))

        # v6 特徵
        if 'cos_incidence' in self.feature_columns:
            # 需要 solar zenith / azimuth；輕量算法
            ts = pd.DatetimeIndex([pd.to_datetime(timestamp)])
            if ts.tz is None:
                ts = ts.tz_localize('Asia/Taipei', ambiguous='NaT',
                                     nonexistent='shift_forward')
            solpos = pvlib.solarposition.get_solarposition(
                ts, self.lat, self.lon, altitude=self.altitude)
            z  = math.radians(float(np.asarray(solpos['apparent_zenith'])[0]))
            sa = math.radians(float(np.asarray(solpos['azimuth'])[0]))
            t  = math.radians(tilt)
            pa = math.radians(azi)
            cos_inc = (math.cos(z) * math.cos(t) +
                       math.sin(z) * math.sin(t) * math.cos(sa - pa))
            feat['cos_incidence']   = max(-1.0, min(1.0, cos_inc))
            feat['sin_solar_elev']  = math.cos(z)

        # v8 特徵
        if 'panel_calib' in self.feature_columns:
            feat['panel_calib'] = panel_calib if panel_calib is not None \
                                  else self.default_panel_calib

        # 依 feature_columns 順序排成 vector
        vec = np.array([feat[col] for col in self.feature_columns],
                        dtype='float32').reshape(1, -1)
        return vec

    # ─────────────────────────────────────────────────────────
    # 主 API：預測最佳角度
    # ─────────────────────────────────────────────────────────
    def predict_best_angle(self,
                            timestamp: datetime,
                            illumination_wm2: float,
                            candidate_angles: List[Tuple[float, float]],
                            panel_calib: Optional[float] = None
                            ) -> InferenceResult:
        """
        對候選角度集合執行推論，回傳最佳角度與預期功率。

        Parameters
        ----------
        timestamp : 當前時刻
        illumination_wm2 : 當前 GHI 照度（W/m²，從 LDR 校正或外部 GHI 計）
        candidate_angles : [(tilt, azi), ...] 候選角度集合
        panel_calib : v8 用；若 None 則用 default

        Returns
        -------
        InferenceResult
        """
        if not self._loaded:
            raise RuntimeError("ANFIS 模型未載入，無法推論")

        # Step 1: 算每個候選角度的 POA
        poa_arr = self.compute_poa(timestamp, illumination_wm2,
                                    candidate_angles)

        # Step 2: 構造每個角度的特徵向量並 stack
        X_list = []
        for tilt, azi in candidate_angles:
            x = self._build_features(timestamp, tilt, azi,
                                      illumination_wm2, panel_calib)
            X_list.append(x)
        X = np.concatenate(X_list, axis=0)
        X_scaled = self.scaler.transform(X)

        # Step 3: ANFIS 推論 PR
        pr_pred = self.model.predict(X_scaled, verbose=0).flatten()
        pr_pred = np.clip(pr_pred, 0.0, None)

        # Step 4: 回推實際功率
        # expected_power = PR × POA × area × eff
        power_pred = pr_pred * poa_arr * PANEL_AREA_M2 * PANEL_EFF_STC

        # Step 5: 找最佳
        best_idx = int(np.argmax(power_pred))
        best_angle = candidate_angles[best_idx]
        best_power = float(power_pred[best_idx])
        best_pr    = float(pr_pred[best_idx])
        best_poa   = float(poa_arr[best_idx])

        all_predictions = {tuple(angle): float(p)
                           for angle, p in zip(candidate_angles, power_pred)}

        return InferenceResult(
            best_angle=best_angle,
            predicted_power=best_power,
            predicted_pr=best_pr,
            poa_at_best=best_poa,
            all_predictions=all_predictions,
        )

    # ─────────────────────────────────────────────────────────
    # 工具：產生雙軸 grid 候選角度
    # ─────────────────────────────────────────────────────────
    @staticmethod
    def make_grid(tilt_min: float = 10.0, tilt_max: float = 40.0,
                  tilt_step: float = 5.0,
                  azi_min: float = 145.0, azi_max: float = 215.0,
                  azi_step: float = 10.0) -> List[Tuple[float, float]]:
        """產生雙軸 grid 候選角度集合"""
        tilts = np.arange(tilt_min, tilt_max + 1e-9, tilt_step)
        azis  = np.arange(azi_min,  azi_max  + 1e-9, azi_step)
        return [(float(t), float(a)) for t in tilts for a in azis]


# ════════════════════════════════════════════════════════════════
# CLI 測試
# ════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='AnfisInference 模組單元測試')
    parser.add_argument('--model-dir', required=True,
                        help='模型 run 資料夾路徑')
    parser.add_argument('--illum', type=float, default=850.0,
                        help='測試照度 W/m²')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

    inf = AnfisInference(model_dir=args.model_dir)
    if not inf._loaded:
        print("❌ 模型載入失敗")
        exit(1)

    print(f"模型版本: {inf.model_version}")
    print(f"特徵: {inf.feature_columns}")

    candidates = AnfisInference.make_grid()
    print(f"\n候選角度數: {len(candidates)}")

    now = datetime.now()
    result = inf.predict_best_angle(
        timestamp=now,
        illumination_wm2=args.illum,
        candidate_angles=candidates,
    )

    print(f"\n=== 推論結果 ===")
    print(f"  最佳角度: tilt={result.best_angle[0]:.1f}° azi={result.best_angle[1]:.1f}°")
    print(f"  預測功率: {result.predicted_power:.2f} W")
    print(f"  預測 PR_norm: {result.predicted_pr:.4f}")
    print(f"  最佳角度 POA: {result.poa_at_best:.1f} W/m²")
    print(f"\n  Top 5 候選:")
    top5 = sorted(result.all_predictions.items(), key=lambda x: -x[1])[:5]
    for (t, a), p in top5:
        print(f"    tilt={t:.0f}° azi={a:.0f}° → {p:.2f} W")
