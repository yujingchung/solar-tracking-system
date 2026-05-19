# ============================================================
# cleanup_reorganize.ps1
# 重新整理太陽能監控平台專案目錄結構
#
# 功能：
#   1. 建立 _archive/ + data/illumination_inbox/ + data/illumination_archive/
#   2. 把 debug / 過渡 / 舊版檔案歸檔
#   3. 刪除明顯垃圾（test_write.txt、failed clone 等）
#   4. 移動老照度 CSV 到 archive
#   5. 最後產生報告
#
# 使用：
#   cd D:\宇靖\solar-tracking-dashboard
#   .\cleanup_reorganize.ps1
#
# 跑之前確認你已經 git push（清掉的東西 git 還能還原）
# ============================================================

$ErrorActionPreference = 'Continue'
Set-Location 'D:\宇靖\solar-tracking-dashboard'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  專案清理與重組" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan

# 計數器
$script:created = 0
$script:moved = 0
$script:deleted = 0
$script:skipped = 0

function Ensure-Dir($path) {
    if (-not (Test-Path $path)) {
        New-Item -ItemType Directory -Force -Path $path | Out-Null
        Write-Host "  ✓ 建立資料夾: $path" -ForegroundColor Green
        $script:created++
    }
}

function Move-IfExists($source, $dest) {
    if (Test-Path $source) {
        $destDir = Split-Path $dest -Parent
        Ensure-Dir $destDir
        if (Test-Path $dest) {
            Write-Host "  ⊘ 目標已存在，跳過: $dest" -ForegroundColor Yellow
            $script:skipped++
        } else {
            Move-Item -Force $source $dest
            Write-Host "  → 搬: $source → $dest" -ForegroundColor Blue
            $script:moved++
        }
    } else {
        Write-Host "  · 不存在: $source" -ForegroundColor DarkGray
    }
}

function Remove-IfExists($path, $description = "") {
    if (Test-Path $path) {
        cmd /c "if exist `"$path\*`" (rmdir /s /q `"$path`") else (del /f /q `"$path`")" 2>$null
        if (-not (Test-Path $path)) {
            Write-Host "  ✗ 刪: $path $description" -ForegroundColor Red
            $script:deleted++
        } else {
            # PowerShell fallback
            Remove-Item -Recurse -Force $path -ErrorAction SilentlyContinue
            if (-not (Test-Path $path)) {
                Write-Host "  ✗ 刪 (PS): $path $description" -ForegroundColor Red
                $script:deleted++
            } else {
                Write-Host "  ⚠ 無法刪除: $path（權限問題）" -ForegroundColor Yellow
                $script:skipped++
            }
        }
    }
}

# ────────────────────────────────────────────────────────────
# Step 1：建立新的目錄結構
# ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "── Step 1：建立目錄結構 ──" -ForegroundColor Cyan
Ensure-Dir "_archive"
Ensure-Dir "_archive/z3a_debug"
Ensure-Dir "_archive/old_manuals"
Ensure-Dir "_archive/illumination_csv_history"
Ensure-Dir "_archive/dashboard_html_backups"
Ensure-Dir "data/illumination_inbox"
Ensure-Dir "data/illumination_archive"

# ────────────────────────────────────────────────────────────
# Step 2：歸檔 Z3A debug 腳本（已完成任務的）
# ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "── Step 2：歸檔 Z3A debug 腳本 ──" -ForegroundColor Cyan
Move-IfExists "z3a_debug_login.py"   "_archive/z3a_debug/z3a_debug_login.py"
Move-IfExists "z3a_debug_login2.py"  "_archive/z3a_debug/z3a_debug_login2.py"
Move-IfExists "z3a_debug_refresh.py" "_archive/z3a_debug/z3a_debug_refresh.py"
Move-IfExists "z3a_ping.py"          "_archive/z3a_debug/z3a_ping.py"
Move-IfExists "check_z3a.py"         "_archive/z3a_debug/check_z3a.py"

# ────────────────────────────────────────────────────────────
# Step 3：歸檔老版手冊
# ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "── Step 3：歸檔老版手冊 ──" -ForegroundColor Cyan
Move-IfExists "Dashboard_使用手冊_v1.docx" "_archive/old_manuals/Dashboard_使用手冊_v1.docx"
Move-IfExists "使用手冊.docx"               "_archive/old_manuals/使用手冊_v2.3.docx"
# 留下 使用手冊_v2.4.docx 在根目錄當主版

# ────────────────────────────────────────────────────────────
# Step 4：歸檔老的 dashboard.html 備份
# ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "── Step 4：歸檔 dashboard.html 備份 ──" -ForegroundColor Cyan
Move-IfExists "backend/static/dashboard.bak.20260506_070852.html" "_archive/dashboard_html_backups/dashboard.bak.20260506.html"
Move-IfExists "backend/static/dashboard.bak.20260514.html"        "_archive/dashboard_html_backups/dashboard.bak.20260514.html"
Move-IfExists "backend/staticfiles/dashboard.bak.20260506_070852.html" "_archive/dashboard_html_backups/staticfiles_dashboard.bak.20260506.html"
Move-IfExists "backend/staticfiles/dashboard.bak.20260514.html"        "_archive/dashboard_html_backups/staticfiles_dashboard.bak.20260514.html"

# ────────────────────────────────────────────────────────────
# Step 5：歸檔老照度 CSV
# ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "── Step 5：歸檔老照度 CSV ──" -ForegroundColor Cyan
Move-IfExists "solar.radiation-v2_20260505.csv" "_archive/illumination_csv_history/solar.radiation-v2_20260505.csv"

# ────────────────────────────────────────────────────────────
# Step 6：刪除明顯垃圾
# ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "── Step 6：刪除垃圾檔案 ──" -ForegroundColor Cyan
Remove-IfExists "test_write.txt" "(5 byte 開發測試殘留)"
Remove-IfExists ".env.dev.bak.20260514" "(含舊 token 備份，gitignored)"
Remove-IfExists "backend/static/dashboard.html.test" "(0 byte 開發殘留)"
Remove-IfExists "backend/static/colors_and_type.css" "(舊 design tokens，已被 theme.css 取代)"
Remove-IfExists "backend/staticfiles/colors_and_type.css" "(同上)"
Remove-IfExists "ui-ux-pro-max-skill" "(上次失敗的 clone 整個目錄)"

# ────────────────────────────────────────────────────────────
# Step 7：刪除 .claude/skills/ui-ux-pro-max 殘留
# ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "── Step 7：清掉 .claude/skills/ui-ux-pro-max 殘留 ──" -ForegroundColor Cyan
Remove-IfExists ".claude/skills/ui-ux-pro-max" "(失敗的 skill 安裝)"
Remove-IfExists ".claude/skills/ui-ux-pro-max-tmp" "(也是失敗殘留)"

# ────────────────────────────────────────────────────────────
# Step 8：建立 illumination_inbox/README.md 告訴未來的你怎麼用
# ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "── Step 8：寫 illumination_inbox/README.md ──" -ForegroundColor Cyan
$readmePath = "data/illumination_inbox/README.md"
@'
# illumination_inbox/

從 MongoDB Atlas 抓回來的照度 CSV，丟到這個資料夾，
**每週一 02:00 Windows Task Scheduler 會自動合併**進主 CSV。

## 你要做的

1. 從 Mongo Atlas Compass 匯出 solar.radiation-v2 collection
2. 存成 `solar.radiation-v2_YYYYMMDD.csv`（不一定要這個檔名，副檔名是 .csv 就好）
3. 直接丟到 **這個資料夾**
4. 等下週一自動合併（或手動跑 `..\..\solar_weekly_run.ps1`）

## 自動化會做什麼

當 `solar_weekly_run.ps1` 跑時，會：

1. 列出 `data/illumination_inbox/*.csv` 所有檔案
2. 對每個檔案跑 `python merge_illumination_csv.py --csv <該檔>`
3. 合併成功後把該檔搬到 `data/illumination_archive/`（不是這裡了）
4. 通知 backend reload 快取

## 注意

- **不要直接修改既有合併過的 CSV**，會打亂索引
- 照度欄位有重疊時：**舊優先**，新 CSV 只補空缺
- 想覆寫舊資料時，跑 `merge_illumination_csv.py --force-overwrite`
'@ | Out-File -Encoding UTF8 $readmePath
Write-Host "  ✓ 寫好: $readmePath" -ForegroundColor Green

# ────────────────────────────────────────────────────────────
# Step 9：寫 _archive/README.md
# ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "── Step 9：寫 _archive/README.md ──" -ForegroundColor Cyan
@'
# _archive/

歷史檔案歸檔區。這些檔案曾經有用、保留作參考，但不再活躍使用。

| 子資料夾 | 內容 |
|---------|------|
| `z3a_debug/` | Z3A 登入格式 / refresh 端點探測腳本（已找出答案）|
| `old_manuals/` | 舊版使用手冊（已被 `使用手冊_v2.4.docx` 取代）|
| `illumination_csv_history/` | 舊照度 CSV（已合併進主 CSV）|
| `dashboard_html_backups/` | dashboard.html 歷史版本備份 |

整個 `_archive/` 已加入 `.gitignore`，不會 push 到 GitHub。
要徹底清除可以直接刪除整個資料夾。
'@ | Out-File -Encoding UTF8 "_archive/README.md"
Write-Host "  ✓ 寫好: _archive/README.md" -ForegroundColor Green

# ────────────────────────────────────────────────────────────
# 最終報告
# ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  完成" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  建立資料夾：$script:created" -ForegroundColor Green
Write-Host "  搬移檔案  ：$script:moved" -ForegroundColor Blue
Write-Host "  刪除檔案  ：$script:deleted" -ForegroundColor Red
Write-Host "  跳過      ：$script:skipped" -ForegroundColor Yellow
Write-Host ""
Write-Host "下一步：" -ForegroundColor Cyan
Write-Host "  1. 把 _archive/ 加入 .gitignore（如果還沒）" -ForegroundColor White
Write-Host "  2. 之後抓到照度 CSV 丟到 data\illumination_inbox\" -ForegroundColor White
Write-Host "  3. 跑 .\solar_weekly_run.ps1 驗證新流程正常" -ForegroundColor White
