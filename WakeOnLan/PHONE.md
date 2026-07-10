# Wake-on-LAN From A Phone

This setup runs on an Android phone with Termux. The phone and the target PC must be on the same Wi-Fi/local network.

Sending a magic packet directly from a browser is not possible because mobile browsers cannot send UDP broadcast packets. That is why the command runs through Termux.

Create the local configuration from `phone/config.example.env`, then run:

```sh
cp phone/config.example.env phone/config.env
nano phone/config.env
```

After entering the project directory in Termux, run:

```sh
sh phone/wake-pc.sh
```

More readable alternative:

```sh
sh phone/wake-my-pc.sh
```

## Android Termux Setup

Install Termux from F-Droid. The Play Store version can be outdated.

Install Python inside Termux:

```sh
pkg update
pkg install python
```

After copying this folder to the phone, enter the project directory and run:

```sh
sh phone/wake-pc.sh
```

You can also pass the MAC address manually:

```sh
sh phone/wake-pc.sh AA:BB:CC:DD:EE:FF
```

To test without sending:

```sh
sh phone/wake-pc.sh --dry-run
```

## Write The MAC Address To Config

To configure this PC or another computer:

```sh
cp phone/config.example.env phone/config.env
nano phone/config.env
```

Replace the `WOL_MAC` line with the computer MAC address:

```sh
WOL_MAC=AA:BB:CC:DD:EE:FF
```

Then just run:

```sh
sh phone/wake-pc.sh
```

## Broadcast Address

The default address works on most home networks:

```sh
255.255.255.255
```

If it does not work, try a specific broadcast address for your router network:

```sh
sh phone/wake-pc.sh --broadcast 192.168.1.255
```

If your network is `192.168.0.x`:

```sh
sh phone/wake-pc.sh --broadcast 192.168.0.255
```

## One Tap From The Home Screen

If you installed the Termux:Widget app, you can create a shortcut:

```sh
sh phone/install-termux-widget.sh
```

Then add Termux:Widget to the Android home screen and select the `Wake-PC` shortcut.

## Target PC Requirements

- The PC must be connected with an Ethernet cable.
- Wake-on-LAN must be enabled in BIOS/UEFI.
- `Wake on Magic Packet` must be enabled on the Windows network adapter.
- Windows power management must allow the network adapter to wake the computer.
