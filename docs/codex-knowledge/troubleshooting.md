# Troubleshooting

## Docker Desktop: virtualization support not detected

現象：Docker Desktop 顯示 virtualization support not detected。

處理：

- 到 BIOS/UEFI 啟用 CPU virtualization。
- Windows 功能確認 WSL2 / Virtual Machine Platform / Hyper-V 相關設定。
- 重開機後再開 Docker Desktop。

## Tailscale 容器重建後一直 Restarting

已遇過原因：既有 Tailscale state 有非預設設定，重跑 `tailscale up` 時如果沒有列出所有非預設 flags 會失敗。

目前 compose 已固定：

```text
TS_EXTRA_ARGS=--reset --accept-dns=false --advertise-tags=tag:container
```

檢查：

```powershell
docker logs solar_tailscale --tail 100
docker exec solar_tailscale tailscale status
docker exec solar_tailscale tailscale serve status
```

## Tailscale URL 打到學長舊機

`solar-dashboard.tail7c1eb9.ts.net` 推定是舊機。新機平行運轉用：

```text
solar-dashboard-zhiyu.tail7c1eb9.ts.net
```

如果改 hostname，需要同步改：

- `docker-compose-dev.yml` 的 `tailscale.hostname`
- `.env.dev` 的 `DJANGO_ALLOWED_HOSTS`
- `.env.dev` 的 `CSRF_TRUSTED_ORIGINS`

然後重建 backend 與 tailscale。

## Fiddler 只看到 CONNECT，看不到 token

代表 HTTPS decrypt 沒成功，或該流量沒有被 Fiddler 解密。

已知替代方式：七云物聯 Windows app cache 可能有 token：

```text
C:\Users\USER\AppData\Roaming\iot7.cn\七云物联\shared_preferences.json
```

不要把 token 貼進文件。更新 `.env.dev` 後重建 backend 並測 `/api/z3a/status/`。

## MySQL dump 不是有效 SQL

舊版 `solar_db_dump.sql` 曾經只有 `mysqldump` usage 訊息，不能匯入。

有效 dump 應該開頭類似：

```sql
-- MySQL dump 10.13
CREATE DATABASE ... `solar_tracking_db`;
USE `solar_tracking_db`;
DROP TABLE IF EXISTS ...
CREATE TABLE ...
INSERT INTO ...
```

匯入前先 `Get-Content -TotalCount 40` 和 `Select-String` 檢查。

## PowerShell + docker exec + mysql 引號問題

複雜 SQL 不要硬塞在 `mysql -e "..."`，容易被 PowerShell、docker、sh 多層引號吃掉。優先使用 pipeline：

```powershell
$pwd = (docker exec solar_db printenv MYSQL_ROOT_PASSWORD).Trim()
$sql = @'
SHOW DATABASES;
SHOW TABLES FROM solar_tracking_db;
'@
$sql | docker exec -i solar_db mysql -uroot "-p$pwd"
```
