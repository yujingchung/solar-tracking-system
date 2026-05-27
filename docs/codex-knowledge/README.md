# Codex Knowledge

這個資料夾是給未來維護這個太陽能追蹤 dashboard 的 Codex / 接手者看的長期知識區。

目的不是取代正式 README，而是保存「這台 Windows 接手機」的實際狀態、移植決策、維運流程與踩坑紀錄。這些內容應保持可讀、可驗證、不可含秘密。

## 建議閱讀順序

1. `current-local-state.md`：目前這台電腦的專案位置、資料位置、服務狀態。
2. `operations-runbook.md`：日常啟動、檢查、排程、token 更新、dump 匯入流程。
3. `z3a-token-app-cache.md`：從七云物聯 App cache 自動更新 Z3A token 的流程。
4. `migration-log-2026-05.md`：2026-05 新機移植與平行運轉紀錄。
5. `troubleshooting.md`：已遇過的問題與解法。

## 安全規則

- 不記錄實際 `Z3A_TOKEN`、帳號密碼、Tailscale auth key。
- 不把大型 CSV、MySQL data directory、SQLite DB、log、`.env.dev` 放進 git。
- 若需要描述秘密，只寫「在哪裡更新」與「怎麼驗證」，不要貼值。
- 舊節點 `solar-dashboard.tail7c1eb9.ts.net` 推定是學長電腦。平行運轉期間不要刪除或覆蓋。
