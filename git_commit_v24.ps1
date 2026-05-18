# ============================================================
# git_commit_v24.ps1
# Push v2.4 changes (manual + illumination merge tool) to GitHub
#
# Usage:
#   cd D:\宇靖\solar-tracking-dashboard
#   .\git_commit_v24.ps1
#
# Run AFTER git_commit_all.ps1 (or independently — script is idempotent)
# ============================================================

$ErrorActionPreference = 'Stop'
Set-Location 'D:\宇靖\solar-tracking-dashboard'

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding           = [System.Text.Encoding]::UTF8
git config --local i18n.commitEncoding utf-8
git config --local i18n.logOutputEncoding utf-8

# Clean stale lock if present
if (Test-Path '.git\index.lock') {
    Write-Host 'Removing stale .git\index.lock ...' -ForegroundColor Yellow
    Remove-Item '.git\index.lock' -Force
}

function Commit-IfChanges {
    param([string]$Message, [string[]]$Files)

    # Stage files (will silently skip ignored / missing ones)
    foreach ($f in $Files) {
        if (Test-Path $f) {
            git add -- "$f" 2>&1 | Out-Null
        }
    }
    # Check if anything is staged
    $staged = git diff --cached --name-only
    if (-not $staged) {
        Write-Host "  (nothing new to commit)" -ForegroundColor Gray
        return
    }
    Write-Host "  staged:" -ForegroundColor Cyan
    $staged | ForEach-Object { Write-Host "    $_" }
    git commit -m $Message
}

Write-Host ''
Write-Host '=== Commit A: feat(illumination) merge tool ===' -ForegroundColor Green
Commit-IfChanges "feat(illumination): 加 merge_illumination_csv.py 從本機 CSV 合併照度

工具特性：
- 自動偵測 datetime / data.avg 欄位
- 處理 Mongo CSV 時區假象（datetime 帶 Z 但實際已是台北時間，
  不再做 +8 轉換 → 之前 step4 內建匯入會把照度峰值錯移到傍晚）
- 舊優先策略：主 CSV 已有 illumination 的時間點保留原值，新 CSV 只補空缺
- 自動 .bak.illumination.YYYYMMDD_HHMMSS.csv 備份
- --dry-run 可預覽不寫檔，--force-overwrite 改為新值覆蓋

用於不靠 MongoDB 連線、直接從 Mongo 匯出的 CSV 更新照度。" `
@('merge_illumination_csv.py')

Write-Host ''
Write-Host '=== Commit B: docs(manual) v2.4 整合使用手冊 ===' -ForegroundColor Green
Commit-IfChanges "docs(manual): 整合使用手冊 v2.4 — 涵蓋 dashboard + 自動化 + token SOP

v2.4 整合 v2.3 舊版 + 本輪所有新增功能，共 12 章 719 段：
- Ch 1 系統概述（加 Task Scheduler 元件）
- Ch 2 每週維護（加自動模式 + 照度合併工具）
- Ch 3 面板對照表（不變）
- Ch 4 五步前處理（註記照度匯入改用獨立工具）
- Ch 5 儀表板（全寫：4 頁籤 → 7 頁籤）
- Ch 6 Backend API 端點（新）
- Ch 7 自動化排程系統（新）
- Ch 8 Z3A Token 手動更新 SOP（新）
- Ch 9 照度資料更新（新）
- Ch 10 常用指令速查（更新）
- Ch 11 疑難排解（8 個常見問題）
- Ch 12 路徑與環境變數（含 Z3A_REFRESH_TOKEN）

並保留：
- 使用手冊.docx (v2.3 原版，作對照)
- Dashboard_使用手冊_v1.docx (僅 dashboard 那份，過渡版)" `
@('使用手冊_v2.4.docx', 'Dashboard_使用手冊_v1.docx', '使用手冊.docx')

Write-Host ''
Write-Host '=== Commit C: chore git_commit_v24.ps1 ===' -ForegroundColor Green
Commit-IfChanges "chore: 加 git_commit_v24.ps1 push script

v2.4 階段使用的 push 腳本。idempotent — 已 commit 過的會跳過。" `
@('git_commit_v24.ps1')

Write-Host ''
Write-Host '=== Push to origin/main ===' -ForegroundColor Cyan
git log --oneline -8
Write-Host ''
git push origin main

Write-Host ''
Write-Host '=== DONE ===' -ForegroundColor Green
Write-Host 'View on GitHub: https://github.com/yujingchung/solar-tracking-system' -ForegroundColor Cyan
