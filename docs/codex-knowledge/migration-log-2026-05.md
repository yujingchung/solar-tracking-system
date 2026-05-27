# Migration Log 2026-05

## 目標

使用者正在從學長電腦接手收資料與運轉。策略是先在新機平行運轉，不刪除舊節點，不立即接管舊 URL。

正式本機位置：

- repo：`C:\projects\solar-tracking-dashboard`
- data：`C:\solar-data`

## 已完成

- Clone `https://github.com/yujingchung/solar-tracking-system.git` 到 `C:\projects\solar-tracking-dashboard`。
- 從 Google Drive 移植包還原 `.env.dev`、CSV、SQLite DB。
- 主 CSV 放在 `C:\solar-data\csv`，並讓 `Z3A_CSV_PATH` 指向該位置。
- 專案 `data` 建為 junction 指向 `C:\solar-data\csv`。
- 設定使用者環境變數 `PYTHONUTF8=1`。
- 安裝 Docker Desktop 後，Docker / Compose 可用。
- 啟動 Docker compose：backend、MySQL、Tailscale。
- 註冊 Windows Task Scheduler：`SolarWeeklyMaintenance`。
- 取得新的 Z3A token 並確認 backend token status OK。
- 匯入更新後的 MySQL dump。
- 建立平行 Tailscale 節點：`solar-dashboard-zhiyu.tail7c1eb9.ts.net`。

## 重要程式修正

- `backend/Dockerfile`
  - 修正 build 穩定性與必要套件。
- `backend/docker-entrypoint.sh`
  - 修正 bash/quote/encoding 問題，讓容器能穩定等待 MySQL 並啟動。
- `docker-compose-dev.yml`
  - MySQL env 改用 `.env.dev` 預設。
  - Tailscale hostname 改為 `solar-dashboard-zhiyu`。
  - Tailscale extra args 加入 `--reset --accept-dns=false --advertise-tags=tag:container`，避免重建容器時因非預設設定而 crash loop。
- `z3a_collect.py`
  - 在 `main()` 載入 `.env.dev`，並讓 `Z3A_CSV_PATH` 生效。
- `backend/dashboard/z3a_api.py`
  - 修正自動登入嘗試使用錯誤 endpoint 的問題；但因 captcha，不能保證全自動取得 token。

## 目前平行運轉結論

- 新機 URL：`https://solar-dashboard-zhiyu.tail7c1eb9.ts.net/dashboard/`
- 舊機 URL：`https://solar-dashboard.tail7c1eb9.ts.net/`
- 平行運轉期間不要刪除舊機節點。
- 若未來要正式接管舊 URL，再另外規劃 Tailscale 節點轉移，不要在沒有確認前直接刪除。
