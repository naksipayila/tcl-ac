# TCL Portable AC Cycle Controller

Local web panel and command-line helper for the TCL `TAC-12CHPB/DM4` portable AC.

The cycle changes the target temperature instead of repeatedly power-cycling the unit:

```text
20 min at 70°F
20 min at 80°F
repeat
```

## Setup

```powershell
py -m pip install -r requirements.txt
```

Set the TCL Home `ssotoken` as a Windows user environment variable:

```powershell
setx TCL_SSO_TOKEN "YOUR_SSOTOKEN_HERE"
```

Open a new terminal after setting the variable.

## Web Panel

Start hidden:

```text
Double-click start_server_hidden.cmd
```

Start with a visible console:

```powershell
py web_app.py --config config.json
```

Open:

```text
http://127.0.0.1:8787/
```

Phones on the same Wi-Fi can use the LAN URL shown in the panel footer. Allow Windows Firewall access if prompted.

The panel supports:

- Start and stop the 70°F / 80°F cycle.
- Manually set compressor target to 70°F or 80°F.
- Toggle AC power with `powerSwitch`.
- Toggle swing with `swingWind`.
- Read the current target temperature on page load and with `Refresh`.
- Close the local server from the panel.

## CLI

Validate config without sending device commands:

```powershell
py tcl_cycle.py validate --config config.json
```

Read device shadow/status:

```powershell
py tcl_cycle.py status --config config.json
```

Send one temperature command:

```powershell
py tcl_cycle.py once cooling --config config.json
py tcl_cycle.py once resting --config config.json
```

Run the cycle:

```powershell
py tcl_cycle.py run --config config.json
```

Use `"backend": "mock"` in `config.json` for dry-run testing without touching the device.

## TCL Home AWS Notes

Commands are sent to AWS IoT Shadow through MQTT-over-WebSocket.

Main payloads:

```json
{"targetCelsiusDegree": 21, "targetFahrenheitDegree": 70}
```

```json
{"targetCelsiusDegree": 26, "targetFahrenheitDegree": 80}
```

```json
{"powerSwitch": 1}
```

```json
{"swingWind": 1}
```

The `ssotoken` expires periodically. Recapture it from TCL Home through HTTP Toolkit when needed.

Logs are written to `logs/tcl_cycle.log`.
