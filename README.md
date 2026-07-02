# TCL Portable AC Cycle Controller

Targets `TAC-12CHPB/DM4` and similar TCL portable ACs by changing the setpoint temperature instead of power cycling the compressor.

Default cycle:

```text
20 min at 70°F
20 min at 80°F
repeat
```

## Quick Test

```powershell
py tcl_cycle.py validate --config config.json
py tcl_cycle.py once cooling --config config.json
py tcl_cycle.py once resting --config config.json
```

Use `"backend": "mock"` in `config.json` for dry-run testing without touching the device.

## Web Panel

```powershell
py -m pip install -r requirements.txt
```

Start the server hidden (no visible window):

```text
Double-click start_server_hidden.cmd
```

Then open `http://127.0.0.1:8787/` in your browser.

### LAN (phone) access

The server binds to `0.0.0.0:8787` by default, so phones on the same Wi-Fi can connect too. The phone URL is shown at the top of the panel as `Phone: http://...:8787/`. Allow Windows Firewall access if prompted.

### Manual start with visible CMD

```powershell
py web_app.py --config config.json
```

## Usage

The browser tab is only a control panel; the 20/20 cycle runs in the background Python web server. Closing the tab does not stop the cycle. Stop the server with `Ctrl+C` (for visible CMD) or the `Close Server` button in the panel.

## Device Connection (TCL Home AWS)

This model uses AWS IoT Shadow for commands. To authenticate:

1. Open TCL Home with HTTP Toolkit and capture:
   ```
   GET https://eu-iot-api-prod.tcljd.com/v1/auth/service/loadBalance
   ```
2. Copy the `ssotoken` header and set it as an environment variable:
   ```powershell
   setx TCL_SSO_TOKEN "YOUR_SSOTOKEN_HERE"
   ```
3. Open a new PowerShell window and test:
   ```powershell
   py tcl_cycle.py status --config config.json
   ```

Command payloads:

```json
{
  "state": {
    "desired": {
      "targetCelsiusDegree": 21,
      "targetFahrenheitDegree": 70
    }
  }
}
```

```json
{
  "state": {
    "desired": {
      "targetCelsiusDegree": 26,
      "targetFahrenheitDegree": 80
    }
  }
}
```

Swing startup command:

```json
{
  "state": {
    "desired": {
      "swingWind": 1
    }
  }
}
```

Commands are sent via MQTT-over-WebSocket by default (`"command_method": "mqtt_ws"`). REST fallback options: `"shadow_update"`, `"topic_publish"`.

The `ssotoken` expires periodically — recapture it from TCL Home through HTTP Toolkit when needed.

## Notes

- The tool does not power off the AC; it only changes the target between `70°F` and `80°F`.
- If the room is above `80°F` the compressor may continue running even during the resting phase. This is thermostat behaviour.
- Logs are written to `logs/tcl_cycle.log`.
