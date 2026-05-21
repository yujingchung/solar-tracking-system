# 太陽能追蹤系統 — 移植包（Migration Kit）

> 目標：把整個專案從舊 Windows 電腦完整搬到**新 Windows 電腦**並順利運作。
> 建立日期：2026-05-21　|　對應版本：dashboard v2.4
> 這個資料夾是「照著做就會完成」的完整流程；不需要再翻其他文件。

---

## 📦 這個資料夾裡有什麼

| 檔案 | 用途 | 在哪台機器用 |
|------|------|--------------|
| `README.md`（本檔） | 完整移植主流程，從頭到尾照著做 | 兩台都看 |
| `requirements-local.txt` | 本機（非 Docker）Python 腳本的套件清單 | 新機安裝用 |
| `1_在舊機執行_打包.ps1` | 自動把 git 以外的必要檔案打包成一個資料夾 | **舊機** |
| `2_在新機執行_環境檢查.ps1` | 檢查新機軟體、環境變數、檔案是否就緒 | **新機** |

---

## 🗺️ 移植總流程（九步）

```
舊機                              新機
─────                            ─────
[步驟1] 提交未存的修改 (git push)
[步驟2] 跑 1_在舊機執行_打包.ps1
        → 產生「移植檔包」資料夾    ──搬運──▶  [步驟3] 安裝前置軟體
                                              [步驟4] git clone 程式碼
                                              [步驟5] 還原檔包(.env/CSV/db/MySQL)
                                              [步驟6] 跑 2_在新機執行_環境檢查.ps1
                                              [步驟7] 啟動 Docker
                                              [步驟8] 重抓 Z3A token / 重設排程
                                              [步驟9] 跑驗證清單
```

---

## 為什麼不能只靠 git clone？

GitHub repo（`https://github.com/yujingchung/solar-tracking-system.git`）**只含程式碼**。下列東西被 `.gitignore` 擋掉，必須手動搬，否則新機跑不起來或資料對不上：

| 項目 | 路徑 | 大小 | 怎麼搬 |
|------|------|------|--------|
| 機密設定 | `.env.dev` | 2 KB | 打包腳本會帶 |
| 主資料集 | `data/...processed.csv` | ~150 MB | 打包腳本會帶 |
| SQLite 角度庫 | `solar_angle_data.db` | 12.7 MB | 打包腳本會帶 |
| MySQL 即時資料 | `mysql/` | ~672 MB | 打包腳本會做 mysqldump |

> `data/*.bak.*.csv` 那一堆每週自動產生的備份（共約 2 GB）**不用搬**，打包腳本預設略過。

---

# 舊機作業

## 步驟 1 — 先提交未儲存的修改

舊機目前有一批還沒 commit 的改動（`CLAUDE.md`、preprocessor、多個 ANFIS run 設定等）。先把它們推上 GitHub，新機 clone 才會拿到最新版：

```powershell
cd D:\宇靖\solar-tracking-dashboard
git add -A
git commit -m "migration: snapshot before moving machine"
git push
```

> 如果你不想用 git、想直接整夾複製，也可以跳過 git，改用「整個 `solar-tracking-dashboard` 資料夾壓縮搬過去」的土法。但走 git + 打包腳本比較乾淨、檔案小很多。

## 步驟 2 — 打包 git 以外的必要檔案

在舊機用 PowerShell 執行：

```powershell
cd D:\宇靖\solar-tracking-dashboard\移植包_MIGRATION_KIT
powershell -ExecutionPolicy Bypass -File .\1_在舊機執行_打包.ps1
```

它會在桌面（或你指定的位置）產生一個 `solar_migration_包_YYYYMMDD` 資料夾，內含：
`.env.dev`、主資料集 CSV、`solar_angle_data.db`、`solar_db_dump.sql`（MySQL 匯出）。

把這個資料夾用隨身碟或雲端硬碟搬到新機。

---

# 新機作業

## 步驟 3 — 安裝前置軟體

依序裝好（裝完各自確認指令能跑）：

1. **Docker Desktop for Windows**（含 WSL2）— 跑 MySQL + Django + Tailscale 三容器的核心。確認 `docker --version`、`docker-compose --version`。
2. **Git for Windows** — `git clone` 用。
3. **Python 3.12** — 本機腳本用；安裝勾「Add Python to PATH」。確認 `python --version`。
4. **PowerShell**（Windows 內建即可）。
5. **Fiddler Classic** — Z3A token 抓取用（步驟 8）。
6. **VS Code**（選用）。

> 企業 / 防毒環境若有 SSL 攔截，所有 `pip install` 都要加：
> `--trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org`

## 步驟 4 — 取得程式碼

```powershell
cd D:\宇靖    # 或你想放專案的位置
git clone https://github.com/yujingchung/solar-tracking-system.git solar-tracking-dashboard
```

> repo 名是 `solar-tracking-system`，本機資料夾建議仍叫 `solar-tracking-dashboard`，與既有腳本路徑一致。

## 步驟 5 — 還原「移植檔包」

把步驟 2 搬過來的 `solar_migration_包_YYYYMMDD` 內的檔案放回新機專案：

1. `.env.dev` → 專案根目錄 `D:\宇靖\solar-tracking-dashboard\.env.dev`
2. 主資料集 CSV → `data\` 資料夾內
3. `solar_angle_data.db` → 專案根目錄
4. `solar_db_dump.sql` → 暫放專案根目錄（步驟 7 啟動 DB 後再匯入）

**還原後立刻改 `.env.dev` 這兩個 key：**

| Key | 改什麼 |
|-----|--------|
| `Z3A_CSV_PATH` | 改成新機的 CSV 完整路徑（絕對路徑會變） |
| `Z3A_TOKEN` / `Z3A_REFRESH_TOKEN` | token 約 10 天過期，移植當下多半已失效，步驟 8 從 Fiddler 重抓 |

其餘 key（`SQL_*`、`SECRET_KEY`、`Z3A_PHONE/PASSWORD`、`DJANGO_ALLOWED_HOSTS`、`CSRF_TRUSTED_ORIGINS`、`TS_AUTHKEY`）**沿用不動**（除非 Tailscale 機器名變了，見步驟 8）。
特別注意 `SQL_HOST=db` 是 docker 服務名，**不要改成 localhost**。

## 步驟 6 — 環境檢查 + 安裝本機 Python 套件

先跑檢查腳本，確認軟體與環境變數就緒：

```powershell
cd D:\宇靖\solar-tracking-dashboard\移植包_MIGRATION_KIT
powershell -ExecutionPolicy Bypass -File .\2_在新機執行_環境檢查.ps1
```

再安裝本機腳本（`z3a_collect.py`、ANFIS 訓練、固定面板 pipeline）所需套件：

```powershell
cd D:\宇靖\solar-tracking-dashboard\移植包_MIGRATION_KIT
pip install -r requirements-local.txt ^
  --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org
```

> `tensorflow` 較大，只有要重新訓練 ANFIS 才需要；若新機只做維運可先註解掉它再裝。

### ⚠️ 一定要設 `PYTHONUTF8=1`（最容易踩雷處）

Windows 預設 stdout 是 cp950，遇到 Z3A 雲端 CSV 裡的簡體字（如「时间」）會 `UnicodeEncodeError` 且**靜默失敗**（資料合併 0 筆、你不會收到錯誤）。
設定方式：設定 → 系統 → 進階系統設定 → 環境變數 → 新增系統變數 `PYTHONUTF8 = 1`，然後**重開 PowerShell**。

> 另：從 git clone 下來的 `.ps1` 應已含 UTF-8 BOM；若你自行編輯過含中文的 `.ps1`，存檔要選「UTF-8 with BOM」，否則 PowerShell 5.1 會 parse 失敗。

## 步驟 7 — 啟動 Docker 並還原 MySQL

> ⚠️ **先關掉 Fiddler！** Fiddler 的 HTTPS decrypt 會攔截容器 TLS，導致 Tailscale 報
> `x509: certificate signed by unknown authority (CN=DO_NOT_TRUST_FiddlerRoot)`。

```powershell
cd D:\宇靖\solar-tracking-dashboard
docker-compose -f docker-compose-dev.yml up -d --build
```

等 MySQL 容器起來後，匯入舊機的資料庫：

```powershell
docker exec -i solar_db sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD"' < solar_db_dump.sql
```

> 若即時資料可由樹莓派重新上傳，也可**跳過 MySQL 匯入**（CSV 歷史研究資料不在 DB，不受影響）。

檢查容器與 log：

```powershell
docker ps
docker logs solar_backend --tail 50
docker logs solar_tailscale --tail 50
```

## 步驟 8 — Tailscale、Z3A token、Windows 排程

**Tailscale：**
- compose 的 `tailscale` 容器 `hostname: solar-dashboard` 決定公開網址 `solar-dashboard.tail7c1eb9.ts.net`。
- 到 [Tailscale Admin → Machines](https://login.tailscale.com/admin/machines) 把**舊機的 `solar-dashboard` 節點刪除或停用**，否則新機可能被自動改名成 `solar-dashboard-1`，公開網址就變了。
- 若機器名變了，記得同步改 `.env.dev` 的 `DJANGO_ALLOWED_HOSTS`、`CSRF_TRUSTED_ORIGINS` 與 `tailscale-config/serve.json`。
- `TS_AUTHKEY` 若是 Reusable + No expiry 可沿用；否則到 [Keys](https://login.tailscale.com/admin/settings/keys) 重新產生貼回 `.env.dev`。

**Z3A token（半自動，每約 10 天手動更新）：**
1. 新機裝好 Fiddler Classic、設定 HTTPS decrypt（照專案根目錄的 `Z3A_TOKEN_SOP.md`）。
2. 用手機 App 登入 Z3A，從 Fiddler 抓最新 `Z3A_TOKEN` 與 `Z3A_REFRESH_TOKEN`，貼進 `.env.dev`。
3. 驗證：
   ```powershell
   python z3a_check_token.py     # 看 token 剩幾天
   python z3a_ping.py            # 確認新機 IP 沒被雲端 block
   ```
> 抓 token 與抓資料分開做：跑 `z3a_collect` 時別同時開 Fiddler decrypt。

**Windows Task Scheduler（排程綁本機，必須重註冊）：**
```powershell
# 以「系統管理員」身分開 PowerShell
cd D:\宇靖\solar-tracking-dashboard
.\register_task_scheduler.ps1
```
這會註冊每週一 02:00 跑 `solar_weekly_run.ps1`。註冊後到「工作排程器」確認任務存在、路徑指向新機。
> Cowork 端的 `solar-weekly-maintenance`（週四 09:00 token 提醒）是雲端排程，與本機無關，不用重設。

## 步驟 9 — 驗證清單（全過才算完成）

- [ ] `git status` 正常，無遺漏舊機改動
- [ ] `.env.dev` 存在，`Z3A_CSV_PATH` 已改成新機路徑
- [ ] `PYTHONUTF8=1` 系統環境變數已設（重開過終端機）
- [ ] `pip install -r requirements-local.txt` 成功
- [ ] `docker ps` 三容器都 `Up`
- [ ] `http://localhost:8000/dashboard/` 開得起來、7 頁籤正常
- [ ] 「固定面板研究」頁有資料（CSV 載入成功）
- [ ] 「即時監控」頁讀得到 MySQL 資料（若有匯入 DB）
- [ ] 公開網址 `https://solar-dashboard.tail7c1eb9.ts.net/dashboard/` 可連
- [ ] `python z3a_check_token.py` 顯示 token 天數
- [ ] `python z3a_collect.py --days 1` 能抓到資料、無編碼錯誤
- [ ] `register_task_scheduler.ps1` 已跑、工作排程器看得到任務
- [ ] 舊機 Tailscale 節點已刪/停用

---

## 一句話摘要

**程式碼靠 git；`.env.dev` + 主 CSV + `solar_angle_data.db` + MySQL dump 用打包腳本帶；新機要設 `PYTHONUTF8=1`、改 `Z3A_CSV_PATH`、重抓 Z3A token、重註冊排程、處理 Tailscale 機器名。起 docker 前先關 Fiddler。**
