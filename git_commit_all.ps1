# ============================================================
# git_commit_all.ps1
# Commit and push all 2026-05-15 changes to GitHub in logical groups
#
# Usage:
#   cd D:\宇靖\solar-tracking-dashboard
#   .\git_commit_all.ps1
#
# Behavior:
#   1. Clean any leftover .git/index.lock
#   2. Stage and commit in 5 logical groups
#   3. Push to origin/main
# ============================================================

$ErrorActionPreference = 'Stop'
Set-Location 'D:\宇靖\solar-tracking-dashboard'

# Use UTF-8 for git commit messages
$env:LC_ALL = 'C.UTF-8'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding           = [System.Text.Encoding]::UTF8

# Force git on Windows to use Unicode for commit messages
git config --local i18n.commitEncoding utf-8
git config --local i18n.logOutputEncoding utf-8

# ------------------------------------------------------------
# Step 0: Clean stale lock if present
# ------------------------------------------------------------
if (Test-Path '.git\index.lock') {
    Write-Host 'Removing stale .git\index.lock ...' -ForegroundColor Yellow
    Remove-Item '.git\index.lock' -Force
}

Write-Host '=== Current branch ===' -ForegroundColor Cyan
git branch --show-current

Write-Host ''
Write-Host '=== Untracked + Modified summary ===' -ForegroundColor Cyan
git status --short | Measure-Object | Select-Object -ExpandProperty Count
Write-Host '(use `git status --short` for full list)'

# ------------------------------------------------------------
# Commit 1: .gitignore + CLAUDE.md (project meta)
# ------------------------------------------------------------
Write-Host ''
Write-Host '=== Commit 1: project meta (.gitignore + CLAUDE.md) ===' -ForegroundColor Green
git add .gitignore CLAUDE.md
git commit -m "docs: 更新 .gitignore + CLAUDE.md 反映 2026-05-15 重構

- .gitignore: 加 .env.dev backups / logs/ / *.bak.*.csv / z3a_pipeline_output/
- CLAUDE.md: 更新 Section 4 (dashboard 7 頁籤架構)、5 (新增 kpi-summary + reload endpoint)、9 (Z3A 半自動化)、10 (closed issues)、12 (env vars)、13 (design decisions)
- 新增 Section 14: 本輪主要改進清單"

# ------------------------------------------------------------
# Commit 2: Dashboard frontend redesign (theme + html)
# ------------------------------------------------------------
Write-Host ''
Write-Host '=== Commit 2: dashboard frontend redesign ===' -ForegroundColor Green
git add backend/static/theme.css
git add backend/staticfiles/theme.css
git add backend/static/dashboard.html
git add backend/staticfiles/dashboard.html
git commit -m "feat(dashboard): 學術深藍+錢金黃配色系統，7 頁籤架構，研究 KPI 列

- 新增 theme.css 設計系統 (navy-1~5 / gold-1~3 / system identity tokens)
- 完全重寫 dashboard.html (~2189 行，從 1461 行擴充)
- 頁籤從 8 個整理為 7 個：
  * 總覽 (新增研究 KPI 列 + 季節切換)
  * 固定面板研究 (新增：排行榜 + 方位/傾角效應 + A vs B 散布圖 + 月度 heatmap)
  * CSV 進階分析 (保留原舊版完整功能)
  * 即時監控 (合併原 4 個系統 tab 為 1 個 + 子切換)
  * 發電比較
  * Z3A 採集
  * 下載中心 (新)
- 全部使用手繪 SVG 圖示取代 emoji
- 顏色硬編碼改為 CSS 變數，數字統一 tabular-nums"

# ------------------------------------------------------------
# Commit 3: Backend KPI endpoint + cache invalidation
# ------------------------------------------------------------
Write-Host ''
Write-Host '=== Commit 3: backend KPI + reload + cache ===' -ForegroundColor Green
git add backend/dashboard/fixed_panel_api.py
git add backend/dashboard/urls.py
git commit -m "feat(backend): 新增研究 KPI endpoint + cache mtime auto-reload

- fixed_panel_api.py:
  * 修復原本斷掉的 FixedPanelStatusView (line 318 import o)
  * 新增 FixedPanelKpiSummaryView (/api/fixed-panels/kpi-summary/)
    回傳：total_energy_kwh, per_group (12 組合排行), best/worst, diff_pct,
         by_tilt, by_azimuth, by_season, ab_consistency
    支援 ?season=spring|summer|fall|winter|all 篩選
  * 新增 FixedPanelReloadView (POST /api/fixed-panels/reload/)
    給 scheduled task 抓完新資料後呼叫
  * get_df() 加入 mtime 檢查 — CSV 被外部更新自動重讀
  * 新增 invalidate_df_cache() 手動清快取 helper
- urls.py: 註冊兩個新 endpoint"

# ------------------------------------------------------------
# Commit 4: Z3A automation (script + helpers + SOP)
# ------------------------------------------------------------
Write-Host ''
Write-Host '=== Commit 4: Z3A 半自動化 ===' -ForegroundColor Green
git add z3a_collect.py
git add z3a_check_token.py
git add z3a_debug_login.py z3a_debug_login2.py z3a_debug_refresh.py z3a_ping.py
git add Z3A_TOKEN_SOP.md
git commit -m "feat(z3a): 修正登入格式 + 加 refresh fallback + 加診斷工具集

z3a_collect.py:
- 修正 _login_with_phone(): /user/login + form-urlencoded + MD5(password)
  + PassWord 欄位 (注意大寫 W) + 讀 data.tokenString
- 新增 _refresh_with_token2(): 用 tokenString2 嘗試 6 個常見端點
- 新增 _ensure_valid_token(): token 有效 -> refresh -> 帳密登入 三階段
- 新增 _load_env_file(): 讀 .env.dev 補環境變數

新增工具：
- z3a_check_token.py: 解 JWT 看 access + refresh token 剩多少天
- z3a_ping.py: 確認雲端是否可達（區分 Fiddler 卡住 vs IP block）
- z3a_debug_login.py / login2.py: 找出正確登入格式的盲試腳本
- z3a_debug_refresh.py: 探測 refresh 端點 (已確認雲端未實作)
- Z3A_TOKEN_SOP.md: 完整手動更新 SOP（含 Fiddler 步驟）

備註：Z3A 雲端強制圖形驗證碼（Safetynum + Safetyid），純自動登入不可行；
維運策略改為「每 10 天從 Fiddler 抓 token 貼進 .env.dev」"

# ------------------------------------------------------------
# Commit 5: Windows Task Scheduler automation
# ------------------------------------------------------------
Write-Host ''
Write-Host '=== Commit 5: Windows Task Scheduler 排程 ===' -ForegroundColor Green
git add solar_weekly_run.ps1
git add register_task_scheduler.ps1
git add git_commit_all.ps1
git commit -m "feat(scheduling): Windows Task Scheduler 每週一 02:00 自動抓取

- solar_weekly_run.ps1: 完整 4 階段運維腳本
  Stage 1: Docker 容器健康 + Django API 200 檢查
  Stage 2: python z3a_check_token.py 看 token 剩多少天 (5 級分流)
  Stage 3: token 還有效 -> python -X utf8 z3a_collect.py --pipeline --days 7
  Stage 3.5: POST /api/fixed-panels/reload/ 通知 backend 清快取
  Stage 4: 列最新 3 個 .bak 檔
  輸出: logs/solar_weekly_YYYY-MM-DD.log + logs/latest_report.txt

- register_task_scheduler.ps1: 一鍵註冊到 Windows Task Scheduler
  - Trigger: 每週一 02:00
  - Settings: 電池可跑、開機補跑、最長 2 小時、失敗重試 3 次
  - 用 \$PSScriptRoot 解析路徑避免中文路徑硬編碼

- git_commit_all.ps1: 本次 commit 用的批次腳本（保留以利後續參考）

關鍵設定:
- \$env:PYTHONUTF8 = '1' + python -X utf8 + chcp 65001
- [Console]::OutputEncoding = UTF8 (讓 PS 正確解碼 Python 輸出)
- 兩個 .ps1 都加 UTF-8 BOM 讓 PowerShell 5.1 能正確解析

排程分工:
- Windows TS (本機): 真正做事 (docker + 雲端抓取)
- Cowork (sandbox): 純 token 提醒 (週四 09:00)"

# ------------------------------------------------------------
# Step 99: Push to origin
# ------------------------------------------------------------
Write-Host ''
Write-Host '=== Push to origin/main ===' -ForegroundColor Cyan
git log --oneline -5
Write-Host ''
git push origin main

Write-Host ''
Write-Host '=== DONE ===' -ForegroundColor Green
Write-Host 'View on GitHub:' -ForegroundColor Cyan
Write-Host 'https://github.com/yujingchung/solar-tracking-system'
