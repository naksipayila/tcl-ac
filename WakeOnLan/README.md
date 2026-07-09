# Wake-on-LAN Tool

This small tool sends a Wake-on-LAN magic packet to a computer on the same home network.
The local sender does not require internet access, port forwarding, or remote desktop access.

For the browser UI that works from outside the home network, use the main Home Control panel and see `WEB.md`.
For Android/Termux phone usage, see `PHONE.md`.
The current PC MAC address is already written to `phone/config.env`; on the phone, `sh phone/wake-pc.sh` is enough.

## Usage

```powershell
python .\wol.py AA:BB:CC:DD:EE:FF
```

You can find the target PC MAC address on Windows with this command:

```powershell
ipconfig /all
```

The value on the `Physical Address` line is the MAC address.

## Examples

Send with the default local broadcast address:

```powershell
python .\wol.py AA:BB:CC:DD:EE:FF
```

If your router network is `192.168.1.x`, send with a specific broadcast address:

```powershell
python .\wol.py AA:BB:CC:DD:EE:FF --broadcast 192.168.1.255
```

Check the settings without sending:

```powershell
python .\wol.py AA:BB:CC:DD:EE:FF --dry-run
```

## Web UI

The web UI is integrated into the main Cloudflare Home Control panel and uses an always-on Android/Termux relay inside the home network.

```text
Browser -> Home Control Worker -> Android relay -> WOL packet -> PC
```

Start with `WEB.md` if you want to configure the relay for the panel's `PC` tab.

## Target PC Requirements

- The PC must be connected with an Ethernet cable.
- `Wake on LAN`, `Power On by PCI-E`, or a similar BIOS/UEFI option must be enabled.
- `ErP`, if present, should be disabled.
- In Windows Device Manager, `Wake on Magic Packet` must be enabled for the network adapter.
- In the Power Management tab, allow the network adapter to wake the computer.
