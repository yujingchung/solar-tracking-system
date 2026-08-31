# codebase-memory-mcp 安裝設定指南（Claude 桌面 App / Cowork · Windows）

> 目標：把 codebase-memory-mcp 裝進 Claude 桌面 App，讓**之後每個 session（含 Cowork）**都能用它查詢、追蹤、分析你的 codebase。
> 撰寫日期：2026-06-29 ｜ 對應版本：codebase-memory-mcp（DeusData）UI variant

---

## 這是什麼

一支 **pure C、零依賴的單一執行檔**，用 tree-sitter 把整個 codebase 索引成「知識圖譜」（函式、類別、呼叫鏈、HTTP route、跨檔關係），再透過 MCP 暴露 14 個查詢工具給 AI agent。
- Django 等級專案索引約 **6 秒**；結構查詢 **< 1ms**
- 號稱比逐檔 grep **省 ~99% token**
- UI 版多一個 `localhost:9749` 的 **3D 互動知識圖譜**

對你的 `solar-tracking-dashboard`（Django + Python + 一堆腳本）特別適合拿來「這個函式被誰呼叫」「整體架構長怎樣」「改這支會影響哪些地方」。

---

## ⚠️ 先看這個：桌面 App vs Cowork 的真相

官方安裝程式**只會自動設定 Claude Code（CLI），不會碰桌面 App**。所以桌面 App 要**手動**設定。設定方式有一個關鍵機制：

- 你把 MCP server 寫進 `claude_desktop_config.json` 後：
  - **classic Claude 桌面聊天**：100% 直接可用（最穩）。
  - **Cowork 模式**：Claude Desktop 會透過 SDK 層**自動把它「橋接（bridge）」進 Cowork 的沙箱 VM**，在 Cowork 端顯示為 `type: sdk`。**不需要額外設定。**

但要誠實說：Cowork 的這個橋接是**較新、官方文件沒明寫**的行為，不同版本曾出現「桌面聊天看得到、Cowork/Claude Code 卻被停用」的 bug（GitHub issue #42453）。所以：

> **最穩的保證是 classic 桌面聊天一定能用；Cowork 是自動橋接、盡力而為。** 萬一 Cowork 端沒出現，本指南末段有 fallback。

---

## 步驟 1 — 安裝 UI 版 binary（Windows PowerShell）

開一個 PowerShell，貼上：

```powershell
# 1. 下載官方安裝腳本
Invoke-WebRequest -Uri https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/main/install.ps1 -OutFile install.ps1

# 2. (建議) 先看一下腳本內容再跑
notepad install.ps1

# 3. 安裝 UI 版，並跳過自動設定 agent（我們只手動設定桌面 App）
.\install.ps1 --ui --skip-config
```

裝完後執行檔會在（你的 Windows 使用者名是 `user`）：

```
C:\Users\user\AppData\Local\Programs\codebase-memory-mcp\codebase-memory-mcp.exe
```

> UI 版 zip 內原檔名是 `codebase-memory-mcp-ui.exe`，安裝腳本會自動改名成 `codebase-memory-mcp.exe`，所以最終就是上面這個路徑。
> 不確定路徑時，安裝後新開一個 PowerShell 執行 `where.exe codebase-memory-mcp` 確認。

**旗標說明：** `--ui`＝下載含 3D 圖譜的版本；`--skip-config`＝不自動改其他 agent 設定。
（若你之後也想在 Claude Code CLI 用，把 `--skip-config` 拿掉重跑一次即可。）

**SmartScreen 警告**：未簽章軟體可能跳警告，點「更多資訊 → 仍要執行」。

---

## 步驟 2 — 設定 Claude 桌面 App

1. 打開 Claude 桌面 App → **Settings（設定）→ Developer（開發者）→ Edit Config**。
   這會用你的編輯器打開 `claude_desktop_config.json`
   （實體路徑通常是 `C:\Users\user\AppData\Roaming\Claude\claude_desktop_config.json`）。

2. 填入以下內容（若檔案已有 `mcpServers`，只要把 `codebase-memory-mcp` 這段加進去）：

```json
{
  "mcpServers": {
    "codebase-memory-mcp": {
      "command": "C:\\Users\\user\\AppData\\Local\\Programs\\codebase-memory-mcp\\codebase-memory-mcp.exe",
      "args": ["--ui=true", "--port=9749"]
    }
  }
}
```

> **JSON 注意事項**
> - Windows 路徑的反斜線要寫成 `\\`（雙反斜線），不然 JSON 會壞。
> - 逗號、括號要對齊，JSON 很挑。
> - `args` 裡的 `--ui=true --port=9749` 就是讓 3D 圖譜跟著 MCP server 一起啟動。

---

## 步驟 3 — 完整重啟並確認

1. **完全退出** Claude 桌面 App：右下角系統匣圖示 → 右鍵 → Quit（只關視窗不算，要真的退出）。
2. 重新打開。
3. 確認載入成功：
   - **classic 聊天**：聊天框點 **「+」→ Connectors**（或工具/🔨 圖示），應該看到 `codebase-memory-mcp` 與它的 14 個工具。
   - **Cowork**：開一個 Cowork session，它應自動被橋接進來（`type: sdk`）。

---

## 步驟 4 — 索引你的專案

對 agent（桌面聊天或 Cowork 都可）說：

```
幫我索引這個專案：D:\宇靖\solar-tracking-dashboard
```

或讓它直接呼叫工具 `index_repository`，參數用**絕對路徑**：

```
index_repository(repo_path="D:\\宇靖\\solar-tracking-dashboard")
```

之後背景 watcher 會自動偵測 git 變動增量更新，不用每次重索引。

> **中文路徑提醒**：你的路徑含中文（`宇靖`、另一個專案是 `太陽能追日系統的演算法優化`）。codebase-memory-mcp 是 C + tree-sitter、走 UTF-8，理論上 OK；但你環境裡中文路徑曾踩雷（CLAUDE.md 記的 h5py / cp950 問題）。萬一索引失敗，先拿純英文路徑的資料夾測一次，確認是不是中文路徑造成的。

---

## 步驟 5 — 打開 3D 知識圖譜

只要 Claude 桌面 App 開著（MCP server 在跑），瀏覽器開：

```
http://localhost:9749
```

就能看到你 codebase 的 3D 互動圖譜。

---

## 常用 MCP 工具（14 個，挑常用的）

| 工具 | 用途 |
|------|------|
| `index_repository` | 索引一個 repo |
| `list_projects` | 列出已索引專案 + 節點/邊數 |
| `get_architecture` | 一次拿到：語言、套件、entry point、routes、hotspots、叢集 |
| `search_graph` | 依 label / 名稱 regex / 檔案 / degree 搜尋符號 |
| `trace_call_path` | BFS 追「誰呼叫這個函式」「它又呼叫了什麼」（深度 1–5）|
| `get_code_snippet` | 用 qualified name 讀某函式原始碼 |
| `detect_changes` | 把 git diff 對應到受影響符號 + 影響範圍 + 風險分級 |
| `query_graph` | 跑 Cypher-like 查詢（唯讀）|
| `search_code` | 只在已索引檔案裡做 grep |

**好用的起手式**：先 `get_graph_schema` 看圖譜結構，再 `search_graph` 找到精確名稱，再 `trace_call_path` 追呼叫鏈。

---

## 疑難排解

| 問題 | 解法 |
|------|------|
| 改了 config 但 MCP 沒載入（**靜默失敗**） | Windows 的 MSIX 版「Edit Config」可能開到錯的檔。改去編輯真正讀取的位置：`%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`，存檔後完整重啟。 |
| classic 聊天看得到、**Cowork 看不到** | 這是已知版本相依問題（issue #42453）。先確認桌面 App 是最新版；仍不行就用下方 fallback。 |
| `localhost:9749` 開不起來 | 確認你裝的是 **UI 版**、`args` 有 `--ui=true`。或在 PowerShell 手動跑：`& "C:\Users\user\AppData\Local\Programs\codebase-memory-mcp\codebase-memory-mcp.exe" --ui=true --port=9749`（它讀同一份 `~/.cache` 快取，看到的圖一樣）。 |
| port 9749 被佔用 / 啟動兩個實例衝突 | 把 `args` 裡的 `--ui=true --port=9749` 拿掉（MCP server 保持乾淨），改成「要看圖時」才用上一格的手動指令單獨開 UI。 |
| `index_repository` 失敗 | 一定要用**絕對路徑**；中文路徑問題見步驟 4 提醒。 |
| `trace_call_path` 回 0 筆 | 先用 `search_graph(name_pattern=".*部分名稱.*")` 找出正確 qualified name 再追。 |

### Fallback：Cowork 真的橋接不進來時

用 [supergateway](https://github.com/supercorp-ai/supergateway) 把 stdio MCP 轉成 HTTP endpoint，再用 project 層級 `.mcp.json` 以 `streamable-http` 連入。屬進階用法，一般不需要——classic 桌面聊天本來就能用。

---

## 更新 / 解除安裝

```powershell
# 更新（MCP server 啟動時也會自動檢查新版並提示）
codebase-memory-mcp update

# 解除安裝（移除 agent 設定/hooks，不刪 binary 與 SQLite 索引）
codebase-memory-mcp uninstall
```

索引資料庫放在 `~/.cache/codebase-memory-mcp/`（WAL 模式，重啟保留）。要整個重置就刪掉這個資料夾。

---

## 參考連結

- GitHub：https://github.com/DeusData/codebase-memory-mcp
- 官方：Local MCP Servers on Claude Desktop — https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop
- 論文（arXiv:2603.27277）：https://arxiv.org/abs/2603.27277
