# Z3A Token 更新 SOP

> Z3A 雲端登入強制要圖形驗證碼，無法純自動化，所以採「半自動」方案：
> - 平日 Schedule task 用 `Z3A_TOKEN`（access token，10 天有效）
> - 約每 10 天手動更新一次（約 2 分鐘工作）
> - 想自己驗一下狀態：`python z3a_check_token.py`

---

## 一、何時要更新

每週一執行的 schedule task 會自動檢查 token：

| Token 剩餘 | 任務行為 | 你要做的 |
|----------|---------|---------|
| `> 7 天`  | 正常抓資料 | 沒事 |
| `3-7 天`  | 抓資料 + 通知「請本週更新」 | 找空檔做一次更新（SOP 三步） |
| `< 3 天`  | 抓資料 + 緊急通知 | **立刻更新** |
| `< 1 天`  | 跳過抓取，只發通知 | **馬上更新**，否則本週無資料 |
| `已過期`  | 完全跳過 + 通知 | 一定要更新才能繼續抓 |

或任何時候你想查：`python z3a_check_token.py`

---

## 二、更新步驟（2 分鐘搞定）

### 1. 開 Fiddler Classic
- 確認 **Tools → Options → HTTPS** 設定還在
  - ☑ Capture HTTPS CONNECTs
  - ☑ Decrypt HTTPS traffic（from all processes）
- 確認左下角顯示 **「Capturing」**（按 F12 切換）
- 把右側清單清空（Ctrl+X）

### 2. 啟雲物聯桌面 App 重新登入
- **完全關掉** 啟雲物聯 App（含背景）
- 重開 App
- 輸入 `13584809353` + `pmp123456` + 驗證碼 → 登入

### 3. Fiddler 找 token 並複製

- Fiddler 主畫面 Ctrl+F 搜 `login`
- 找到 `POST https://server.qiyunwulian.com:12341/user/login` 那筆
- 點該筆 → 右上 **Inspectors** → 上半部選 **Raw**（看 request）、下半部選 **JSON** 或 **Raw**（看 response）
- Response 會是：
  ```json
  {"code":0,"msg":"","data":{
      "tokenString":"eyJhbGciOiJIUzI1NiIsInR5...",
      "tokenString2":"eyJhbGciOiJIUzI1NiIsInR5..."
  }}
  ```

### 4. 貼進 .env.dev
打開 `D:\宇靖\solar-tracking-dashboard\.env.dev`：

```env
Z3A_TOKEN=<貼上 tokenString 的整串值>
Z3A_REFRESH_TOKEN=<貼上 tokenString2 的整串值>
```

⚠ 注意：值兩邊**不要有引號**，整串貼進去就好。

### 5. 重啟 Docker backend 讓它載入新 token
```powershell
docker-compose -f docker-compose-dev.yml restart solar_backend
```
（這個只影響 dashboard 的 Z3A 採集頁籤；`z3a_collect.py` 不需要重啟。）

### 6. 驗證
```powershell
python z3a_check_token.py
```
看到「✓ 有效 — 剩 9-10 天」就完成了。

---

## 三、抓不到 token 的特殊情況

| 症狀 | 原因 | 解法 |
|------|------|------|
| Fiddler 看不到 qiyunwulian 請求 | App 有憑證綁定，Fiddler 解密被拒 | 用瀏覽器版（如果有）或上一份「找 cache 檔」方案 |
| App 登入卡住沒反應 | 同上，App 拒絕 Fiddler 假憑證 | 同上 |
| Response body 是亂碼 | 沒裝 Fiddler 根憑證 | 重做憑證 trust：Tools → Options → HTTPS → Actions → Trust Root Certificate |
| `code != 0` | 驗證碼錯 | 重輸 |

---

## 四、Schedule Task 的位置

- 任務名稱：`weekly-z3a-data-collection`
- 排程：每週一 02:10
- 任務檔案：`C:\Users\user\Documents\Claude\Scheduled\weekly-z3a-data-collection\SKILL.md`
- 從 Claude/Cowork 側欄「Scheduled」可以手動 Run now 或修改

---

## 五、相關檔案

| 檔案 | 用途 |
|------|------|
| `z3a_collect.py` | 抓資料主腳本，schedule 自動跑這個 |
| `z3a_check_token.py` | 手動查 token 狀態 |
| `z3a_debug_login.py` | 登入 debug（盲試）|
| `z3a_debug_login2.py` | 登入 debug（聚焦 /user/login）|
| `z3a_debug_refresh.py` | refresh 端點探測（已確認不存在）|
| `z3a_ping.py` | 快速確認雲端連線 |
| `.env.dev` | 帳密 + token 設定（在 .gitignore 內）|
