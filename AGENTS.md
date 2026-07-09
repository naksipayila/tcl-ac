# Agent Notes

## Safety
- Live app is Cloudflare-only at `https://tcl-ac.qaliqtaha.workers.dev`; never use GitHub Pages or deploy `WakeOnLan/web` for production.
- Deploy only when explicitly asked. Use `cloudflare/` as the package root; the repo root is not a Node package.
- Never print, commit, or paste `TCL_SSO_TOKEN`, captured `ssotoken`, AWS credentials, Authorization headers, cookies, `RELAY_TOKEN`, or presigned AWS/MQTT URLs.
- AC-changing routes are `POST /api/start`, `/api/power`, `/api/swing`, and `/api/phase`; cron also sends AC commands when D1 `controller.running=true`.
- `POST /api/stop` only stops stored D1 cycle state and does not power off the AC. `POST /api/wol/wake` only queues a PC wake command for the Android relay.
- `GET /api/state` reads stored D1 state only; `GET /api/device-status` reads the real device shadow and persists D1 state.
- `POST /api/device-probe` is AC read-only: it tries AWS IoT SearchIndex, then shadow reported values. `Last Known` means usable shadow state with `device_connection_verified=false`, not confirmed offline.

## Commands
- From `cloudflare/`: install `npm install`; dev `npm run dev`; syntax `npm run check`; deploy `npm run deploy`.
- There is no test script. After `public/index.html` script edits run `node -e "const fs=require('fs');const h=fs.readFileSync('public/index.html','utf8');const re=new RegExp('<script>([\\\\s\\\\S]*?)<\\\\/script>','g');new Function([...h.matchAll(re)].map(m=>m[1]).join('\\n'));"`.
- After service worker edits run `node --check public/sw.js`; after manifest edits run `node -e "JSON.parse(require('fs').readFileSync('public/manifest.webmanifest','utf8'));"`.
- Local preview login needs `.dev.vars` with `PANEL_PASSWORD` and `PANEL_SESSION_SECRET`; apply local D1 first with `npx wrangler d1 migrations apply tcl-ac-state --local`.
- Keep `TCL_SSO_TOKEN` out of `.dev.vars` unless intentionally testing real AC commands locally.
- Remote D1 migrations require `npx wrangler d1 migrations apply tcl-ac-state --remote`; `npm run migrate` is not remote.

## Architecture
- `cloudflare/src/worker.js` owns API routing, auth cookies, D1 state, WOL relay endpoints, AWS SigV4, MQTT-over-WebSocket shadow publishing, and cron phase switching.
- `cloudflare/public/index.html` is the full UI; there is no frontend build step. It polls `/api/state` every second and polls `/api/wol/status` only while the PC tab is open.
- `cloudflare/wrangler.toml` owns bindings/env, assets, cron `* * * * *`, 70F/80F 20/20 cycle values, `MIN_SECONDS_BETWEEN_COMMANDS=5`, and WOL relay timing.
- Keep `assets.run_worker_first = ["/api/*"]`; otherwise API requests fall through to static asset 404s.
- D1 schema is `cloudflare/migrations/0001_state.sql`; the single `state` table stores `controller`, login-rate keys, and WOL keys when DB is bound.
- WOL keys are `command:current` and `relay:last_seen`; Worker reads D1 first and only falls back to `WOL_STATE` KV. Avoid direct KV writes because the free-tier write limit has already been hit.
- Device writes must use AWS IoT MQTT-over-WebSocket publish to `$aws/things/{DEVICE_ID}/shadow/update`; REST shadow update/topic publish returned 403 for this device.
- PWA files are `cloudflare/public/manifest.webmanifest`, `cloudflare/public/sw.js`, and `cloudflare/public/favicon.png`; service worker must not cache `/api/*` and should get a cache-name bump when cached assets change.

## AC Cycle Behavior
- `POST /api/start` sends the 70F cooling setpoint and startup swing when `STARTUP_SWING=1`, then starts the stored 20/20 loop.
- `POST /api/phase` sends a manual 70F/80F setpoint and stops the stored loop; the UI label is `Compressor` but it is setpoint control, not a real compressor sensor.
- `Set Temp` / `active_temperature` comes from reported target setpoint fields, not ambient room temperature.
- Cron transitions use `cycle_version` to avoid stale writes resurrecting a stopped cycle; failed cron transitions defer retry by `CYCLE_RETRY_SECONDS` (5 minutes), not every minute.
- Device command confirmation waits 20 seconds and does not clear desired state on timeout, so slow power-on commands are not cancelled before the AC receives them.

## WOL Relay
- Remote wake flow is `Browser -> Home Control Worker -> Android/Termux relay -> LAN magic packet`; browsers/Cloudflare cannot send UDP broadcast directly.
- Active relay files are under `WakeOnLan/relay/`; `WakeOnLan/web` is only an old standalone prototype/reference. Follow `WakeOnLan/AGENTS.md` for that subtree.
- Relay config must use `WOL_WEB_URL=https://tcl-ac.qaliqtaha.workers.dev`; test with `sh relay/run-web-relay.sh --check` then `sh relay/run-web-relay.sh --ping`.
- Current PC defaults in examples are MAC `34:5A:60:4A:8E:47` and broadcast `192.168.1.255`; keep `relay/web-config.env` private because it contains `WOL_RELAY_TOKEN`.

## UI Conventions
- Keep visible labels English and do not show the AC model label unless asked.
- Do not add manual refresh controls or automatic device-status polling unless asked.
- Initial load/login should not flash `Stopped`, `Checking`, or `Checking Device`: load `/api/state` before showing the app; `/api/device-probe` may update the state afterward.
- The app always starts on the AC tab; do not persist/restore the PC tab on reload because that triggers initial WOL status checking.
- Power is an icon-only button in the status hero; Start/Stop Cycle is one stateful button; `Stop Cycle` must remain available even if device status is offline because it is D1-only.

## Repo Notes
- Required Worker secrets are `TCL_SSO_TOKEN`, `PANEL_PASSWORD`, `PANEL_SESSION_SECRET`, and `RELAY_TOKEN`; keep them in Cloudflare secrets.
- `cloudflare/package-lock.json` is the real lockfile; root `/package-lock.json` is ignored.
- `node_modules/`, `.wrangler/`, `.dev.vars`, `.env*`, and `opencode.json` are local-only and should not be committed. `opencode.json` is user-specific HTTP Toolkit MCP config.
