# Home Control

Serverless Cloudflare Worker panel for a TCL air conditioner and PC Wake-on-LAN.

The cycle adjusts the thermostat target instead of repeatedly switching the compressor on and off:

```text
20 min at 70F -> 20 min at 80F -> repeat
```

## Live Panel

```text
https://tcl-ac.qaliqtaha.workers.dev
```

The panel is protected by a Cloudflare Worker HttpOnly session cookie.

## Architecture

| Part | Role |
|------|------|
| `cloudflare/public/index.html` | Static frontend panel |
| `cloudflare/src/worker.js` | API, auth, AWS/TCL integration, cron handler |
| Cloudflare D1 | Stores AC controller, login-rate, and WOL relay state |
| Android/Termux relay | Sends PC wake packets on the local network |
| Cloudflare cron | Checks every minute and switches phase when due |
| Worker secrets | Store `TCL_SSO_TOKEN`, `PANEL_PASSWORD`, `PANEL_SESSION_SECRET`, `RELAY_TOKEN` |

Device commands use TCL Home auth, AWS Cognito credentials, SigV4, and AWS IoT MQTT-over-WebSocket publish to the device shadow update topic.

## Deploy

Run from `cloudflare/`:

```powershell
npm install
npx wrangler login
npx wrangler d1 migrations apply tcl-ac-state --remote
npx wrangler deploy
```

Required Cloudflare secrets:

```text
TCL_SSO_TOKEN
PANEL_PASSWORD
PANEL_SESSION_SECRET
RELAY_TOKEN
```

Set or update secrets with:

```powershell
npx wrangler secret put TCL_SSO_TOKEN
npx wrangler secret put PANEL_PASSWORD
npx wrangler secret put PANEL_SESSION_SECRET
npx wrangler secret put RELAY_TOKEN
```

## Panel Controls

| Control | Action |
|---------|--------|
| `Start Cycle` | Sends 70F cooling and starts the 20/20 loop |
| `Stop Cycle` | Stops stored cycle state; it does not power off the AC |
| `Compressor` | Manually sends 70F or 80F and stops the cycle |
| `Power` | Toggles `powerSwitch` |
| `Swing` | Toggles `swingWind` |
| `Wake` | Queues a PC wake command for the Android relay |

The panel probes device online status on load/login. If AWS connectivity is unavailable but the shadow has usable reported state, the panel shows `Last Known`; controls stay disabled only when the device is definitely offline or status cannot be read.

## Safety Notes

- `GET /api/state` reads D1 state only.
- `GET /api/device-status` reads the real device shadow and persists D1 state.
- `POST /api/device-probe` is read-only for the AC: it tries AWS IoT SearchIndex connectivity, then falls back to reading shadow reported values. It does not change setpoints or publish desired state.
- `POST /api/start`, `/api/power`, `/api/swing`, and `/api/phase` send real device commands.
- Device command routes require the device to be online or `Last Known` before sending and wait for reported-state confirmation before updating panel state; command desired state is not cleared on confirmation timeout.
- `POST /api/stop` only stops the stored cycle state.
- PC wake uses `Browser -> Worker -> Android relay -> LAN magic packet`; the Worker and browser cannot send LAN UDP directly.
- Do not put tokens, cookies, authorization headers, or AWS credentials in git.
