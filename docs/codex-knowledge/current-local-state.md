# Current Local State

最後更新：2026-05-26 Asia/Taipei。

## 固定位置

- Git 專案：`C:\projects\solar-tracking-dashboard`
- 移植包備份：`C:\solar-data\migration-kit`
- 大型 CSV：`C:\solar-data\csv`
- 備份區：`C:\solar-data\backups`
- 專案內 `data` 是 junction，指到 `C:\solar-data\csv`

## 目前服務

- Local dashboard：`http://localhost:8000/dashboard/`
- 平行運轉 Tailscale/Funnel dashboard：`https://solar-dashboard-zhiyu.tail7c1eb9.ts.net/dashboard/`
- 舊節點：`https://solar-dashboard.tail7c1eb9.ts.net/`，推定是學長電腦，平行運轉期間不要動。

Docker compose 服務：

- `solar_backend`
- `solar_db`
- `solar_tailscale`

常用檢查：

```powershell
cd C:\projects\solar-tracking-dashboard
docker compose -f docker-compose-dev.yml ps
Invoke-WebRequest -UseBasicParsing http://localhost:8000/api/z3a/status/
docker exec solar_tailscale tailscale serve status
```

## 關鍵資料

- `.env.dev` 位於專案根目錄，含 token 與密碼，不進 git。
- 2026-05-27 已用 App cache 自動工具更新 Z3A token：
  - Access token 到期：2026-06-06 10:55:46 Asia/Taipei
  - Refresh token 到期：2026-09-04 10:55:46 Asia/Taipei
- `Z3A_CSV_PATH` 應指向：

```text
C:\solar-data\csv\combined_solar_data_20250301_20260406_processed.csv
```

- SQLite：`C:\projects\solar-tracking-dashboard\solar_angle_data.db`
- SQLite 已知表格筆數：
  - `processed_solar_data`: 17,732
  - `solar_panel_data`: 17,732
  - `averaged_solar_data`: 0

## 目前已匯入的 MySQL dump

2026-05-26 匯入更新後的 dump：

```text
C:\solar-data\migration-kit\solar_migration_包_20260521\solar_db_dump.sql
```

匯入前備份：

```text
C:\solar-data\backups\mysql_before_import_20260526_112847.sql
```

匯入後已知表格筆數：

- `dashboard_fixedpaneldata`: 599,453
- `dashboard_powerrecord`: 167,854
- `dashboard_systemgroup`: 7
- `auth_user`: 2

## Windows 排程

排程名稱：`SolarWeeklyMaintenance`

- 工作目錄：`C:\projects\solar-tracking-dashboard`
- 指令：`powershell.exe -ExecutionPolicy Bypass -NoProfile -File "C:\projects\solar-tracking-dashboard\solar_weekly_run.ps1"`
- 週期：每週一 02:00
- 2026-05-26 檢查狀態：Ready
- 最近成功測試結果：`LastTaskResult=0`
