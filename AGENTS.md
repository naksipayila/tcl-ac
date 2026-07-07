# AGENTS.md

## Safety
- This repo is Cloudflare-only; the old local Python panel/CLI has been removed.
- Device-changing Cloudflare Worker paths include POSTs to `/api/start`, `/api/power`, `/api/swing`, and `/api/phase`.
- `/api/stop` only stops the stored D1 cycle state; it does not power off the AC.
- `GET /api/device-status` reads the real device shadow; do not call it unless the user asks for a real status read.
- The Worker cron can send commands when D1 state has `running=true`.
- Never print, commit, or paste `TCL_SSO_TOKEN`, captured `ssotoken`, AWS credentials, Authorization headers, cookies, or presigned AWS URLs.

## Commands
- Work from `cloudflare/` for Cloudflare tasks.
- Install dependencies: `npm install`.
- Safe syntax check: `node --check src/worker.js`.
- Wrangler dry-run: `npx wrangler deploy --dry-run`.
- Apply D1 migrations: `npx wrangler d1 migrations apply tcl-ac-state --remote`.
- Deploy: `npx wrangler deploy`.
- Required Worker secrets: `TCL_SSO_TOKEN`, `PANEL_PASSWORD`, and `PANEL_SESSION_SECRET`; never put them in git or command output.

## Architecture
- `cloudflare/src/worker.js` owns the serverless API, login cookie handling, AWS SigV4, MQTT-over-WebSocket shadow publishing, D1 state, and cron phase switching.
- `cloudflare/public/index.html` owns the hosted panel and calls same-origin `/api/*` endpoints.
- `cloudflare/wrangler.toml` owns Worker bindings, D1 database binding, env vars, assets, and cron schedule.
- `cloudflare/migrations/` owns D1 schema migrations.

## UI/Docs
- Current panel is compact and monochrome; keep UI labels English.
- When `state.power_switch` is false, Start Cycle, Compressor, and Swing should render disabled/off and avoid sending commands.
- Power toggle is a confirmation slider; do not replace it with a simple click toggle.
- Keep docs Cloudflare-only; do not reintroduce local Python server instructions unless explicitly asked.

## Repo Notes
- There is no Python runtime in the repo now.
- `node_modules/`, `.wrangler/`, `.dev.vars`, `.env`, and `opencode.json` are local-only and should not be committed.
- `opencode.json` is local/user-specific HTTP Toolkit MCP config; do not rely on it being present in other checkouts.
