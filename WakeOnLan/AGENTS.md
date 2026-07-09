# Agent Notes

## Project Shape
- Intended working folder is `WakeOnLan`; `tapo-control` was the older locked copy from before the folder rename.
- Core WOL sender is `wol.py`; it uses only Python stdlib and sends UDP magic packets.
- `phone/` is for direct Android/Termux local-network WOL; `relay/` is for the always-on Android phone web relay behind CGNAT.
- `web/` is the old standalone Cloudflare Worker prototype/reference; the active browser UI/API is integrated under `../cloudflare/`. `relay/cloudflare_wol_relay.py` polls the active Worker and sends local WOL packets.
- Setup/user walkthroughs live in `README.md`, `PHONE.md`, and `WEB.md`; keep those in sync when changing commands or config names.

## Commands
- Syntax check Python: `python -m py_compile .\wol.py .\relay\cloudflare_wol_relay.py`
- Local dry-run for this PC: `python .\wol.py 34:5A:60:4A:8E:47 --broadcast 192.168.1.255 --dry-run`
- Termux local WOL dry-run: `sh phone/wake-pc.sh --dry-run`
- Termux web relay config check/run after `relay/web-config.env` is filled: `sh relay/run-web-relay.sh --check` then `sh relay/run-web-relay.sh`

## Config And Secrets
- The current target PC is configured in `phone/config.env` and `relay/web-config.env`: MAC `34:5A:60:4A:8E:47`, broadcast `192.168.1.255`.
- If the target PC or LAN subnet changes, update phone/relay config files and matching docs/examples.
- `relay/web-config.env` is expected to hold `WOL_WEB_URL` and `WOL_RELAY_TOKEN`; treat it as local secret-bearing config once filled.
- The active Cloudflare Worker uses the main panel login plus `RELAY_TOKEN`; do not write relay tokens into `wrangler.toml` or committed config files.
- Existing user-facing text is ASCII-only to avoid Windows console encoding errors; keep new console output/docs ASCII unless there is a clear reason not to.

## Operational Gotchas
- Mobile browsers cannot send UDP broadcast packets; Android flows require Termux with Python installed.
- CGNAT blocks inbound modem OpenVPN/port-forward approaches here; remote wake is via an always-on Android relay that polls Cloudflare, not directly through the sleeping PC.
- A successful packet send only proves the WOL packet was emitted; actual wake still depends on Ethernet link, BIOS/UEFI WOL/ErP settings, and Windows NIC power settings.
