#!/usr/bin/env python3
"""Cloudflare web-app controlled Wake-on-LAN relay for Android/Termux."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from wol import normalize_mac, send_wol  # noqa: E402


DEFAULT_CONFIG = Path(__file__).resolve().with_name("web-config.env")
DEFAULT_BROADCAST = "255.255.255.255"
DEFAULT_PORT = 9
DEFAULT_REPEAT = 3
DEFAULT_DELAY = 0.2
DEFAULT_POLL_SECONDS = 3.0
DEFAULT_TIMEOUT_SECONDS = 20.0


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def config_value(values: dict[str, str], name: str, default: str = "") -> str:
    return os.environ.get(name, values.get(name, default)).strip()


def config_int(values: dict[str, str], name: str, default: int) -> int:
    raw = config_value(values, name, str(default))
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def config_float(values: dict[str, str], name: str, default: float) -> float:
    raw = config_value(values, name, str(default))
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def config_bool(values: dict[str, str], name: str, default: bool = False) -> bool:
    raw = config_value(values, name, "1" if default else "0").lower()
    return raw in {"1", "true", "yes", "on"}


def load_config(config_path: Path) -> dict[str, Any]:
    values = read_env_file(config_path)

    web_url = config_value(values, "WOL_WEB_URL").rstrip("/")
    if not web_url or web_url.startswith("https://your-worker"):
        raise ValueError("WOL_WEB_URL is not set")

    relay_token = config_value(values, "WOL_RELAY_TOKEN")
    if not relay_token or relay_token == "PASTE_RELAY_TOKEN_HERE":
        raise ValueError("WOL_RELAY_TOKEN is not set")

    raw_mac = config_value(values, "WOL_MAC")
    if not raw_mac:
        raise ValueError("WOL_MAC is not set")

    mac = normalize_mac(raw_mac)
    port = config_int(values, "WOL_PORT", DEFAULT_PORT)
    repeat = config_int(values, "WOL_REPEAT", DEFAULT_REPEAT)
    delay = config_float(values, "WOL_DELAY", DEFAULT_DELAY)
    poll_seconds = config_float(values, "WOL_POLL_SECONDS", DEFAULT_POLL_SECONDS)
    timeout_seconds = config_float(values, "WOL_REQUEST_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)

    if not 1 <= port <= 65535:
        raise ValueError("WOL_PORT must be between 1 and 65535")
    if repeat < 1:
        raise ValueError("WOL_REPEAT must be at least 1")
    if delay < 0:
        raise ValueError("WOL_DELAY cannot be negative")
    if poll_seconds <= 0:
        raise ValueError("WOL_POLL_SECONDS must be positive")
    if timeout_seconds <= 0:
        raise ValueError("WOL_REQUEST_TIMEOUT must be positive")

    return {
        "web_url": web_url,
        "relay_token": relay_token,
        "mac": mac,
        "broadcast": config_value(values, "WOL_BROADCAST", DEFAULT_BROADCAST) or DEFAULT_BROADCAST,
        "port": port,
        "repeat": repeat,
        "delay": delay,
        "poll_seconds": poll_seconds,
        "timeout_seconds": timeout_seconds,
        "dry_run": config_bool(values, "WOL_DRY_RUN", False),
    }


def request_json(
    config: dict[str, Any],
    path: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = None
    headers = {
        "Authorization": f"Bearer {config['relay_token']}",
        "User-Agent": "WakeOnLan-Web-Relay/1.0",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        f"{config['web_url']}{path}",
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(request, timeout=config["timeout_seconds"]) as response:
            raw_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc

    if not raw_body.strip():
        return {}
    result = json.loads(raw_body)
    if not isinstance(result, dict):
        raise RuntimeError(f"Unexpected API response: {result!r}")
    return result


def report_result(config: dict[str, Any], command_id: str, ok: bool, message: str) -> None:
    request_json(
        config,
        "/api/relay/report",
        method="POST",
        payload={"id": command_id, "ok": ok, "message": message},
    )


def handle_command(config: dict[str, Any], command: dict[str, Any]) -> None:
    command_id = str(command.get("id") or "")
    action = command.get("action")
    if not command_id:
        raise RuntimeError("Relay command is missing an id")
    if action != "wake":
        report_result(config, command_id, False, f"Unknown action: {action}")
        return

    try:
        send_wol(
            config["mac"],
            config["broadcast"],
            config["port"],
            config["repeat"],
            config["delay"],
            dry_run=config["dry_run"],
        )
    except Exception as exc:  # noqa: BLE001 - report the failure to the web app.
        report_result(config, command_id, False, f"Could not send WOL: {exc}")
        return

    if config["dry_run"]:
        report_result(config, command_id, True, "Dry run complete; WOL packet was not sent.")
    else:
        report_result(config, command_id, True, "WOL packet sent.")


def run_once(config: dict[str, Any]) -> bool:
    response = request_json(config, "/api/relay/next")
    command = response.get("command")
    if not command:
        return False
    if not isinstance(command, dict):
        raise RuntimeError(f"Unexpected command payload: {command!r}")
    handle_command(config, command)
    return True


def run_loop(config: dict[str, Any]) -> None:
    print("Cloudflare WOL relay is running. Waiting for web commands.")
    print(f"Worker: {config['web_url']}")
    if config["dry_run"]:
        print("Dry run is enabled; WOL packets will not be sent.")

    while True:
        try:
            response = request_json(config, "/api/relay/next")
            command = response.get("command")
            if isinstance(command, dict):
                handle_command(config, command)
            poll_seconds = float(response.get("pollAfter") or config["poll_seconds"])
            time.sleep(max(0.5, poll_seconds))
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"Connection error: {exc}; retrying.", file=sys.stderr)
            time.sleep(config["poll_seconds"])
        except KeyboardInterrupt:
            print("Stopped.")
            return
        except Exception as exc:  # noqa: BLE001 - keep the relay alive.
            print(f"Error: {exc}; retrying.", file=sys.stderr)
            time.sleep(config["poll_seconds"])


def print_check(config: dict[str, Any]) -> None:
    print(f"Worker: {config['web_url']}")
    print(f"Relay token: {'set' if config['relay_token'] else 'missing'}")
    print(f"Poll interval: {config['poll_seconds']}s")
    print(f"Dry run: {'yes' if config['dry_run'] else 'no'}")
    send_wol(config["mac"], config["broadcast"], config["port"], config["repeat"], config["delay"], dry_run=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cloudflare web-app controlled Wake-on-LAN relay.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Web relay config file path")
    parser.add_argument("--check", action="store_true", help="Check local config and do not start polling")
    parser.add_argument("--ping", action="store_true", help="Ping the Cloudflare Worker and exit")
    parser.add_argument("--once", action="store_true", help="Poll once and exit")
    parser.add_argument("--dry-run", action="store_true", help="Do not send WOL packets when commands arrive")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    try:
        config = load_config(args.config)
    except Exception as exc:  # noqa: BLE001 - CLI validation message.
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        config["dry_run"] = True

    if args.check:
        print_check(config)
        return 0

    if args.ping:
        try:
            response = request_json(config, "/api/relay/ping", method="POST")
        except Exception as exc:  # noqa: BLE001 - CLI validation message.
            print(f"Ping failed: {exc}", file=sys.stderr)
            return 1
        print(f"Ping OK. Server time: {response.get('serverTime', 'unknown')}")
        return 0

    if args.once:
        try:
            handled = run_once(config)
        except Exception as exc:  # noqa: BLE001 - CLI validation message.
            print(f"Poll failed: {exc}", file=sys.stderr)
            return 1
        print("Command handled." if handled else "No command pending.")
        return 0

    run_loop(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
