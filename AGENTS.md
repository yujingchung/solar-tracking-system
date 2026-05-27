# AGENTS.md

給未來在這個 repo 工作的 Codex / coding agent：

1. 先讀 `docs/codex-knowledge/README.md`。
2. 不要把 `.env.dev`、token、密碼、Tailscale auth key、Fiddler 封包內容寫進 git。
3. 這台電腦是平行運轉節點，不要刪除或接管舊的 `solar-dashboard` Tailscale 節點，除非使用者明確要求。
4. 修改 `.env.dev` 後，backend 需要重建，不是單純 restart：

```powershell
docker compose -f docker-compose-dev.yml up -d --force-recreate --no-deps backend
```

5. 維運時優先確認 dashboard、Z3A token、CSV、SQLite、MySQL、Windows Task Scheduler、Tailscale Funnel。
6. Z3A token 更新優先使用 `scripts/update_z3a_token_from_app_cache.ps1`，它會從七云物聯 App cache 更新 `.env.dev`，不要先走 Fiddler。
