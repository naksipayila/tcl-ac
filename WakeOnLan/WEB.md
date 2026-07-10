# Wake-on-LAN In Home Control Panel

Wake-on-LAN is now integrated into the main Cloudflare Home Control panel.
Do not deploy `WakeOnLan/web` as a separate Worker for the live app.

Live panel URL:

```text
https://tcl-ac.qaliqtaha.workers.dev
```

Flow:

```text
Browser -> Home Control Worker -> old Android phone relay -> local network magic packet -> PC wakes up
```

Cloudflare and the browser cannot send Wake-on-LAN UDP broadcast packets directly. The Android/Termux relay is still required because it is inside the same local network as the PC.

## Active Files

- `../cloudflare/src/worker.js`: main Worker API for AC and Wake-on-LAN.
- `../cloudflare/public/index.html`: browser panel with AC and PC tabs.
- `relay/cloudflare_wol_relay.py`: Android/Termux relay that polls the Worker.
- `relay/run-web-relay.sh`: Termux runner for the web relay.
- `relay/install-termux-boot-web.sh`: optional Termux:Boot startup installer.
- `relay/web-config.example.env`: relay config template.

`web/` is an old standalone prototype/reference; the active app is under `../cloudflare/`.

## Cloudflare Requirements

The active Worker needs:

- Cloudflare D1 binding for command and relay heartbeat state.
- `WOL_STATE` KV is only a legacy read fallback while it remains configured.
- `RELAY_TOKEN` Cloudflare secret for the Android relay.
- Existing panel auth secrets: `PANEL_PASSWORD` and `PANEL_SESSION_SECRET`.

The browser uses the normal Home Control panel login. There is no separate `ADMIN_PIN` for Wake-on-LAN anymore.

Set the relay token from the `cloudflare` folder if it is not already set:

```powershell
npx wrangler secret put RELAY_TOKEN
```

Do not put `RELAY_TOKEN` into `wrangler.toml` or any committed file.

## Configure The Android Relay

Copy the project folder to the old Android phone and open Termux in the project directory.

Install Python if needed:

```sh
pkg update
pkg install python termux-api
termux-setup-storage
```

Create the web relay config:

```sh
cp relay/web-config.example.env relay/web-config.env
nano relay/web-config.env
```

Set these values:

```sh
WOL_WEB_URL=https://tcl-ac.qaliqtaha.workers.dev
WOL_RELAY_TOKEN=PASTE_THE_SAME_RELAY_TOKEN_HERE
```

The current PC settings are already in the example:

```sh
WOL_MAC=34:5A:60:4A:8E:47
WOL_BROADCAST=192.168.1.255
```

## Test The Relay

Check the local relay config:

```sh
sh relay/run-web-relay.sh --check
```

Ping the Cloudflare Worker with the relay token:

```sh
sh relay/run-web-relay.sh --ping
```

Run the relay:

```sh
sh relay/run-web-relay.sh
```

Open the Home Control panel, log in, switch to the `PC` tab, and press `Wake PC`.

## Dry Run

To test the full web flow without sending the WOL packet:

```sh
sh relay/run-web-relay.sh --dry-run
```

The panel should show the command as succeeded with a dry-run message.

## Automatic Startup

Install Termux:Boot from F-Droid, then run:

```sh
sh relay/install-termux-boot-web.sh
```

Disable battery optimization for Termux and Termux:Boot. Keep the old phone plugged in and connected to the home Wi-Fi.

## Security Notes

- Use a strong Home Control panel password.
- Use a long random `RELAY_TOKEN`; it protects the relay API.
- Keep `relay/web-config.env` private because it contains the relay token.
- The old Android phone must not be on a guest Wi-Fi network.
- No router port forwarding is required.
