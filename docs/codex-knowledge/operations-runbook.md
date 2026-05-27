# Operations Runbook

## 啟動與基本檢查

```powershell
cd C:\projects\solar-tracking-dashboard
docker compose -f docker-compose-dev.yml up -d
docker compose -f docker-compose-dev.yml ps
```

本機 dashboard：

```powershell
Invoke-WebRequest -UseBasicParsing http://localhost:8000/dashboard/
Invoke-WebRequest -UseBasicParsing http://localhost:8000/api/z3a/status/
```

Tailscale/Funnel：

```powershell
docker exec solar_tailscale tailscale status
docker exec solar_tailscale tailscale serve status
Invoke-WebRequest -UseBasicParsing https://solar-dashboard-zhiyu.tail7c1eb9.ts.net/dashboard/
```

## `.env.dev` 更新後

`docker compose restart backend` 不會保證重新載入 env file。更新 `.env.dev` 後用：

```powershell
cd C:\projects\solar-tracking-dashboard
docker compose -f docker-compose-dev.yml up -d --force-recreate --no-deps backend
```

驗證：

```powershell
Invoke-WebRequest -UseBasicParsing http://localhost:8000/api/z3a/status/
```

## Z3A token

優先使用 App cache 自動更新工具，不走 Fiddler：

```powershell
cd C:\projects\solar-tracking-dashboard
powershell.exe -ExecutionPolicy Bypass -File .\scripts\update_z3a_token_from_app_cache.ps1 -Apply -RecreateBackend -CheckStatus
```

詳細教學見 `docs/codex-knowledge/z3a-token-app-cache.md` 與根目錄 `Z3A_TOKEN_SOP.md`。

目前程式會檢查 token 狀態，但 Z3A 登入端有 captcha，不能假設能全自動登入重抓 token。

有效 token 來源優先順序：

1. 七云物聯 Windows app cache：

```text
C:\Users\USER\AppData\Roaming\iot7.cn\七云物联\shared_preferences.json
```

2. Fiddler HTTPS decrypt capture。

更新方式：

1. 從 app cache 或 Fiddler 找新 token。
2. 更新 `.env.dev` 內 token 欄位。
3. 重建 backend。
4. 呼叫 `/api/z3a/status/` 確認 `token_valid=true`。

不要把 token 值寫進文件或 git。

## 每週資料收集

手動跑一次：

```powershell
cd C:\projects\solar-tracking-dashboard
powershell.exe -ExecutionPolicy Bypass -NoProfile -File .\solar_weekly_run.ps1
```

檢查 log：

```powershell
Get-Content C:\projects\solar-tracking-dashboard\logs\latest_report.txt
```

排程檢查：

```powershell
Get-ScheduledTask -TaskName SolarWeeklyMaintenance
Get-ScheduledTaskInfo -TaskName SolarWeeklyMaintenance
```

## MySQL dump 匯入

匯入前一定先備份目前容器資料庫。

```powershell
cd C:\projects\solar-tracking-dashboard
$pwd = (docker exec solar_db printenv MYSQL_ROOT_PASSWORD).Trim()
$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$backup = "C:\solar-data\backups\mysql_before_import_$ts.sql"
docker exec -e MYSQL_PWD=$pwd solar_db mysqldump -uroot --databases solar_tracking_db | Set-Content -Path $backup -Encoding UTF8
```

匯入 dump：

```powershell
$dump = "C:\solar-data\migration-kit\solar_migration_包_20260521\solar_db_dump.sql"
docker cp $dump solar_db:/tmp/solar_db_dump.sql
docker exec -e MYSQL_PWD=$pwd solar_db sh -lc 'mysql -uroot < /tmp/solar_db_dump.sql'
docker exec solar_db rm -f /tmp/solar_db_dump.sql
```

驗證筆數：

```powershell
$sql = @'
SELECT 'dashboard_fixedpaneldata' AS table_name, COUNT(*) AS exact_count FROM dashboard_fixedpaneldata
UNION ALL SELECT 'dashboard_powerrecord', COUNT(*) FROM dashboard_powerrecord
UNION ALL SELECT 'dashboard_systemgroup', COUNT(*) FROM dashboard_systemgroup
UNION ALL SELECT 'auth_user', COUNT(*) FROM auth_user;
'@
$sql | docker exec -i solar_db mysql -uroot "-p$pwd" solar_tracking_db
```
