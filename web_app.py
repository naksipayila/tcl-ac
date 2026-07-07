from __future__ import annotations

import argparse
import json
import logging
import os
import pathlib
import queue
import socket
import sys
import threading
import time
import traceback
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from tcl_cycle import (
    CONFIG_DEFAULT,
    BackendError,
    ConfigError,
    create_backend,
    get_cycle_config,
    load_config,
    setup_logging,
)


DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8787
LOCAL_BROWSER_HOST = "127.0.0.1"
FAVICON_PATH = pathlib.Path(__file__).with_name("favicon.png")


def browser_url(host: str, port: int) -> str:
    if host in {"0.0.0.0", "::", ""}:
        return f"http://{LOCAL_BROWSER_HOST}:{port}/"
    return f"http://{host}:{port}/"


def local_network_ips() -> list[str]:
    ips: set[str] = set()
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if ip and not ip.startswith("127."):
                ips.add(ip)
    except OSError:
        pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
            udp_socket.connect(("8.8.8.8", 80))
            ip = udp_socket.getsockname()[0]
            if ip and not ip.startswith("127."):
                ips.add(ip)
    except OSError:
        pass

    return sorted(ips)


def network_urls(host: str, port: int) -> list[str]:
    if host in {"0.0.0.0", "::", ""}:
        return [f"http://{ip}:{port}/" for ip in local_network_ips()]
    if host not in {"127.0.0.1", "localhost"}:
        return [f"http://{host}:{port}/"]
    return []


PAGE_HTML = r"""<!doctype html>
<html class="dark" lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TCL AC Control</title>
<link rel="icon" type="image/png" href="/favicon.png">
<link rel="shortcut icon" type="image/png" href="/favicon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;900&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet">
<style>
  .material-symbols-outlined {
    font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 20;
    font-size: 20px;
  }

  ::-webkit-scrollbar { width: 4px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: #2a2a2a; border-radius: 2px; }

  *,
  *::before,
  *::after {
    box-sizing: border-box;
  }

  :root {
    --page-bg: #080808;
    --panel-bg: rgba(16, 16, 16, 0.94);
    --panel-border: rgba(255, 255, 255, 0.12);
    --card-bg: rgba(255, 255, 255, 0.04);
    --card-bg-strong: rgba(255, 255, 255, 0.068);
    --card-border: rgba(255, 255, 255, 0.12);
    --text-main: #f5f5f5;
    --text-soft: #c9c9c9;
    --text-muted: #8b8b8b;
    --accent-main: #f4f4f4;
    --accent-soft: #b7b7b7;
    --accent-contrast: #090909;
  }

  body {
    min-height: 100vh;
    min-height: 100dvh;
    margin: 0;
    display: grid;
    place-items: center;
    padding: 22px;
    font-family: 'Inter', sans-serif;
    color: var(--text-main);
    overflow-x: hidden;
    overflow-y: auto;
    background:
      radial-gradient(circle at 50% -18%, rgba(255, 255, 255, 0.1), transparent 32%),
      radial-gradient(circle at 92% 6%, rgba(255, 255, 255, 0.045), transparent 26%),
      linear-gradient(180deg, #0b0b0b 0%, var(--page-bg) 56%, #030303 100%);
  }

  button,
  a {
    font: inherit;
    -webkit-tap-highlight-color: transparent;
  }

  button {
    appearance: none;
    margin: 0;
  }

  button:not(:disabled),
  [role="button"],
  .footer-link {
    cursor: pointer;
  }

  .app-shell {
    width: min(100%, 600px);
    padding: 32px 18px;
    border: 1px solid var(--panel-border);
    border-radius: 16px;
    background:
      linear-gradient(180deg, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0.018) 42%, rgba(255, 255, 255, 0.026)),
      var(--panel-bg);
    box-shadow: 0 22px 70px rgba(0, 0, 0, 0.58), inset 0 1px 0 rgba(255, 255, 255, 0.07);
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
  }

  .hero-card {
    width: 100%;
    max-width: 520px;
    margin: 0 auto;
    padding: 16px;
    border: 1px solid var(--card-border);
    border-radius: 12px;
    background:
      linear-gradient(180deg, rgba(255, 255, 255, 0.064), rgba(255, 255, 255, 0.024));
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
  }

  .controls-card {
    width: 100%;
    max-width: 520px;
    margin: 12px auto 0;
    padding: 14px;
    border: 1px solid var(--card-border);
    border-radius: 12px;
    background:
      linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.018)),
      rgba(0, 0, 0, 0.12);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
  }

  .hero-footer,
  .footer-row,
  .control-row {
    display: flex;
    align-items: center;
  }

  .hero-footer,
  .footer-row,
  .control-row {
    justify-content: space-between;
  }

  .metric-label,
  .section-label,
  .control-meta,
  .footer-link {
    color: var(--text-muted);
  }

  .metric-label,
  .section-label {
    margin: 0;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.13em;
    text-transform: uppercase;
  }

  .temperature {
    flex: 0 0 auto;
    margin: 0;
    font-size: clamp(36px, 10vw, 54px);
    font-weight: 780;
    letter-spacing: -0.06em;
    line-height: 0.92;
  }

  .hero-footer {
    gap: 12px;
  }

  .metric-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
    flex: 1;
    min-width: 0;
  }

  .metric-value {
    display: block;
    margin-top: 3px;
    overflow: hidden;
    color: var(--text-main);
    font-size: 14px;
    font-weight: 700;
    letter-spacing: -0.02em;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .metric-item {
    min-width: 0;
  }

  .refresh-button {
    flex: 0 0 auto;
    min-height: 34px;
    padding: 0 11px;
    border: 1px solid var(--card-border);
    border-radius: 9px;
    background: rgba(255, 255, 255, 0.05);
    color: var(--text-soft);
    font-size: 11px;
    font-weight: 700;
    transition: background 0.18s ease, border-color 0.18s ease, color 0.18s ease, transform 0.18s ease;
  }

  .refresh-button:hover,
  .control-row:hover,
  .footer-toggle:hover,
  .restart-button:hover,
  .utility-button:hover {
    border-color: rgba(255, 255, 255, 0.18);
    background: rgba(255, 255, 255, 0.085);
  }

  .action-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }

  .hero-card .action-grid {
    margin-top: 10px;
  }

  .action-button {
    width: 100%;
    min-height: 56px;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 10px;
    border: 1px solid transparent;
    border-radius: 10px;
    text-align: center;
    transition: transform 0.18s ease, opacity 0.18s ease, background 0.18s ease, border-color 0.18s ease;
  }

  .action-label,
  .control-title {
    display: block;
    color: var(--text-main);
    font-size: 15px;
    font-weight: 750;
    letter-spacing: -0.01em;
  }

  .action-label {
    font-size: 13px;
  }

  .action-button small,
  .control-meta {
    display: block;
    margin-top: 5px;
    font-size: 12px;
    line-height: 1.35;
  }

  .action-primary {
    background: linear-gradient(135deg, rgba(238, 238, 238, 0.95), rgba(168, 168, 168, 0.84));
    color: var(--accent-contrast);
    box-shadow: 0 10px 30px rgba(255, 255, 255, 0.1);
  }

  .action-primary .action-label {
    color: var(--accent-contrast);
  }

  .action-quiet,
  .control-row,
  .utility-button,
  .footer-link {
    border: 1px solid var(--card-border);
    background: var(--card-bg);
  }

  .action-quiet {
    color: var(--text-soft);
  }

  .action-quiet .action-label {
    color: var(--text-soft);
  }

  .action-button:active:not(:disabled),
  .control-row:active:not(:disabled),
  .power-slider:active:not(.is-busy),
  .refresh-button:active,
  .footer-toggle:active,
  .restart-button:active,
  .utility-button:active {
    transform: scale(0.985);
  }

  .action-button:disabled,
  .control-row:disabled,
  .control-row.is-disabled,
  .dashboard-button:disabled {
    opacity: 0.42;
    cursor: not-allowed;
    transform: none;
    filter: grayscale(0.2);
  }

  .control-row.is-disabled {
    pointer-events: none;
  }

  .control-row.is-sending {
    cursor: wait;
    opacity: 0.72;
    pointer-events: none;
  }

  .section-label {
    margin: 14px 2px 8px;
  }

  .controls-card > .section-label:first-child {
    margin-top: 0;
  }

  .control-list {
    display: grid;
    gap: 8px;
  }

  .control-row {
    width: 100%;
    min-height: 58px;
    gap: 12px;
    padding: 12px 14px;
    border-radius: 9px;
    color: inherit;
    text-align: left;
    cursor: pointer;
    transition: transform 0.18s ease, opacity 0.18s ease, background 0.18s ease, border-color 0.18s ease;
  }

  .control-copy {
    min-width: 0;
  }

  .control-text {
    min-width: 0;
  }

  .control-value {
    flex: 0 0 auto;
    color: var(--text-soft);
    font-size: 14px;
    font-weight: 750;
  }

  .control-value.cool {
    color: var(--accent-main);
  }

  .control-value.warm {
    color: var(--accent-soft);
  }

  .switch {
    position: relative;
    flex: 0 0 auto;
    width: 40px;
    height: 22px;
  }

  .switch-input {
    position: absolute;
    inset: 0;
    opacity: 0;
    pointer-events: none;
  }

  .switch-slider {
    position: absolute;
    inset: 0;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.12);
    transition: background 0.18s ease, border-color 0.18s ease;
  }

  .switch-slider::after {
    content: '';
    position: absolute;
    top: 3px;
    left: 3px;
    width: 14px;
    height: 14px;
    border-radius: 999px;
    background: #fff;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.28);
    transition: transform 0.18s ease;
  }

  .switch-input:checked + .switch-slider {
    border-color: rgba(255, 255, 255, 0.36);
    background: linear-gradient(135deg, rgba(245, 245, 245, 0.92), rgba(168, 168, 168, 0.78));
  }

  .switch-input:checked + .switch-slider::after {
    transform: translateX(18px);
  }

  .power-slider {
    --power-knob-inset: 5px;
    --power-knob-size: 40px;
    --power-progress: 0;
    position: relative;
    width: 100%;
    min-width: 0;
    min-height: 58px;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    padding: 0 14px 0 52px;
    border: 1px solid var(--card-border);
    border-radius: 9px;
    background: var(--card-bg);
    color: var(--text-main);
    cursor: default;
    isolation: isolate;
    touch-action: pan-y;
    user-select: none;
    transition: transform 0.18s ease, opacity 0.18s ease, background 0.18s ease, border-color 0.18s ease;
  }

  .power-slider::before {
    content: '';
    position: absolute;
    inset: 0;
    z-index: 0;
    border-radius: inherit;
    background: linear-gradient(135deg, rgba(255, 255, 255, 0.26), rgba(150, 150, 150, 0.2));
    opacity: 0.75;
    transform: scaleX(var(--power-progress));
    transform-origin: left center;
    transition: transform 0.2s ease;
  }

  .power-slider.power-on {
    border-color: rgba(255, 255, 255, 0.24);
    background: rgba(255, 255, 255, 0.07);
  }

  .power-slider.power-on::before {
    background: linear-gradient(135deg, rgba(210, 210, 210, 0.26), rgba(95, 95, 95, 0.22));
  }

  .power-slider.power-off {
    border-color: rgba(255, 255, 255, 0.15);
    background: rgba(255, 255, 255, 0.045);
  }

  .power-slider.is-dragging {
    cursor: grabbing;
  }

  .power-slider.is-confirm-ready {
    border-color: rgba(255, 255, 255, 0.34);
  }

  .power-slider.power-on.is-confirm-ready {
    border-color: rgba(255, 255, 255, 0.42);
  }

  .power-slider.is-busy {
    cursor: wait;
    opacity: 0.72;
    pointer-events: none;
  }

  .power-slider:focus-visible {
    outline: 2px solid rgba(255, 255, 255, 0.5);
    outline-offset: 3px;
  }

  .power-slider.is-dragging::before,
  .power-slider.is-dragging .power-slider-knob {
    transition: none;
  }

  .power-slider-label {
    position: relative;
    z-index: 1;
    min-width: 0;
    overflow: hidden;
    color: var(--text-soft);
    font-size: 12px;
    font-weight: 750;
    letter-spacing: -0.01em;
    text-align: center;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .power-slider.is-confirm-ready .power-slider-label {
    color: var(--text-main);
  }

  .power-slider-knob {
    position: absolute;
    top: 50%;
    display: grid;
    place-items: center;
    border-radius: 8px;
    transform: translateY(-50%);
  }

  .power-slider-knob {
    left: var(--power-knob-inset);
    z-index: 3;
    width: var(--power-knob-size);
    height: var(--power-knob-size);
    color: var(--accent-contrast);
    cursor: grab;
    background: linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(178, 178, 178, 0.9));
    box-shadow: 0 8px 22px rgba(255, 255, 255, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.38);
    transition: transform 0.2s ease, background 0.18s ease, box-shadow 0.18s ease;
  }

  .power-slider.power-on .power-slider-knob {
    color: var(--text-main);
    background: linear-gradient(135deg, rgba(82, 82, 82, 0.98), rgba(36, 36, 36, 0.92));
    box-shadow: 0 8px 22px rgba(0, 0, 0, 0.34), inset 0 1px 0 rgba(255, 255, 255, 0.18);
  }

  .power-slider.is-dragging .power-slider-knob {
    cursor: grabbing;
  }

  .footer-row {
    gap: 8px;
    margin-top: 12px;
  }

  .footer-row.is-hidden {
    display: none;
  }

  .footer-toggle-wrap {
    display: flex;
    justify-content: center;
    margin-top: 12px;
  }

  .footer-toggle {
    width: 28px;
    min-width: 0;
    min-height: 24px;
    display: grid;
    place-items: center;
    padding: 0;
    border: 1px solid var(--card-border);
    border-radius: 7px;
    background: var(--card-bg);
    color: var(--text-soft);
    transition: transform 0.18s ease, background 0.18s ease, border-color 0.18s ease;
  }

  .footer-toggle::before {
    content: '';
    width: 6px;
    height: 6px;
    border-right: 1.5px solid currentColor;
    border-bottom: 1.5px solid currentColor;
    transform: translateY(-2px) rotate(45deg);
    transition: transform 0.18s ease;
  }

  .footer-toggle[aria-expanded="true"]::before {
    transform: translateY(2px) rotate(225deg);
  }

  .utility-button,
  .restart-button,
  .footer-link {
    min-height: 42px;
    border-radius: 9px;
  }

  .utility-button,
  .restart-button {
    flex: 0 0 auto;
    min-width: 112px;
    padding: 0 12px;
    font-size: 12px;
    font-weight: 750;
    transition: transform 0.18s ease, background 0.18s ease, border-color 0.18s ease;
  }

  .utility-button {
    color: var(--accent-soft);
  }

  .footer-link {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0 12px;
    overflow: hidden;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 11px;
    text-decoration: none;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .restart-button {
    border: 1px solid rgba(255, 255, 255, 0.16);
    background: rgba(255, 255, 255, 0.055);
    color: var(--accent-main);
    transition: transform 0.18s ease, background 0.18s ease, border-color 0.18s ease, opacity 0.18s ease;
  }

  .restart-button:disabled {
    cursor: wait;
    opacity: 0.58;
    transform: none;
  }

  .shutdown-card {
    width: min(100%, 360px);
    padding: 24px;
    border: 1px solid var(--panel-border);
    border-radius: 16px;
    background: rgba(18, 18, 18, 0.94);
    box-shadow: 0 24px 70px rgba(0, 0, 0, 0.58);
    text-align: center;
  }

  .confirm-card {
    width: min(100%, 380px);
    padding: 22px;
    border: 1px solid var(--panel-border);
    border-radius: 18px;
    background:
      linear-gradient(180deg, rgba(255, 255, 255, 0.06), transparent 28%),
      rgba(18, 18, 18, 0.96);
    box-shadow: 0 26px 80px rgba(0, 0, 0, 0.62), inset 0 1px 0 rgba(255, 255, 255, 0.06);
  }

  .confirm-title {
    margin: 0;
    color: var(--text-main);
    font-size: 20px;
    font-weight: 780;
    letter-spacing: -0.02em;
  }

  .confirm-detail {
    margin: 8px 0 0;
    color: var(--text-soft);
    font-size: 13px;
    line-height: 1.55;
  }

  .confirm-actions {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin-top: 20px;
  }

  .confirm-button {
    width: 100%;
    min-height: 44px;
    border: 1px solid var(--card-border);
    border-radius: 10px;
    font-size: 13px;
    font-weight: 750;
    transition: transform 0.18s ease, background 0.18s ease, border-color 0.18s ease;
  }

  .confirm-button:active {
    transform: scale(0.985);
  }

  .confirm-button:disabled {
    opacity: 0.55;
    cursor: wait;
  }

  .confirm-cancel {
    background: var(--card-bg);
    color: var(--text-soft);
  }

  .confirm-cancel:hover {
    border-color: rgba(255, 255, 255, 0.18);
    background: rgba(255, 255, 255, 0.075);
  }

  .confirm-danger {
    border-color: rgba(255, 255, 255, 0.24);
    background: rgba(255, 255, 255, 0.11);
    color: var(--text-main);
  }

  .confirm-danger:hover {
    border-color: rgba(255, 255, 255, 0.38);
    background: rgba(255, 255, 255, 0.16);
  }

  .hidden {
    display: none !important;
  }

  .modal-overlay {
    position: fixed;
    inset: 0;
    display: none;
    align-items: center;
    justify-content: center;
    padding: 16px;
    background: rgba(0, 0, 0, 0.68);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
  }

  .modal-overlay.flex {
    display: flex;
  }

  .close-confirm-overlay {
    z-index: 40;
  }

  .shutdown-overlay {
    z-index: 50;
    background: rgba(0, 0, 0, 0.74);
  }

  .shutdown-icon {
    color: #d4d4d4;
    font-size: 30px;
  }

  .shutdown-title {
    margin-top: 12px;
    color: #fff;
    font-size: 18px;
    font-weight: 700;
  }

  .shutdown-detail {
    margin-top: 4px;
    color: var(--text-soft);
    font-size: 12px;
    line-height: 1.55;
  }

  @media (max-width: 560px) {
    body {
      place-items: center;
      padding: 10px;
    }

    .app-shell {
      width: min(100%, 420px);
      padding: 24px 10px;
      border-radius: 14px;
    }

    .hero-card {
      padding: 10px;
      border-radius: 10px;
    }

    .temperature {
      font-size: clamp(28px, 9vw, 38px);
    }

    .controls-card {
      margin-top: 10px;
      padding: 10px;
      border-radius: 10px;
    }

    .hero-footer {
      align-items: center;
      flex-direction: row;
      gap: 7px;
    }

    .metric-grid {
      gap: 5px;
    }

    .metric-item {
      display: flex;
      min-width: 0;
      align-items: center;
      gap: 5px;
    }

    .metric-label {
      flex: 0 0 auto;
      font-size: 9px;
      letter-spacing: 0.1em;
    }

    .metric-value {
      min-width: 0;
      margin-top: 0;
      font-size: 13px;
    }

    .refresh-button {
      width: auto;
      min-height: 32px;
      padding: 0 8px;
      font-size: 11px;
    }

    .action-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 7px;
    }

    .action-button {
      min-height: 50px;
    }

    .control-row {
      min-height: 52px;
      padding: 10px 12px;
      border-radius: 8px;
    }

    .power-slider {
      --power-knob-size: 36px;
      min-height: 52px;
      padding: 0 11px 0 46px;
      border-radius: 8px;
    }

    .power-slider-label {
      font-size: 11px;
    }

    .footer-row {
      flex-wrap: wrap;
      gap: 7px;
    }

    .utility-button,
    .restart-button {
      flex: 1 1 calc(50% - 4px);
      min-width: 0;
      padding: 0 9px;
    }

    .footer-link {
      flex: 1 0 100%;
      width: 100%;
      min-height: 38px;
      padding: 0 10px;
      font-size: 10px;
    }

    .confirm-actions {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 420px) {
    body {
      padding: 8px;
    }

    .app-shell {
      width: min(100%, 390px);
      padding: 20px 8px;
      border-radius: 13px;
    }

    .hero-card {
      padding: 9px;
      border-radius: 9px;
    }

    .temperature {
      font-size: clamp(26px, 8vw, 32px);
    }

    .hero-footer {
      gap: 7px;
    }

    .metric-grid {
      gap: 5px;
    }

    .metric-item {
      display: block;
    }

    .metric-label {
      font-size: 8px;
      letter-spacing: 0.08em;
    }

    .metric-value {
      margin-top: 2px;
      font-size: 11px;
    }

    .refresh-button {
      min-height: 30px;
      padding: 0 8px;
      font-size: 10px;
    }

    .controls-card {
      margin-top: 9px;
      padding: 9px;
      border-radius: 9px;
    }

    .action-grid,
    .control-list {
      gap: 6px;
    }

    .action-button {
      min-height: 46px;
      padding: 9px;
      border-radius: 8px;
    }

    .control-row {
      min-height: 48px;
      padding: 9px 10px;
      border-radius: 8px;
    }

    .action-label,
    .control-title {
      font-size: 13px;
    }

    .control-meta {
      font-size: 10px;
    }

    .switch {
      width: 36px;
      height: 20px;
    }

    .switch-slider::after {
      width: 12px;
      height: 12px;
    }

    .switch-input:checked + .switch-slider::after {
      transform: translateX(16px);
    }

    .power-slider {
      --power-knob-size: 34px;
      --power-knob-inset: 5px;
      min-height: 48px;
      padding: 0 9px 0 41px;
      border-radius: 8px;
    }

    .power-slider-label {
      font-size: 10px;
    }

    .utility-button,
    .restart-button {
      min-height: 36px;
      font-size: 11px;
    }
  }
</style>
</head>
<body>
<main class="app-shell">
  <section class="hero-card" aria-label="AC status">
    <div class="hero-footer">
      <div class="temperature" id="activeTempF">--</div>
      <div class="metric-grid">
        <div class="metric-item">
          <p class="metric-label">Phase</p>
          <span class="metric-value" id="phase">stopped</span>
        </div>
        <div class="metric-item">
          <p class="metric-label">Remaining</p>
          <span class="metric-value" id="remaining">--:--</span>
        </div>
      </div>
      <button onclick="readDeviceStatus()" class="refresh-button" aria-label="Refresh AC setting">Refresh</button>
    </div>
    <div class="action-grid" aria-label="Cycle controls">
      <button id="startBtn" onclick="postAction('/api/start')" class="dashboard-button action-button action-primary" aria-label="Start cycle">
        <span class="action-label">Start Cycle</span>
      </button>
      <button id="stopBtn" onclick="postAction('/api/stop')" class="dashboard-button action-button action-quiet" aria-label="Stop cycle">
        <span class="action-label">Stop Cycle</span>
      </button>
    </div>
  </section>

  <section class="controls-card" aria-label="AC controls">
    <p class="section-label">Manual Control</p>
    <div class="control-list">
      <div id="compressorControl" onclick="toggleCompressor()" class="control-row compressor-control" role="button" aria-label="Toggle compressor" aria-pressed="false">
        <span class="control-copy">
          <span class="control-title">Compressor</span>
        </span>
        <span class="switch" aria-hidden="true">
          <input class="switch-input" id="compressorToggle" name="compressor-toggle" type="checkbox" tabindex="-1">
          <span class="switch-slider"></span>
        </span>
      </div>
      <div onclick="toggleSwing()" class="control-row swing-control" role="button" aria-label="Toggle swing">
        <span class="control-copy">
          <span class="control-text">
            <span class="control-title">Swing</span>
            <span class="control-meta" id="swingState">Off</span>
          </span>
        </span>
        <span class="switch" aria-hidden="true">
          <input class="switch-input" id="swingToggle" name="toggle" type="checkbox" tabindex="-1">
          <span class="switch-slider"></span>
        </span>
      </div>
      <div id="powerSlider" class="power-slider power-off" role="button" tabindex="0" aria-label="Slide to turn AC on" aria-pressed="false">
        <span class="power-slider-knob" id="powerKnob" aria-hidden="true">
          <span class="material-symbols-outlined">power_settings_new</span>
        </span>
        <span class="power-slider-label" id="powerLabel"></span>
      </div>
    </div>

    <div class="footer-toggle-wrap">
      <button id="footerToggleBtn" onclick="toggleFooterControls()" class="footer-toggle" type="button" aria-label="Show settings" aria-expanded="false" aria-controls="footerControls"></button>
    </div>
    <div id="footerControls" class="footer-row is-hidden" aria-hidden="true">
      <button onclick="openCloseConfirm()" class="utility-button" aria-label="Close server">Close Server</button>
      <button id="restartServerBtn" onclick="restartServer()" class="restart-button" type="button" aria-label="Restart server">Restart Server</button>
      <a id="phoneUrl" class="footer-link" href="#">loading...</a>
    </div>
  </section>
</main>

<div id="closeConfirmOverlay" class="modal-overlay close-confirm-overlay hidden" role="dialog" aria-modal="true" aria-labelledby="closeConfirmTitle">
  <div class="confirm-card">
    <h2 id="closeConfirmTitle" class="confirm-title">Close Server?</h2>
    <p class="confirm-detail">The cycle will stop and the local panel server will shut down. You can reopen it from the server shortcut later.</p>
    <div class="confirm-actions">
      <button id="closeConfirmCancel" onclick="closeCloseConfirm()" class="confirm-button confirm-cancel" type="button">Cancel</button>
      <button id="closeConfirmAccept" onclick="shutdownServer()" class="confirm-button confirm-danger" type="button">Close Server</button>
    </div>
  </div>
</div>

<div id="shutdownOverlay" class="modal-overlay shutdown-overlay hidden">
  <div class="shutdown-card">
    <span id="shutdownIcon" class="material-symbols-outlined shutdown-icon">hourglass_top</span>
    <div id="shutdownTitle" class="shutdown-title">Closing server</div>
    <div id="shutdownDetail" class="shutdown-detail">Stopping the cycle and shutting down the local panel.</div>
  </div>
</div>

<script>
  const closeConfirmOverlay = document.getElementById('closeConfirmOverlay');
  const closeConfirmAccept = document.getElementById('closeConfirmAccept');
  let refreshTimer = null;

  function toggleFooterControls() {
    const controls = document.getElementById('footerControls');
    const button = document.getElementById('footerToggleBtn');
    if (!controls || !button) return;
    const willShow = controls.classList.contains('is-hidden');
    controls.classList.toggle('is-hidden', !willShow);
    controls.setAttribute('aria-hidden', String(!willShow));
    button.setAttribute('aria-expanded', String(willShow));
    button.setAttribute('aria-label', willShow ? 'Hide settings' : 'Show settings');
  }

  function openCloseConfirm() {
    closeConfirmAccept.disabled = false;
    closeConfirmOverlay.classList.remove('hidden');
    closeConfirmOverlay.classList.add('flex');
    setTimeout(() => closeConfirmAccept.focus(), 0);
  }

  function closeCloseConfirm() {
    closeConfirmOverlay.classList.add('hidden');
    closeConfirmOverlay.classList.remove('flex');
  }

  function showShutdownOverlay(title, detail, icon, color) {
    const overlay = document.getElementById('shutdownOverlay');
    document.getElementById('shutdownTitle').textContent = title;
    document.getElementById('shutdownDetail').textContent = detail;
    const shutdownIcon = document.getElementById('shutdownIcon');
    shutdownIcon.textContent = icon;
    shutdownIcon.style.color = color;
    overlay.classList.remove('hidden');
    overlay.classList.add('flex');
  }

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  async function waitForServerClose() {
    for (let attempt = 0; attempt < 12; attempt += 1) {
      await sleep(250);
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 500);
      try {
        await fetch('/api/state?shutdown_check=' + Date.now(), { cache: 'no-store', signal: controller.signal });
      } catch (error) {
        return true;
      } finally {
        clearTimeout(timeout);
      }
    }
    return false;
  }

  async function waitForServerReady() {
    for (let attempt = 0; attempt < 40; attempt += 1) {
      await sleep(500);
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 500);
      try {
        const response = await fetch('/api/state?restart_check=' + Date.now(), { cache: 'no-store', signal: controller.signal });
        if (response.ok) return true;
      } catch (error) {
        // The server is expected to be temporarily unavailable while restarting.
      } finally {
        clearTimeout(timeout);
      }
    }
    return false;
  }

  function fmtSeconds(value) {
    if (value === null || value === undefined) return '--:--';
    const seconds = Math.max(0, Math.floor(value));
    const minutes = Math.floor(seconds / 60);
    const rest = seconds % 60;
    return String(minutes).padStart(2, '0') + ':' + String(rest).padStart(2, '0');
  }

  function fmtTemperature(value, unit) {
    if (value === null || value === undefined) return '--';
    const rounded = Math.abs(value - Math.round(value)) < 0.05 ? String(Math.round(value)) : value.toFixed(1);
    return rounded + unit;
  }

  function renderTemperature(temperature, isPoweredOn) {
    const value = document.getElementById('activeTempF');
    if (!isPoweredOn) {
      value.textContent = '--';
      return;
    }
    if (!temperature) {
      value.textContent = '--';
      return;
    }
    if (temperature.error) {
      value.textContent = '--';
      return;
    }
    if (temperature.fahrenheit === null || temperature.fahrenheit === undefined) {
      value.textContent = '--';
      return;
    }
    value.textContent = fmtTemperature(temperature.fahrenheit, 'F');
  }

  async function requestJson(path, options) {
    const response = await fetch(path, options || {});
    const data = await response.json();
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || response.statusText);
    }
    return data;
  }

  async function refreshState() {
    try {
      const data = await requestJson('/api/state');
      renderState(data.state);
    } catch (error) {
      console.error(error);
    }
  }

  let latestState = null;
  const POWER_SLIDE_THRESHOLD = 0.95;
  const powerSliderState = {
    busy: false,
    dragging: false,
    pointerId: null,
    startX: 0,
    progress: 0,
  };

  function powerSliderElements() {
    return {
      slider: document.getElementById('powerSlider'),
      knob: document.getElementById('powerKnob'),
      label: document.getElementById('powerLabel'),
    };
  }

  function powerSliderInset(slider) {
    const value = parseFloat(getComputedStyle(slider).getPropertyValue('--power-knob-inset'));
    return Number.isFinite(value) ? value : 6;
  }

  function powerSliderMaxTravel(slider, knob) {
    return Math.max(0, slider.clientWidth - knob.offsetWidth - powerSliderInset(slider) * 2);
  }

  function powerSliderActionText(isOn) {
    return '';
  }

  function updatePowerSliderLabel() {
    const { label } = powerSliderElements();
    if (!label) return;
    if (powerSliderState.busy) {
      label.textContent = 'Sending...';
      return;
    }
    if (powerSliderState.dragging) {
      label.textContent = powerSliderState.progress >= POWER_SLIDE_THRESHOLD ? 'Release to confirm' : 'Keep sliding';
      return;
    }
    label.textContent = powerSliderActionText(Boolean(latestState && latestState.power_switch));
  }

  function setPowerSliderProgress(progress) {
    const { slider, knob } = powerSliderElements();
    if (!slider || !knob) return;
    const clamped = Math.max(0, Math.min(1, progress));
    const travel = powerSliderMaxTravel(slider, knob) * clamped;
    powerSliderState.progress = clamped;
    slider.style.setProperty('--power-progress', clamped.toFixed(3));
    slider.classList.toggle('is-confirm-ready', !powerSliderState.busy && clamped >= POWER_SLIDE_THRESHOLD);
    knob.style.transform = 'translate(' + travel.toFixed(1) + 'px, -50%)';
    updatePowerSliderLabel();
  }

  function resetPowerSlider() {
    setPowerSliderProgress(0);
  }

  function renderPowerSlider() {
    const { slider, label } = powerSliderElements();
    if (!slider || !label) return;
    const isOn = Boolean(latestState && latestState.power_switch);
    slider.classList.toggle('power-on', isOn);
    slider.classList.toggle('power-off', !isOn);
    slider.classList.toggle('is-busy', powerSliderState.busy);
    slider.classList.toggle('is-confirm-ready', !powerSliderState.busy && powerSliderState.progress >= POWER_SLIDE_THRESHOLD);
    slider.setAttribute('aria-disabled', String(powerSliderState.busy));
    slider.setAttribute('aria-pressed', String(isOn));
    slider.setAttribute('aria-label', isOn ? 'Slide to turn AC off' : 'Slide to turn AC on');
    updatePowerSliderLabel();
  }

  function renderState(state) {
    latestState = state;

    document.getElementById('phase').textContent = state.phase || 'stopped';
    document.getElementById('remaining').textContent = fmtSeconds(state.remaining_seconds);

    const isPoweredOn = Boolean(state.power_switch);
    const swingToggle = document.getElementById('swingToggle');
    const swingState = document.getElementById('swingState');
    const swingControl = document.querySelector('.swing-control');
    const swingOn = isPoweredOn && Boolean(state.swing_wind);
    if (swingOn) {
      swingToggle.checked = true;
      swingState.textContent = 'On';
    } else {
      swingToggle.checked = false;
      swingState.textContent = 'Off';
    }
    if (swingControl) {
      swingControl.classList.toggle('is-disabled', !isPoweredOn);
      swingControl.setAttribute('aria-disabled', String(!isPoweredOn));
      swingControl.setAttribute('aria-pressed', String(swingOn));
      swingControl.title = !isPoweredOn ? 'Turn AC on first.' : '';
    }

    const phoneUrl = document.getElementById('phoneUrl');
    const urls = state.network_urls || [];
    if (urls.length) {
      phoneUrl.textContent = urls[0];
      phoneUrl.href = urls[0];
    } else {
      phoneUrl.textContent = 'No phone URL';
      phoneUrl.href = '#';
    }

    renderTemperature(state.active_temperature, isPoweredOn);

    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    startBtn.disabled = state.running || !isPoweredOn;
    startBtn.title = !isPoweredOn
      ? 'Turn AC on first.'
      : (state.running ? 'Cycle is already running.' : '');
    stopBtn.disabled = !state.running;
    const compressorControl = document.getElementById('compressorControl');
    const compressorToggle = document.getElementById('compressorToggle');
    const activeTempF = Number(state.active_temperature && state.active_temperature.fahrenheit);
    const coolingSetpointF = Number(state.cycle && state.cycle.cooling_setpoint_f);
    const restingSetpointF = Number(state.cycle && state.cycle.resting_setpoint_f);
    const compressorOn = Number.isFinite(activeTempF)
      && Number.isFinite(coolingSetpointF)
      && Math.abs(activeTempF - coolingSetpointF) < 0.5;
    if (compressorToggle) compressorToggle.checked = isPoweredOn && compressorOn;
    if (compressorControl) {
      compressorControl.classList.toggle('is-disabled', !isPoweredOn);
      compressorControl.setAttribute('aria-disabled', String(!isPoweredOn));
      compressorControl.setAttribute('aria-pressed', String(isPoweredOn && compressorOn));
      compressorControl.title = !isPoweredOn
        ? 'Turn AC on first.'
        : (compressorOn ? 'Set to ' + restingSetpointF + 'F.' : 'Set to ' + coolingSetpointF + 'F.');
    }

    renderPowerSlider();
    if (!powerSliderState.dragging && !powerSliderState.busy) resetPowerSlider();

  }

  async function postAction(path) {
    try {
      const data = await requestJson(path, { method: 'POST' });
      renderState(data.state);
    } catch (error) {
      console.error(error);
      refreshState();
    }
  }

  async function sendPhase(phase) {
    const button = document.getElementById('compressorControl');
    const title = button ? button.querySelector('.control-title') : null;
    const originalTitle = title ? title.textContent : '';
    if (button) {
      button.classList.add('is-sending');
      button.setAttribute('aria-busy', 'true');
    }
    if (title) title.textContent = 'Sending...';
    try {
      const data = await requestJson('/api/phase', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phase })
      });
      renderState(data.state);
    } catch (error) {
      console.error(error);
      alert(error.message || 'Command failed.');
      await refreshState();
    } finally {
      if (title) title.textContent = originalTitle;
      if (button) {
        button.classList.remove('is-sending');
        button.removeAttribute('aria-busy');
      }
    }
  }

  async function toggleCompressor() {
    if (!latestState || !latestState.power_switch) return;
    const toggle = document.getElementById('compressorToggle');
    const isCooling = Boolean(toggle && toggle.checked);
    await sendPhase(isCooling ? 'resting' : 'cooling');
  }

  async function readDeviceStatus(silent) {
    try {
      const data = await requestJson('/api/device-status');
      if (data.state) {
        renderState(data.state);
      } else {
        renderTemperature(data.active_temperature, Boolean(latestState && latestState.power_switch));
      }
    } catch (error) {
      console.error(error);
      if (silent) await refreshState();
    }
  }

  async function shutdownServer() {
    closeConfirmAccept.disabled = true;
    closeCloseConfirm();
    if (refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
    showShutdownOverlay(
      'Closing server',
      'Stopping the cycle and shutting down the local panel.',
      'hourglass_top',
      '#d4d4d4'
    );
    try {
      await requestJson('/api/shutdown', { method: 'POST' });
      const closed = await waitForServerClose();
      if (closed) {
        showShutdownOverlay(
          'Server closed',
          'The local panel server has stopped. You can close this tab.',
          'check_circle',
          '#f5f5f5'
        );
      } else {
        showShutdownOverlay(
          'Shutdown requested',
          'The close command was sent, but the page could not verify that the server stopped yet.',
          'info',
          '#c7c7c7'
        );
      }
    } catch (error) {
      const closed = await waitForServerClose();
      if (closed) {
        showShutdownOverlay(
          'Server closed',
          'The local panel server stopped after the close request. You can close this tab.',
          'check_circle',
          '#f5f5f5'
        );
      } else {
        showShutdownOverlay(
          'Close failed',
          error.message,
          'error',
          '#e5e5e5'
        );
        refreshTimer = setInterval(refreshState, 2000);
      }
    }
  }

  async function restartServer() {
    const button = document.getElementById('restartServerBtn');
    if (button) button.disabled = true;
    if (refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
    showShutdownOverlay(
      'Restarting server',
      'Restarting the local panel. This page will reload automatically.',
      'restart_alt',
      '#f5f5f5'
    );
    try {
      await requestJson('/api/restart', { method: 'POST' });
    } catch (error) {
      console.error(error);
    }
    await waitForServerClose();
    const ready = await waitForServerReady();
    if (ready) {
      window.location.reload();
      return;
    }
    showShutdownOverlay(
      'Restart requested',
      'The local panel is restarting. Reload this page in a moment.',
      'info',
      '#c7c7c7'
    );
  }

  async function togglePower() {
    if (powerSliderState.busy) return;
    powerSliderState.busy = true;
    renderPowerSlider();
    try {
      const current = latestState ? latestState.power_switch : false;
      const next = !current;
      const data = await requestJson('/api/power', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: next })
      });
      if (data.state) renderState(data.state);
      else await refreshState();
    } catch (error) {
      console.error(error);
      refreshState();
    } finally {
      powerSliderState.busy = false;
      renderPowerSlider();
      resetPowerSlider();
    }
  }

  function beginPowerDrag(event) {
    if (powerSliderState.busy || (event.button !== undefined && event.button !== 0)) return;
    const { slider } = powerSliderElements();
    if (!slider) return;
    const dragHandle = event.target instanceof Element ? event.target.closest('.power-slider-knob') : null;
    if (!dragHandle) return;
    powerSliderState.dragging = true;
    powerSliderState.pointerId = event.pointerId;
    powerSliderState.startX = event.clientX;
    slider.classList.add('is-dragging');
    slider.setPointerCapture(event.pointerId);
    setPowerSliderProgress(0);
    updatePowerSliderLabel();
    event.preventDefault();
  }

  function movePowerDrag(event) {
    if (!powerSliderState.dragging || event.pointerId !== powerSliderState.pointerId) return;
    const { slider, knob } = powerSliderElements();
    if (!slider || !knob) return;
    const maxTravel = powerSliderMaxTravel(slider, knob);
    const distance = Math.max(0, event.clientX - powerSliderState.startX);
    setPowerSliderProgress(maxTravel ? distance / maxTravel : 0);
  }

  function finishPowerDrag(event, cancelled) {
    if (!powerSliderState.dragging || event.pointerId !== powerSliderState.pointerId) return;
    const { slider } = powerSliderElements();
    powerSliderState.dragging = false;
    powerSliderState.pointerId = null;
    if (slider) {
      slider.classList.remove('is-dragging');
      if (slider.hasPointerCapture(event.pointerId)) slider.releasePointerCapture(event.pointerId);
    }
    if (!cancelled && powerSliderState.progress >= POWER_SLIDE_THRESHOLD) {
      setPowerSliderProgress(1);
      togglePower();
      return;
    }
    resetPowerSlider();
  }

  function handlePowerSliderKeydown(event) {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    if (powerSliderState.busy) return;
    setPowerSliderProgress(1);
    togglePower();
  }

  function initPowerSlider() {
    const { slider } = powerSliderElements();
    if (!slider) return;
    slider.addEventListener('pointerdown', beginPowerDrag);
    slider.addEventListener('pointermove', movePowerDrag);
    slider.addEventListener('pointerup', (event) => finishPowerDrag(event, false));
    slider.addEventListener('pointercancel', (event) => finishPowerDrag(event, true));
    slider.addEventListener('keydown', handlePowerSliderKeydown);
  }

  async function toggleSwing() {
    if (!latestState || !latestState.power_switch) return;
    try {
      const current = latestState ? latestState.swing_wind : false;
      const next = !current;
      await requestJson('/api/swing', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: next })
      });
      refreshState();
    } catch (error) {
      console.error(error);
    }
  }

  async function loadInitialState() {
    await readDeviceStatus(true);
    if (!refreshTimer) refreshTimer = setInterval(refreshState, 2000);
  }

  closeConfirmOverlay.addEventListener('click', (event) => {
    if (event.target === closeConfirmOverlay) closeCloseConfirm();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !closeConfirmOverlay.classList.contains('hidden')) {
      closeCloseConfirm();
    }
  });

  initPowerSlider();
  loadInitialState();
</script>
</body>
</html>
"""


def empty_temperature(error: str | None = None, updated_at: float | None = None) -> dict[str, Any]:
    return {
        "fahrenheit": None,
        "celsius": None,
        "source": None,
        "updated_at": updated_at,
        "error": error,
    }


def celsius_to_fahrenheit(value: float) -> float:
    return (value * 9.0 / 5.0) + 32.0


def normalize_temperature(value: float, unit: str) -> dict[str, float]:
    if unit == "F":
        fahrenheit = value
        celsius = (value - 32.0) * 5.0 / 9.0
    else:
        celsius = value
        fahrenheit = celsius_to_fahrenheit(value)
    return {"fahrenheit": round(fahrenheit, 1), "celsius": round(celsius, 1)}


def value_at_path(value: Any, path: tuple[str, ...]) -> Any:
    current = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def numeric_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def boolean_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "on", "yes"}:
            return True
        if normalized in {"0", "false", "off", "no"}:
            return False
        try:
            value = float(normalized)
        except ValueError:
            return None
    if isinstance(value, (int, float)):
        return value != 0
    return None


def extract_bool_property(status: Any, property_name: str) -> bool | None:
    target_paths = [
        ("state", "reported", property_name),
        ("state", "desired", property_name),
        ("reported", property_name),
        ("desired", property_name),
    ]
    for path in target_paths:
        value = boolean_value(value_at_path(status, path))
        if value is not None:
            return value
    return None


def extract_active_temperature(status: Any) -> dict[str, Any]:
    target_paths = [
        (("state", "reported", "targetFahrenheitDegree"), "F"),
        (("state", "reported", "targetCelsiusDegree"), "C"),
        (("state", "desired", "targetFahrenheitDegree"), "F"),
        (("state", "desired", "targetCelsiusDegree"), "C"),
    ]
    for path, unit in target_paths:
        value = numeric_value(value_at_path(status, path))
        if value is None:
            continue
        if value < -40 or value > 140:
            continue
        normalized = normalize_temperature(value, unit)
        return {
            "fahrenheit": normalized["fahrenheit"],
            "celsius": normalized["celsius"],
            "source": ".".join(path),
            "updated_at": time.time(),
            "error": None,
        }

    return empty_temperature(updated_at=time.time())

class WebController:
    def __init__(self, config_path: pathlib.Path, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.config = load_config(config_path)
        self.cycle = get_cycle_config(self.config)
        self.backend = create_backend(self.config, self.cycle)

        safety = self.config.get("safety") if isinstance(self.config.get("safety"), dict) else {}
        self.min_seconds_between_commands = float(safety.get("min_seconds_between_commands", 30))
        self.status_log_seconds = float(safety.get("status_log_seconds", 60))

        self.state_lock = threading.RLock()
        self.command_lock = threading.RLock()
        self.command_queue: queue.Queue[Any] = queue.Queue()
        self._worker_active = True
        self._worker_thread = threading.Thread(target=self._command_worker, name="tcl-cmd-worker", daemon=True)
        self._worker_thread.start()
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.last_command_at = 0.0
        self.running = False
        self.phase = "stopped"
        self.cycle_number = 0
        self.phase_started_at: float | None = None
        self.phase_end_at: float | None = None
        self.active_temperature = empty_temperature()
        self.power_switch = False
        self.swing_wind = False

    def snapshot(self) -> dict[str, Any]:
        with self.state_lock:
            now = time.time()
            stopping = self.running and self.stop_event.is_set()
            remaining = None
            if self.running and not stopping and self.phase_end_at is not None:
                remaining = max(0.0, self.phase_end_at - now)
            return {
                "running": self.running,
                "phase": "stopped" if stopping else self.phase,
                "power_switch": self.power_switch,
                "swing_wind": self.swing_wind,
                "remaining_seconds": remaining,
                "network_urls": network_urls(self.host, self.port),
                "cycle": {
                    "cooling_setpoint_f": float(self.cycle["cooling_setpoint_f"]),
                    "resting_setpoint_f": float(self.cycle["resting_setpoint_f"]),
                    "cooling_minutes": float(self.cycle["cooling_minutes"]),
                    "resting_minutes": float(self.cycle["resting_minutes"]),
                },
                "active_temperature": dict(self.active_temperature),
            }

    def start_cycle(self) -> str:
        with self.state_lock:
            if self.running:
                return "Cycle is already running."
            self.stop_event = threading.Event()
            self.running = True
            self.phase = "starting"
            self.phase_started_at = None
            self.phase_end_at = None
            self.thread = threading.Thread(target=self._run_cycle, name="tcl-web-cycle", daemon=True)
            self.thread.start()
        logging.info("Web: cycle start requested")
        return "Cycle started."

    def stop_cycle(self) -> str:
        with self.state_lock:
            if not self.running:
                return "Cycle is already stopped."
            self._request_cycle_stop_locked()
        thread = self.thread
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        logging.info("Web: cycle stop requested")
        return "Stopping cycle."

    def _request_cycle_stop_locked(self) -> None:
        self.stop_event.set()
        self.phase = "stopped"
        self.phase_started_at = None
        self.phase_end_at = None

    def set_power_switch(self, enabled: bool) -> str:
        status = "on" if enabled else "off"
        with self.state_lock:
            prev = self.power_switch
            if not enabled and self.running:
                self._request_cycle_stop_locked()
                logging.info("Web: cycle stop requested because AC power was turned off")
        def updater(done: bool, error: str | None) -> None:
            if error:
                self.power_switch = prev
            elif not done:
                self.power_switch = enabled
        self._enqueue_command(
            lambda ev=enabled: self.backend.set_power_switch(ev), f"AC power {status}", updater
        )
        return f"AC power turned {status}."

    def set_swing_wind(self, enabled: bool) -> str:
        status = "on" if enabled else "off"
        prev = self.swing_wind
        def updater(done: bool, error: str | None) -> None:
            if error:
                self.swing_wind = prev
            elif not done:
                self.swing_wind = enabled
        self._enqueue_command(
            lambda ev=enabled: self.backend.set_swing_wind(ev), f"Swing {status}", updater
        )
        return f"Swing turned {status}."

    def send_phase(self, phase: str) -> str:
        if phase == "cooling":
            setpoint = float(self.cycle["cooling_setpoint_f"])
            label = "cooling"
        elif phase == "resting":
            setpoint = float(self.cycle["resting_setpoint_f"])
            label = "resting"
        else:
            raise ConfigError("phase must be cooling or resting")
        thread = None
        stopped_cycle = False
        with self.state_lock:
            previous_temperature = dict(self.active_temperature)
            if self.running:
                self._request_cycle_stop_locked()
                thread = self.thread
                stopped_cycle = True
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        if stopped_cycle:
            logging.info("Web: cycle stop requested for manual %s command", label)

        def updater(done: bool, error: str | None) -> None:
            if error:
                self.active_temperature = previous_temperature
                return
            normalized = normalize_temperature(setpoint, "F")
            self.active_temperature = {
                "fahrenheit": normalized["fahrenheit"],
                "celsius": normalized["celsius"],
                "source": f"manual.{label}",
                "updated_at": time.time(),
                "error": None,
            }
        self._enqueue_command(
            lambda sp=setpoint, lb=label: self._safe_apply_sync(sp, lb),
            f"{setpoint:g}F {label}", updater,
        )
        if stopped_cycle:
            return f"Cycle stopped. {setpoint:g}F command queued."
        return f"{setpoint:g}F command queued."

    def read_device_status(self) -> Any:
        with self.command_lock:
            logging.info("Web: device status requested")
            status = self.backend.status()
            temperature = extract_active_temperature(status)
            swing_wind = extract_bool_property(status, "swingWind")
            power_switch = extract_bool_property(status, "powerSwitch")
            with self.state_lock:
                self.active_temperature = temperature
                if swing_wind is not None:
                    self.swing_wind = swing_wind
                if power_switch is not None:
                    self.power_switch = power_switch
                    if not power_switch and self.running:
                        self._request_cycle_stop_locked()
                        logging.info("Web: cycle stop requested because device reported AC power off")
        return status

    def _safe_apply_sync(self, setpoint_f: float, phase: str) -> None:
        if not self._safe_apply(setpoint_f, phase, threading.Event()):
            raise BackendError("Manual command cancelled")

    def _enqueue_command(
        self,
        fn: Any,
        description: str,
        state_updater: Any,
    ) -> None:
        with self.state_lock:
            state_updater(False, None)
        self.command_queue.put((fn, description, state_updater))

    def _command_worker(self) -> None:
        while self._worker_active:
            try:
                item = self.command_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is None:
                self.command_queue.task_done()
                break
            fn, description, state_updater = item
            try:
                with self.command_lock:
                    logging.info("Web: running queued command: %s", description)
                    fn()
                with self.state_lock:
                    state_updater(True, None)
            except Exception as exc:
                error_msg = str(exc)
                logging.error("Web: command %s failed: %s", description, error_msg)
                with self.state_lock:
                    state_updater(False, error_msg)
            finally:
                self.command_queue.task_done()

    def _shutdown_worker(self) -> None:
        self._worker_active = False
        self.command_queue.put(None)

    def _run_cycle(self) -> None:
        try:
            with self.command_lock:
                logging.info("Web: sending startup command before cycle")
                self.backend.startup()
            while not self.stop_event.is_set():
                with self.state_lock:
                    self.cycle_number += 1
                    cycle_number = self.cycle_number
                logging.info("Web cycle %d started", cycle_number)

                if not self._run_phase("cooling", float(self.cycle["cooling_setpoint_f"]), float(self.cycle["cooling_minutes"])):
                    break
                if not self._run_phase("resting", float(self.cycle["resting_setpoint_f"]), float(self.cycle["resting_minutes"])):
                    break
                logging.info("Web cycle %d finished", cycle_number)
        except Exception:
            logging.exception("Web cycle failed")
        finally:
            with self.state_lock:
                self.running = False
                self.phase = "stopped"
                self.phase_started_at = None
                self.phase_end_at = None
            logging.info("Web cycle stopped")

    def _run_phase(self, phase: str, setpoint_f: float, minutes: float) -> bool:
        if self.stop_event.is_set():
            return False
        now = time.time()
        with self.state_lock:
            self.phase = phase
            self.phase_started_at = now
            self.phase_end_at = now + (minutes * 60.0)
        if not self._safe_apply(setpoint_f, phase, self.stop_event):
            return False
        normalized = normalize_temperature(setpoint_f, "F")
        with self.state_lock:
            self.active_temperature = {
                "fahrenheit": normalized["fahrenheit"],
                "celsius": normalized["celsius"],
                "source": f"cycle.{phase}",
                "updated_at": time.time(),
                "error": None,
            }
        return self._wait_minutes(minutes, phase)

    def _safe_apply(self, setpoint_f: float, phase: str, stop_event: threading.Event) -> bool:
        if stop_event.is_set():
            return False
        with self.command_lock:
            elapsed = time.monotonic() - self.last_command_at
            if self.last_command_at and elapsed < self.min_seconds_between_commands:
                wait_seconds = self.min_seconds_between_commands - elapsed
                logging.info("Safety wait: %.0f seconds", wait_seconds)
                if stop_event.wait(wait_seconds):
                    return False
            if stop_event.is_set():
                return False
            self.backend.apply_setpoint_f(setpoint_f, phase)
            self.last_command_at = time.monotonic()
        return True

    def _wait_minutes(self, minutes: float, label: str) -> bool:
        total_seconds = minutes * 60.0
        end_at = time.monotonic() + total_seconds
        while not self.stop_event.is_set():
            remaining = end_at - time.monotonic()
            if remaining <= 0:
                return True
            logging.info("%s phase running, remaining %.1f min", label, remaining / 60.0)
            if self.stop_event.wait(min(self.status_log_seconds, remaining)):
                return False
        return False


class WebServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], controller: WebController):
        super().__init__(server_address, RequestHandler)
        self.controller = controller
        self.restart_requested = False


class RequestHandler(BaseHTTPRequestHandler):
    server: WebServer

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self._send_html(PAGE_HTML)
            return
        if parsed.path in {"/favicon.ico", "/favicon.png"}:
            self._send_favicon()
            return
        if parsed.path == "/api/state":
            self._send_json({"ok": True, "state": self.server.controller.snapshot()})
            return
        if parsed.path == "/api/device-status":
            self._handle_device_status()
            return
        self._send_json({"ok": False, "error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path == "/api/start":
                message = self.server.controller.start_cycle()
                self._send_json({"ok": True, "message": message, "state": self.server.controller.snapshot()})
                return
            if parsed.path == "/api/stop":
                message = self.server.controller.stop_cycle()
                self._send_json({"ok": True, "message": message, "state": self.server.controller.snapshot()})
                return
            if parsed.path == "/api/power":
                body = self._read_json_body()
                enabled = bool(body.get("enabled", False))
                message = self.server.controller.set_power_switch(enabled)
                self._send_json({"ok": True, "message": message, "state": self.server.controller.snapshot()})
                return
            if parsed.path == "/api/swing":
                body = self._read_json_body()
                enabled = bool(body.get("enabled", False))
                message = self.server.controller.set_swing_wind(enabled)
                self._send_json({"ok": True, "message": message, "state": self.server.controller.snapshot()})
                return
            if parsed.path == "/api/phase":
                body = self._read_json_body()
                phase = str(body.get("phase", ""))
                message = self.server.controller.send_phase(phase)
                self._send_json({"ok": True, "message": message, "state": self.server.controller.snapshot()})
                return
            if parsed.path == "/api/shutdown":
                message = self.server.controller.stop_cycle()
                self._send_json({"ok": True, "message": message})
                self.server.controller._shutdown_worker()
                threading.Thread(target=self.server.shutdown, name="tcl-web-shutdown", daemon=True).start()
                return
            if parsed.path == "/api/restart":
                message = self.server.controller.stop_cycle()
                self.server.restart_requested = True
                self._send_json({"ok": True, "message": message})
                self.server.controller._shutdown_worker()
                threading.Thread(target=self.server.shutdown, name="tcl-web-restart", daemon=True).start()
                return
            self._send_json({"ok": False, "error": "Not found"}, HTTPStatus.NOT_FOUND)
        except (BackendError, ConfigError, ValueError) as exc:
            logging.error("Web request failed: %s", exc)
            self._send_json({"ok": False, "error": str(exc), "state": self.server.controller.snapshot()}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            logging.error("Web request crashed: %s\n%s", exc, traceback.format_exc())
            self._send_json({"ok": False, "error": str(exc), "state": self.server.controller.snapshot()}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, format: str, *args: Any) -> None:
        logging.info("HTTP %s - %s", self.address_string(), format % args)

    def _handle_device_status(self) -> None:
        try:
            status = self.server.controller.read_device_status()
            state = self.server.controller.snapshot()
            self._send_json(
                {
                    "ok": True,
                    "device_status": status,
                    "active_temperature": state["active_temperature"],
                    "state": state,
                }
            )
        except (BackendError, ConfigError) as exc:
            logging.error("Device status failed: %s", exc)
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            logging.error("Device status crashed: %s\n%s", exc, traceback.format_exc())
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON body: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def _send_html(self, html: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        raw = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_favicon(self) -> None:
        try:
            raw = FAVICON_PATH.read_bytes()
        except OSError:
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/png")
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local web panel for the TCL AC cycle controller")
    parser.add_argument("--config", default=CONFIG_DEFAULT, help="Config file path")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host to bind, default allows LAN access with 0.0.0.0")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to listen on")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser automatically")
    return parser


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        controller = WebController(pathlib.Path(args.config), args.host, args.port)
        server = WebServer((args.host, args.port), controller)
    except (ConfigError, BackendError, OSError) as exc:
        logging.error("Could not start web panel: %s", exc)
        return 1

    bind_url = f"http://{args.host}:{args.port}/"
    open_url = browser_url(args.host, args.port)
    logging.info("TCL web panel listening on %s", bind_url)
    for url in network_urls(args.host, args.port):
        logging.info("Phone URL: %s", url)
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(open_url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Web panel stopped by keyboard")
    finally:
        restart_requested = server.restart_requested
        controller.stop_cycle()
        server.server_close()
    if restart_requested:
        command = [sys.executable, *sys.argv]
        logging.info("Restarting web panel: %s", command)
        try:
            os.execv(sys.executable, command)
        except OSError as exc:
            logging.error("Could not restart web panel: %s", exc)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
