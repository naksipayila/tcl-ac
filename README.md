# TCL Portable AC Cycle Controller

A local web panel and CLI tool for the **`TAC-12CHPB/DM4`** TCL portable air conditioner.

The cycle adjusts the thermostat target rather than repeatedly switching the compressor on and off:

```
20 min at 70°F  →  20 min at 80°F  →  repeat
```

---

## Quick Start

### 1. Install

```powershell
py -m pip install -r requirements.txt
```

### 2. Authenticate

Capture your `ssotoken` from the **TCL Home** mobile app via [HTTP Toolkit](https://httptoolkit.com). Set it once as a Windows user environment variable:

```powershell
setx TCL_SSO_TOKEN "YOUR_SSOTOKEN_HERE"
```

*Open a new terminal after running `setx`.*

### 3. Launch the Panel

Double-click `start-server.cmd` — the server runs silently in the background.

Open your browser:

```
http://127.0.0.1:8787/
```

Phones on the same Wi‑Fi can use the LAN address shown in the panel footer.

---

## Cloudflare Serverless Panel

The `cloudflare/` app runs the panel without keeping your computer on:

- Cloudflare Worker serves the API and static panel.
- Cloudflare D1 stores cycle state.
- A cron trigger checks every minute and switches phase when needed.
- Worker secrets store `TCL_SSO_TOKEN`, `PANEL_PASSWORD`, and `PANEL_SESSION_SECRET`.

Deploy from the `cloudflare/` directory:

```powershell
npm install
npx wrangler login
npx wrangler d1 migrations apply tcl-ac-state --remote
npx wrangler deploy
```

The current Worker URL is:

```
https://tcl-ac.qaliqtaha.workers.dev
```

---

## Web Panel



| Control | Action |
|---------|--------|
| **Start Cycle / Stop** | Begin or pause the 70°F ↔ 80°F loop |
| **Start Compressor / Stop Compressor** | Manually set target to 70°F or 80°F *(disabled when the AC is already at that temperature)* |
| **Power** | Toggle `powerSwitch` — physically turn the AC on or off |
| **Swing** | Toggle `swingWind` — control the louver oscillation |
| **Refresh** | Read the current target temperature directly from the device shadow |
| **Close Server** | Stop the cycle and shut down the local web server |

> **Tip:** Use `"backend": "mock"` in `config.json` for dry‑run testing — nothing is sent to the device.

---

## CLI

All commands run against the same `config.json`:

```powershell
# Validate config (no device commands)
py tcl_cycle.py validate --config config.json

# Read device shadow
py tcl_cycle.py status --config config.json

# Send one command
py tcl_cycle.py once cooling --config config.json    # 70°F
py tcl_cycle.py once resting --config config.json    # 80°F

# Run the continuous 20/20 cycle
py tcl_cycle.py run --config config.json

# Send startup (swing on)
py tcl_cycle.py startup --config config.json
```

---

## How It Works

Commands reach the device through **AWS IoT Shadow** (MQTT‑over‑WebSocket).

The flow:

```
TCL Home API  →  AWS Cognito  →  SigV4‑signed MQTT/WS  →  Device Shadow
```

### Shadow Payloads

| Purpose | JSON |
|---------|------|
| **Set temperature** | `{"targetCelsiusDegree":21, "targetFahrenheitDegree":70}` |
| **Power toggle** | `{"powerSwitch":1}` or `{"powerSwitch":0}` |
| **Swing toggle** | `{"swingWind":1}` or `{"swingWind":0}` |

---

## Files

| File | Role |
|------|------|
| `web_app.py` | Local HTTP server + responsive HTML panel |
| `tcl_cycle.py` | CLI runner + AWS IoT Shadow backend |
| `config.json` | Device ID, cycle timings, API keys |
| `start-server.cmd` | Double‑click launcher (hidden console) |
| `requirements.txt` | `websocket-client>=1.8.0` — the only runtime dependency |
---

## Notes

- The `ssotoken` **expires periodically**. Recapture it from TCL Home through HTTP Toolkit when commands start failing.
- If the room temperature exceeds **80°F**, the compressor may stay on even during the resting phase — this is normal thermostat behaviour.
- The server binds to `0.0.0.0:8787` for LAN access. Allow Windows Firewall if prompted.
- Logs are written to `logs/tcl_cycle.log`.
- Stop a visible‑console server with `Ctrl+C`; stop a hidden server with the **Close Server** button in the panel.
