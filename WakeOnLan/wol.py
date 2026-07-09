#!/usr/bin/env python3
"""Small Wake-on-LAN sender for the local network."""

from __future__ import annotations

import argparse
import re
import socket
import sys
import time


DEFAULT_BROADCAST = "255.255.255.255"
DEFAULT_PORT = 9


def normalize_mac(value: str) -> str:
    mac = re.sub(r"[^0-9A-Fa-f]", "", value)
    if len(mac) != 12 or not re.fullmatch(r"[0-9A-Fa-f]{12}", mac):
        raise ValueError("MAC address must be 12 hex characters, example: AA:BB:CC:DD:EE:FF")
    return mac.upper()


def build_magic_packet(mac: str) -> bytes:
    mac_bytes = bytes.fromhex(mac)
    return b"\xff" * 6 + mac_bytes * 16


def send_wol(mac: str, broadcast: str, port: int, repeat: int, delay: float, dry_run: bool) -> None:
    packet = build_magic_packet(mac)

    if dry_run:
        print(f"Ready: {format_mac(mac)} -> {broadcast}:{port} ({repeat} packets, not sent)")
        return

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for index in range(repeat):
            sock.sendto(packet, (broadcast, port))
            if index < repeat - 1:
                time.sleep(delay)

    print(f"Sent: {format_mac(mac)} -> {broadcast}:{port} ({repeat} packets)")


def format_mac(mac: str) -> str:
    return ":".join(mac[index : index + 2] for index in range(0, 12, 2))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Wake a computer on the same home network with Wake-on-LAN."
    )
    parser.add_argument("mac", help="MAC address of the computer to wake")
    parser.add_argument(
        "--broadcast",
        default=DEFAULT_BROADCAST,
        help=f"Broadcast address. Default: {DEFAULT_BROADCAST}",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"UDP port. Usually 9 or 7. Default: {DEFAULT_PORT}",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=3,
        help="How many times to send the magic packet. Default: 3",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.2,
        help="Delay between repeats. Default: 0.2 seconds",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check settings without sending the packet.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    if args.repeat < 1:
        print("Error: --repeat must be at least 1", file=sys.stderr)
        return 2
    if not 1 <= args.port <= 65535:
        print("Error: --port must be between 1 and 65535", file=sys.stderr)
        return 2
    if args.delay < 0:
        print("Error: --delay cannot be negative", file=sys.stderr)
        return 2

    try:
        mac = normalize_mac(args.mac)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    try:
        send_wol(mac, args.broadcast, args.port, args.repeat, args.delay, args.dry_run)
    except OSError as exc:
        print(f"Could not send: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
