# Home Control Cloudflare Worker

Serverless home control panel for the TCL AC and Wake-on-LAN PC wake commands.

## What Runs Here

- Static panel from `public/`.
- API from `src/worker.js`.
- AC controller, login-rate, Wake-on-LAN command, and relay heartbeat state in Cloudflare D1.
- `WOL_STATE` KV is a legacy read fallback; production writes WOL state to D1 when `DB` is bound.
- Minute cron trigger for phase changes.
- Device commands are sent with AWS IoT MQTT-over-WebSocket publish to the device shadow update topic.
- PC wake commands are queued for the Android/Termux relay. The Worker does not send UDP packets directly.
- The WOL relay polls for commands every few seconds; persisted heartbeat writes are throttled.
- The panel loads stored state before it appears, then probes AC status once. If AWS connectivity is unavailable but the shadow has usable reported state, the panel shows `Last Known`; controls are disabled only when the device is definitely offline or status cannot be read.
- Secrets in Cloudflare Worker secrets, not in git.

## Required Secrets

- `TCL_SSO_TOKEN` - captured TCL Home token.
- `PANEL_PASSWORD` - panel login password.
- `PANEL_SESSION_SECRET` - random session signing secret.
- `RELAY_TOKEN` - long random bearer token used only by the Wake-on-LAN Android relay.

## Commands

```powershell
npm install
npx wrangler login
npx wrangler d1 migrations apply tcl-ac-state --remote
npx wrangler secret put TCL_SSO_TOKEN
npx wrangler secret put PANEL_PASSWORD
npx wrangler secret put PANEL_SESSION_SECRET
npx wrangler secret put RELAY_TOKEN
npx wrangler deploy
```

## Safety

- Authenticated initial load reads stored state, then performs a read-only device probe.
- `GET /api/state` reads D1 state only.
- `GET /api/device-status` reads the real device shadow.
- `POST /api/device-probe` is read-only for the AC: it tries AWS IoT SearchIndex connectivity, then falls back to reading shadow reported values. It does not change setpoints or publish desired state.
- `POST /api/start`, `/api/phase`, `/api/power`, `/api/swing` send device commands.
- `POST /api/wol/wake` queues a PC wake command for the Android relay.
- `GET /api/wol/status` reads WOL relay and command state.
- `POST /api/relay/ping`, `GET /api/relay/next`, and `POST /api/relay/report` are used by the Android relay and require `RELAY_TOKEN`.
- Device command routes require the device to be online or `Last Known` before sending and wait for reported-state confirmation before updating panel state; command desired state is not cleared on confirmation timeout.
- Cron sends commands only when D1 state has `running=true`.
