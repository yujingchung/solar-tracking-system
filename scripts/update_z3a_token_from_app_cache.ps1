param(
    [switch]$Apply,
    [switch]$RecreateBackend,
    [switch]$CheckStatus,
    [string]$Python = "C:\01_CODE\python311\python.exe",
    [string]$CacheFile = "",
    [string]$EnvFile = "",
    [string]$BackupDir = ""
)

$ErrorActionPreference = "Stop"
$Script = Join-Path $PSScriptRoot "update_z3a_token_from_app_cache.py"
$ArgsList = @($Script)

if ($Apply) { $ArgsList += "--apply" }
if ($RecreateBackend) { $ArgsList += "--recreate-backend" }
if ($CheckStatus) { $ArgsList += "--check-status" }
if ($CacheFile) { $ArgsList += @("--cache-file", $CacheFile) }
if ($EnvFile) { $ArgsList += @("--env-file", $EnvFile) }
if ($BackupDir) { $ArgsList += @("--backup-dir", $BackupDir) }

& $Python @ArgsList
exit $LASTEXITCODE
