# ============================================================
# git_commit_pi_deploy.ps1
# Commit Phase 3-5 changes (cleanup + Pi deploy + illumination automation)
#
# 用法：
#   先確認 cleanup_reorganize.ps1 已跑過
#   然後跑這個
# ============================================================

$ErrorActionPreference = 'Stop'
Set-Location 'D:\宇靖\solar-tracking-dashboard'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding           = [System.Text.Encoding]::UTF8
git config --local i18n.commitEncoding utf-8
git config --local i18n.logOutputEncoding utf-8

if (Test-Path '.git\index.lock') {
    Remove-Item '.git\index.lock' -Force
}

function Commit-IfStaged {
    param([string]$Message)
    $staged = git diff --cached --name-only
    if (-not $staged) {
        Write-Host "  (nothing staged for: $($Message.Substring(0, [Math]::Min(50, $Message.Length)))...)" -ForegroundColor Gray
        return
    }
    Write-Host "  staged files:" -ForegroundColor Cyan
    $staged | Select-Object -First 10 | ForEach-Object { Write-Host "    $_" }
    if ($staged.Count -gt 10) { Write-Host "    ... and $($staged.Count - 10) more" }
    git commit -m $Message
}

# ────────────────────────────────────────────────────────────
# Commit 1: 整理用的 .ps1 + .gitignore 更新
# ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== Commit 1: 整理/部署用的 PowerShell 腳本 ===" -ForegroundColor Green
git add cleanup_reorganize.ps1 build_pi_deploy.ps1 .gitignore git_commit_pi_deploy.ps1
Commit-IfStaged "chore(scripts): 加 cleanup_reorganize.ps1 + build_pi_deploy.ps1 + 更新 gitignore

- cleanup_reorganize.ps1: 一鍵整理專案 (歸檔 debug 腳本 / 舊手冊 / 老照度 CSV，刪垃圾)
- build_pi_deploy.ps1: 一次重建 4 個 Pi 部署資料夾，自動帶入 system_id 1-4 + ANFIS 模型
- .gitignore: 加 _archive/ / data/illumination_inbox/ / data/illumination_archive/
- git_commit_pi_deploy.ps1: 本次 commit 腳本（idempotent）"

# ────────────────────────────────────────────────────────────
# Commit 2: solar_weekly_run.ps1 加照度自動化 (Stage 2.5)
# ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== Commit 2: solar_weekly_run.ps1 加 Stage 2.5 照度自動化 ===" -ForegroundColor Green
git add solar_weekly_run.ps1
Commit-IfStaged "feat(scheduling): 加 Stage 2.5 自動合併照度 inbox

solar_weekly_run.ps1 新流程：
1. Backend health check
2. Token status check
2.5. ★ 新增：偵測 data/illumination_inbox/*.csv -> python merge_illumination_csv.py -> 移到 data/illumination_archive/
3. Z3A data collection (--pipeline --days 7)
3.5. Notify backend reload
4. List recent backups

User 工作流程簡化為：每週把 Mongo 匯出的照度 CSV 丟到 illumination_inbox/，
週一 02:00 排程自動合併進主 CSV、移到 archive 留底。"

# ────────────────────────────────────────────────────────────
# Commit 3: 4 個 Pi deploy 資料夾（取代舊版）
# ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== Commit 3: 4 個樹莓派部署資料夾 (重建) ===" -ForegroundColor Green

# 強制加入 deploy 內的所有檔案，包含 .keras
git add -A raspberry-pi/deploy/solar_tracking/
Commit-IfStaged "feat(pi-deploy): 重建 4 個樹莓派部署資料夾 (system_id 1-4)

新部署結構（取代 5/9 舊版）：
- 實驗組1 (system_id=1, ANFIS)：含 anfis_controller.py + models/ (V2 .keras + scaler + config)
- 實驗組2 (system_id=2, ANFIS)：同上
- 對照組1 (system_id=3, traditional)：含 traditional_controller.py
- 對照組2 (system_id=4, traditional)：同上

每個資料夾自動產生：
- 主控制器 .py (從 raspberry-pi/src/controllers/ 複製，system_id + api_url 自動替換)
- config.json (informational 配置紀錄)
- requirements.txt (ANFIS 含 tensorflow/joblib，traditional 較精簡)
- solar_tracking.service (systemd, User=pi, WorkingDirectory=/home/pi/solar_tracking/<name>)
- start.sh (手動測試)
- README.md (詳細 7 步驟部署流程)
- ANFIS：models/ 含 V2 訓練好的 .keras + scaler

api_url 預設 Tailscale Funnel public URL (Pi 在山上也能上傳)。"

# ────────────────────────────────────────────────────────────
# Commit 4: 整理結果（cleanup_reorganize.ps1 跑完後產生的變動）
# ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== Commit 4: 專案整理結果 (歸檔 / 刪檔) ===" -ForegroundColor Green
# 已被歸檔到 _archive/ 或刪除的檔案
git add -A
Commit-IfStaged "chore(cleanup): 整理專案根目錄 + 移除已棄用檔案

歸檔到 _archive/ (gitignored, 本機保留)：
- z3a_debug_login.py / login2.py / refresh.py / z3a_ping.py / check_z3a.py
- 使用手冊.docx (v2.3) / Dashboard_使用手冊_v1.docx (過渡版)
- backend/static/dashboard.bak.20260506*.html
- solar.radiation-v2_20260505.csv (老照度 dump)

刪除：
- test_write.txt (5 byte 殘留)
- .env.dev.bak.20260514 (含過期 token)
- backend/static/dashboard.html.test (空檔)
- backend/static/colors_and_type.css (被 theme.css 取代)
- ui-ux-pro-max-skill/ (上次失敗的 clone, 16 MB)

新建：
- data/illumination_inbox/ (含 README.md 說明用法)
- data/illumination_archive/ (處理過的照度 CSV 歸檔)"

# ────────────────────────────────────────────────────────────
# Push
# ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== Push to origin/main ===" -ForegroundColor Cyan
git log --oneline -8
Write-Host ""
git push origin main

Write-Host ""
Write-Host "=== DONE ===" -ForegroundColor Green
Write-Host "GitHub: https://github.com/yujingchung/solar-tracking-system" -ForegroundColor Cyan
