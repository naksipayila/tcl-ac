# TCL AC Cloudflare Worker

Serverless version of the TCL AC panel.

## What Runs Here

- Static panel from `public/`.
- API from `src/worker.js`.
- Cycle state in Cloudflare D1.
- Minute cron trigger for phase changes.
- Device commands are sent with AWS IoT MQTT-over-WebSocket publish to the device shadow update topic.
- The panel probes online status on load/login. If AWS connectivity is unavailable but the shadow has usable reported state, the panel shows `Last Known`; controls are disabled only when the device is definitely offline or status cannot be read.
- Secrets in Cloudflare Worker secrets, not in git.

## Required Secrets

- `TCL_SSO_TOKEN` - captured TCL Home token.
- `PANEL_PASSWORD` - panel login password.
- `PANEL_SESSION_SECRET` - random session signing secret.

## Commands

```powershell
npm install
npx wrangler login
npx wrangler d1 create tcl-ac-state
npx wrangler d1 migrations apply tcl-ac-state --remote
npx wrangler secret put TCL_SSO_TOKEN
npx wrangler secret put PANEL_PASSWORD
npx wrangler secret put PANEL_SESSION_SECRET
npx wrangler deploy
```

## Safety

- Visiting the panel only checks login/session.
- `GET /api/state` reads D1 state only.
- `GET /api/device-status` reads the real device shadow.
- `POST /api/device-probe` is read-only for the AC: it tries AWS IoT SearchIndex connectivity, then falls back to reading shadow reported values. It does not change setpoints or publish desired state.
- `POST /api/start`, `/api/phase`, `/api/power`, `/api/swing` send device commands.
- Device command routes require the device to be online or `Last Known` before sending and wait for reported-state confirmation before updating panel state; command desired state is not cleared on confirmation timeout.
- Cron sends commands only when D1 state has `running=true`.
