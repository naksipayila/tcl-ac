# AGENTS.md

## Safety
- This repo is Cloudflare-only; the old local Python panel/CLI is gone, so keep docs and workflows Cloudflare-only.
- Live Worker URL is `https://tcl-ac.qaliqtaha.workers.dev`; never use GitHub Pages for this app.
- Do not deploy unless the user explicitly asks for deploy.
- Never print, commit, or paste `TCL_SSO_TOKEN`, captured `ssotoken`, AWS credentials, Authorization headers, cookies, or presigned AWS/MQTT URLs.
- Device-changing routes are `POST /api/start`, `/api/power`, `/api/swing`, and `/api/phase`; cron can also send commands when D1 `controller.running=true`.
- `POST /api/stop` only stops D1 cycle state; it does not power off the AC.
- `GET /api/session` and `GET /api/state` read only Worker/D1 state. `GET /api/device-status` reads the real shadow and persists D1 state.
- `POST /api/device-probe` is read-only for the AC: it tries AWS IoT SearchIndex connectivity, then falls back to reading shadow reported values. Usable shadow state is `Last Known`, not offline, even if the shadow timestamp is old. It must not change setpoints or publish desired state.
- Device command confirmation waits 20 seconds and does not clear desired state on timeout, so slow power-on commands are not cancelled before the AC receives them.

## Commands
- Work from `cloudflare/`; it is the only package root. Do not run `npm install` in the repo root.
- Install deps: `npm install`.
- Local preview: `npm run dev`. Local login needs `.dev.vars` with `PANEL_PASSWORD` and `PANEL_SESSION_SECRET`.
- Before local preview login, apply the local D1 schema: `npx wrangler d1 migrations apply tcl-ac-state --local`; login rate limiting and state reads use the `state` table.
- Omit `TCL_SSO_TOKEN` from `.dev.vars` unless intentionally testing real device commands locally.
- Worker syntax check: `npm run check` or `node --check src/worker.js`. There is no test script.
- After service worker edits run `node --check public/sw.js`; after `index.html` script edits parse inline JS with `node -e "const fs=require('fs');const h=fs.readFileSync('public/index.html','utf8');const re=new RegExp('<script>([\\\\s\\\\S]*?)<\\\\/script>','g');new Function([...h.matchAll(re)].map(m=>m[1]).join('\\n'));"`.
- After manifest edits run `node -e "JSON.parse(require('fs').readFileSync('public/manifest.webmanifest','utf8'));"`.
- Dry-run deploy: `npx wrangler deploy --dry-run`.
- Remote D1 migrations require `npx wrangler d1 migrations apply tcl-ac-state --remote`; `npm run migrate` lacks `--remote`.
- Deploy only on explicit request: `npm run deploy` or `npx wrangler deploy`.

## Architecture
- `cloudflare/src/worker.js` owns API routing, login cookies, D1 state key `controller`, login rate keys `login_rate:<hash>`, AWS SigV4, MQTT-over-WebSocket shadow publishing, and cron phase switching.
- Login rate limit is 5 failed attempts per hashed client address per 5 minutes; successful login clears that key.
- `cloudflare/wrangler.toml` owns Worker bindings/env, D1 binding, assets, cron `* * * * *`, 70F/80F 20/20 cycle values, and `MIN_SECONDS_BETWEEN_COMMANDS=5`.
- Keep `assets.run_worker_first = ["/api/*"]`; otherwise API routes fall through to asset 404s.
- Device writes must use AWS IoT MQTT-over-WebSocket publish to `$aws/things/{DEVICE_ID}/shadow/update`; REST shadow update/topic publish returned 403 for this device.
- `cloudflare/public/index.html` is the whole hosted panel, with no frontend build step; it calls same-origin `/api/*`, polls `/api/state` every 1 second, and probes device online status only on initial load/login.
- PWA files are `cloudflare/public/manifest.webmanifest`, `cloudflare/public/sw.js`, and `cloudflare/public/icons/`; the service worker must not cache `/api/*`.
- D1 schema is in `cloudflare/migrations/0001_state.sql`; the single `state` table stores both controller state and login rate records.

## Device Behavior
- `POST /api/start` sends the 70F cooling setpoint and startup swing when `STARTUP_SWING=1`.
- `POST /api/phase` stops the stored loop and sends a 70F/80F setpoint.
- `Set Temp`/`active_temperature` comes from reported target setpoint fields (`targetFahrenheitDegree`/`targetCelsiusDegree`), not an ambient room-temperature sensor.

## UI
- Current UI is a compact dark glass mobile-style panel on desktop and mobile; keep visible labels English and do not show the model label unless asked.
- Do not add manual refresh controls or automatic device-status polling unless asked.
- On initial load/login, show device status as Checking Device, then Online, Last Known, or Device Offline from `/api/device-probe`.
- `Last Known` uses `state.device_online=true` and `state.device_connection_verified=false`; controls can remain available and command confirmation handles failures. When `state.device_online` is false, the panel should look dim/offline and device controls should be disabled.
- Power is an icon-only normal button in the status hero; Start/Stop cycle is one stateful button; Controls sit below the status card.
- When `state.power_switch` is false, Start Cycle, Compressor, and Swing render disabled/off and avoid sending commands.

## Repo Notes
- Required Worker secrets are `TCL_SSO_TOKEN`, `PANEL_PASSWORD`, and `PANEL_SESSION_SECRET`; keep them in Cloudflare secrets, not git or command output.
- `cloudflare/package-lock.json` is the real package lock; root `/package-lock.json` is ignored because the repo root is not a package.
- `node_modules/`, `.wrangler/`, `.dev.vars`, `.env*`, and `opencode.json` are local-only and should not be committed.
- `opencode.json` is local/user-specific HTTP Toolkit MCP config; do not rely on it being present in other checkouts.
