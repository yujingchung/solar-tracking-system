# Solar Tracking System — 太陽能追日系統

ANFIS-based intelligent dual-axis solar tracking system for master's thesis research.
**Site**: Xianfeng (Jintugong Temple), Tainan | **Researcher**: Chung Yu-Ching

---

## Project Overview

Two-group experiment comparing ANFIS intelligent tracking vs. traditional LDR differential tracking:

| Group | Method | System ID | Controller |
|-------|--------|-----------|------------|
| 實驗組 I & II | ANFIS intelligent tracking | 1, 2 | `anfis_controller.py` |
| 對照組 I & II | Traditional LDR differential | 3, 4 | `traditional_controller.py` |

28 fixed-angle reference panels (tilt 10°/15°/20°/30° × azimuth 160°/180°/200°) + 4 dual-axis tracking panels.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Raspberry Pi (×4)                                      │
│  ├─ MCP3008: 4-channel LDR (E/W/S/N)                  │
│  ├─ INA3221 I2C: actuator power (CH1) + Pi power (CH2) │
│  ├─ RS485→USB: MPPT solar panel V/I                    │
│  └─ Dual-axis linear actuator (Hall sensor feedback)   │
└────────────────┬────────────────────────────────────────┘
                 │ HTTPS (Tailscale Funnel)
┌────────────────▼────────────────────────────────────────┐
│  Django Backend (Docker)                                │
│  ├─ REST API: /api/power-records/                      │
│  ├─ Fixed panel CSV API (49 MB, pandas in-memory)      │
│  └─ Z3A IoT cloud API proxy                            │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│  dashboard.html (single-file frontend)                  │
│  ├─ 系統總覽: realtime power per group                  │
│  ├─ 功率曲線: time-series charts                       │
│  ├─ 固定式面板發電分析: CSV query + illumination chart  │
│  └─ Z3A 採集: live V/I/P from IoT cloud               │
└─────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
solar-tracking-dashboard/
├── backend/
│   ├── dashboard/
│   │   ├── models.py          # SystemGroup, PowerRecord
│   │   ├── views.py           # REST API viewsets
│   │   ├── serializers.py     # RealTimeDataSerializer
│   │   ├── fixed_panel_api.py # Fixed panel CSV query API
│   │   └── z3a_api.py         # Z3A IoT cloud API proxy
│   ├── static/dashboard.html  # Single-file frontend (~1500 lines)
│   └── requirements.txt
├── data/
│   └── combined_solar_data_20250301_20260406_processed.csv  # 49 MB main dataset
├── algorithms/
│   ├── solar_anfis_model_v2.py   # ANFIS model (saves as .keras, not .h5)
│   ├── train_pipeline.py         # One-click training launcher
│   ├── datasets/                 # Preprocessed datasets (dsXX_YYYYMMDD_desc/)
│   ├── runs/                     # Training outputs (runXX_dsXX_desc/)
│   ├── datapreprocessor/
│   │   └── data preprocessor.py  # SimpleSolarPreprocessor
│   └── coordinate_conversion/    # (β,φ) ⇄ (γ,ζ) conversion tools
├── fixed_data_process_visualization/  # 6-step fixed panel data pipeline
│   ├── solar_data_pipeline.py    # Tkinter GUI entry point
│   └── 使用手冊.md
├── raspberry-pi/
│   ├── src/controllers/
│   │   ├── anfis_controller.py        # Experiment group controller
│   │   └── traditional_controller.py  # Control group controller
│   └── deploy/solar_tracking/         # Ready-to-deploy folders
│       ├── 實驗組1/   (system_id=1)
│       ├── 實驗組2/   (system_id=2)
│       ├── 對照組1/   (system_id=3)
│       └── 對照組2/   (system_id=4)
├── algorithms/flowcharts/         # Experiment/control flowchart PDFs
├── z3a_collect.py                 # Z3A historical data fetch + CSV merge
├── docker-compose-dev.yml
└── .env.dev                       # Secrets — NOT in git
```

---

## Quick Start

### Docker (run from project root)

```bash
docker-compose -f docker-compose-dev.yml up -d       # Start
docker-compose -f docker-compose-dev.yml down         # Stop
docker-compose -f docker-compose-dev.yml up -d --build  # Rebuild
```

| URL | Description |
|-----|-------------|
| `http://localhost:8000/dashboard/` | Local dashboard |
| `https://solar-dashboard.tail7c1eb9.ts.net/dashboard/` | Public (Tailscale) |

> ⚠️ Close **Fiddler** before starting Docker — its HTTPS interception breaks Tailscale container TLS.

### Debug

```bash
docker logs solar_backend --tail 50
docker exec -it solar_backend bash
```

---

## Raspberry Pi Deployment

Four independent Pis, each running one controller from `raspberry-pi/deploy/solar_tracking/`.

### Per-Pi hardware

| Component | Role |
|-----------|------|
| MCP3008 (SPI) | 4-channel LDR: CH0=East, CH1=West, CH2=South, CH3=North |
| INA3221 (I2C 0x40) | CH1=actuator power (both), CH2=Pi power |
| RS485→USB | MPPT controller: solar panel V/I |
| Dual-axis actuator | Hall sensor feedback for closed-loop positioning |

### Deploy steps

```bash
# 1. Copy folder to Pi
scp -r 實驗組1/ pi@<PI_IP>:/home/pi/solar_tracking/

# 2. Install dependencies
pip3 install -r requirements.txt

# 3. (Experiment group only) Place model files in models/
#    anfis_with_illumination.keras
#    scaler_X_with_illumination.save
#    model_config_with_illumination.json

# 4. Set simulation_mode = False in CONFIG when hardware is ready

# 5. Test run
bash start.sh

# 6. Enable auto-start on boot
sudo cp solar_tracking.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable solar_tracking
sudo systemctl start solar_tracking
```

### Coordinate system

- **Tip-tilt**: γ = N-S (±30°, +North/−South), ζ = E-W (±30°, +East/−West)
- **Azimuth-elevation**: β (tilt 0–41.4°), φ (azimuth, full 360°)
- Conversion: `tiptilt_to_azalt(γ, ζ) → (β, φ)` in `anfis_controller.py`

---

## ANFIS Training Pipeline

```bash
cd algorithms/
python train_pipeline.py                                  # Full pipeline
python train_pipeline.py --skip-preprocess                # Train only (latest dataset)
python train_pipeline.py --skip-preprocess --dataset ds02_20260506_含照度
```

### Model specs

- **Input**: 9 features — `hour_sin/cos`, `day_sin/cos`, `tilt_sin/cos`, `azimuth_sin/cos`, `illumination`
- **Architecture**: Gaussian MF layer (7 MFs/input) → Dense(128→64→32→16→1) + BatchNorm + Dropout
- **Save format**: `.keras` (not `.h5` — h5py fails on Windows paths with Chinese characters)
- **Output dir**: `algorithms/runs/runXX_dsXX_desc/`

### Current results (run04, ds02, with illumination)

| Metric | Value |
|--------|-------|
| R² (overall) | 0.844 |
| RMSE | 32.43 W |
| MAE | 20.98 W |

Per-angle-range R² all negative → model learns time→power mapping, not angle differentiation.
**Next step**: Add `theoretical_poa`, `solar_elevation` as features to improve angle discrimination.

---

## API Endpoints

**Base URL**: `/api/`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/power-records/` | GET/POST | PowerRecord CRUD — Pi upload target |
| `/api/realtime-data/` | GET | Latest data per system |
| `/api/systems/` | GET/POST | SystemGroup CRUD |
| `/api/fixed-panels/day-curve/` | GET | Per-minute fixed panel curve |
| `/api/fixed-panels/panel-trend/` | GET | Long-term panel trend |
| `/api/z3a/history/` | GET | Z3A device history |
| `/api/z3a/devices/` | GET | List Z3A devices |

**POST `/api/power-records/` required fields**: `system_id`, `voltage`, `current`

---

## Main Dataset

`data/combined_solar_data_20250301_20260406_processed.csv` (49 MB)
- **Period**: 2025-03-01 to 2026-04-06 | **Interval**: 10 min | **Timezone**: Asia/Taipei
- **Key columns**: `timestamp`, `tilt_angle`, `azimuth_angle`, `panel_id`, `voltage_V`, `current_A`, `power_W`, `solar_elevation`, `theoretical_poa`, `ghi`, `illumination`

---

## Z3A IoT Device Map (selected)

| DeviceId | Panel | Tilt | Azimuth |
|----------|-------|------|---------|
| Z3A0412111 | Tracking_2_25_Top | — | Experiment A upper |
| Z3A0512124 | Tracking_2_25_Bot | — | Experiment A lower |
| Z3A0412103 | Tracking_1_20_Top | — | Control B upper |
| Z3A0312076 | Tracking_1_20_Bot | — | Control B lower |

Full device map in `CLAUDE.md` §6.

---

## Open Issues

| Issue | Priority |
|-------|----------|
| MPPT RS485 protocol unknown — `read_mppt_power()` is a stub | High |
| GPIO actuator wiring not confirmed — `_drive_ew/_drive_ns` are stubs | High |
| Hall sensor stroke-angle lookup table not built | High |
| LDR calibration coefficients (4 sensors, individual) not measured | High |
| ANFIS per-range R² all negative — needs feature engineering improvement | Medium |
| Z3A token expires 2026-05-09 — re-login in app, update `.env.dev` | Medium |
| Z3A historical backfill (2026-04-07 onward) not merged | Low |

---

## Environment Variables (`.env.dev`)

| Variable | Description |
|----------|-------------|
| `Z3A_TOKEN` | Bearer token, **expires 2026-05-09** |
| `TS_AUTHKEY` | Tailscale Auth Key (Reusable, No Expiry) |
| `SQL_ROOT_PASSWORD` / `SQL_USER` / `SQL_PASSWORD` | MySQL credentials |
| `DJANGO_ALLOWED_HOSTS` | Includes `solar-dashboard.tail7c1eb9.ts.net` |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v0.4 | 2026-05-09 | ANFIS/traditional controllers fully rewritten; 4 deploy folders; INA3221 + MPPT stubs; payload aligned to API serializer; CLAUDE.md rewritten in English |
| v0.3 | 2026-05 | ANFIS training pipeline; illumination data integration; fixed panel 6-step pipeline; Z3A data collection |
| v0.2 | 2025-09 | Main controller architecture; unified config system |
| v0.1 | 2025-03 | Initial Django backend; basic dashboard |

---

## License

MIT License
