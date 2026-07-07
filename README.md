# TCL AC Cloudflare Controller

Serverless Cloudflare Worker panel for a TCL `TAC-12CHPB/DM4` portable air conditioner.

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
| Cloudflare D1 | Stores cycle state |
| Cloudflare cron | Checks every minute and switches phase when due |
| Worker secrets | Store `TCL_SSO_TOKEN`, `PANEL_PASSWORD`, `PANEL_SESSION_SECRET` |

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
```

Set or update secrets with:

```powershell
npx wrangler secret put TCL_SSO_TOKEN
npx wrangler secret put PANEL_PASSWORD
npx wrangler secret put PANEL_SESSION_SECRET
```

## Panel Controls

| Control | Action |
|---------|--------|
| `Start Cycle` | Sends 70F cooling and starts the 20/20 loop |
| `Stop Cycle` | Stops stored cycle state; it does not power off the AC |
| `Compressor` | Manually sends 70F or 80F and stops the cycle |
| `Power` | Toggles `powerSwitch` |
| `Swing` | Toggles `swingWind` |
| `Refresh` | Reads the real device shadow |

## Safety Notes

- `GET /api/state` reads D1 state only.
- `GET /api/device-status` reads the real device shadow.
- `POST /api/start`, `/api/power`, `/api/swing`, and `/api/phase` send real device commands.
- `POST /api/stop` only stops the stored cycle state.
- Do not put tokens, cookies, authorization headers, or AWS credentials in git.
