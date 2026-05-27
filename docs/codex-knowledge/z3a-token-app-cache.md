# Z3A Token App Cache Automation

Z3A 登入 API 需要驗證碼參數，不能只靠帳號密碼穩定自動登入。這台接手機的實務做法是讀取已登入的七云物聯 Windows App 本機設定檔，抽出 app 已保存的 token，再更新 `.env.dev`。

## Token 來源

七云物聯 App cache：

```text
C:\Users\USER\AppData\Roaming\iot7.cn\七云物联\shared_preferences.json
```

使用的 key：

- `flutter.token` -> `.env.dev` 的 `Z3A_TOKEN`
- `flutter.token2` -> `.env.dev` 的 `Z3A_REFRESH_TOKEN`

不要把 token 值貼到文件、聊天紀錄或 git。

## 自動更新工具

Python 工具：

```text
C:\projects\solar-tracking-dashboard\scripts\update_z3a_token_from_app_cache.py
```

PowerShell wrapper：

```text
C:\projects\solar-tracking-dashboard\scripts\update_z3a_token_from_app_cache.ps1
```

預設是 dry-run，只顯示 token 長度、到期時間、是否需要更新，不會印出 token。

```powershell
cd C:\projects\solar-tracking-dashboard
powershell.exe -ExecutionPolicy Bypass -File .\scripts\update_z3a_token_from_app_cache.ps1
```

確認無誤後寫入 `.env.dev`，並重建 backend 讓 Docker 讀到新 env：

```powershell
cd C:\projects\solar-tracking-dashboard
powershell.exe -ExecutionPolicy Bypass -File .\scripts\update_z3a_token_from_app_cache.ps1 -Apply -RecreateBackend -CheckStatus
```

工具會在更新前自動備份 `.env.dev`，備份檔格式：

```text
.env.dev.bak.yyyyMMdd_HHmmss
```

## 什麼時候要跑

- dashboard 顯示 Z3A token 過期。
- 每週排程 log 出現 token invalid / 401。
- `python z3a_check_token.py` 顯示 access token 剩不到 3 天。
- 七云物聯 App 重新登入後，需要把新 token 同步到 Docker dashboard。

## 驗證

```powershell
Invoke-WebRequest -UseBasicParsing http://localhost:8000/api/z3a/status/
```

成功時 response 應包含：

```json
{
  "token_set": true,
  "token_valid": true
}
```

也可以打開：

```text
http://localhost:8000/dashboard/
https://solar-dashboard-zhiyu.tail7c1eb9.ts.net/dashboard/
```

## 注意事項

- 七云物聯 App 必須曾經成功登入，cache 才會有新 token。
- `.env.dev` 更新後必須 recreate backend；只 `restart` 不一定會重讀 env file。
- 若 `shared_preferences.json` 找不到，先開一次七云物聯 App 並登入。
- 若 `token_valid=false`，先確認 App cache 的 token 到期時間，再重新登入 App 後重跑工具。
