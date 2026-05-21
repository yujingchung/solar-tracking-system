# MIGRATION.md — 專案移植說明

> 本檔已整理成完整的「移植包」資料夾,內含主流程文件、套件清單與自動化腳本。

完整內容請見 **[`移植包_MIGRATION_KIT/`](移植包_MIGRATION_KIT/)** 資料夾:

| 檔案 | 用途 | 在哪台機器用 |
|------|------|--------------|
| [`移植包_MIGRATION_KIT/README.md`](移植包_MIGRATION_KIT/README.md) | 完整九步移植主流程,照著做即可 | 兩台都看 |
| `移植包_MIGRATION_KIT/requirements-local.txt` | 本機(非 Docker)Python 腳本套件清單 | 新機安裝用 |
| `移植包_MIGRATION_KIT/1_在舊機執行_打包.ps1` | 自動打包 git 以外的必要檔案 | 舊機 |
| `移植包_MIGRATION_KIT/2_在新機執行_環境檢查.ps1` | 檢查新機軟體 / 環境變數 / 檔案 | 新機 |

## 一句話摘要

程式碼靠 git;`.env.dev` + 主 CSV + `solar_angle_data.db` + MySQL dump 用打包腳本帶;新機要設 `PYTHONUTF8=1`、改 `Z3A_CSV_PATH`、重抓 Z3A token、重註冊排程、處理 Tailscale 機器名。起 docker 前先關 Fiddler。
