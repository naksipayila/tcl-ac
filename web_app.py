from __future__ import annotations

import argparse
import json
import logging
import pathlib
import queue
import socket
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
  ::-webkit-scrollbar-thumb { background: #2a2a2b; border-radius: 2px; }

  @keyframes breathe {
    0%, 100% { opacity: 0.4; box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    50% { opacity: 1; box-shadow: 0 0 6px 2px rgba(16, 185, 129, 0.3); }
  }
  .animate-breathe {
    animation: breathe 3s ease-in-out infinite;
  }

  *,
  *::before,
  *::after {
    box-sizing: border-box;
  }

  :root {
    --page-bg: #07080a;
    --panel-bg: rgba(18, 20, 24, 0.92);
    --panel-border: rgba(255, 255, 255, 0.08);
    --card-bg: rgba(255, 255, 255, 0.045);
    --card-bg-strong: rgba(255, 255, 255, 0.075);
    --card-border: rgba(255, 255, 255, 0.085);
    --text-main: #f8fafc;
    --text-soft: #cbd5e1;
    --text-muted: #7f8b9d;
    --cyan: #67e8f9;
    --cyan-strong: #22d3ee;
    --green: #74e6b2;
    --red: #fb7185;
    --amber: #fbbf24;
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
      radial-gradient(circle at 50% -20%, rgba(103, 232, 249, 0.16), transparent 34%),
      radial-gradient(circle at 100% 10%, rgba(116, 230, 178, 0.08), transparent 28%),
      linear-gradient(180deg, #0b0d11 0%, var(--page-bg) 58%, #050506 100%);
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
    width: min(100%, 520px);
    padding: 18px;
    border: 1px solid var(--panel-border);
    border-radius: 24px;
    background:
      linear-gradient(180deg, rgba(255, 255, 255, 0.055), transparent 24%),
      var(--panel-bg);
    box-shadow: 0 26px 80px rgba(0, 0, 0, 0.54), inset 0 1px 0 rgba(255, 255, 255, 0.06);
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
  }

  .hero-card {
    width: 100%;
    padding: 22px;
    border: 1px solid var(--card-border);
    border-radius: 20px;
    background:
      radial-gradient(circle at 82% 12%, rgba(103, 232, 249, 0.14), transparent 30%),
      linear-gradient(180deg, rgba(255, 255, 255, 0.07), rgba(255, 255, 255, 0.035));
  }

  .hero-top,
  .hero-footer,
  .footer-row,
  .control-row,
  .status-pill {
    display: flex;
    align-items: center;
  }

  .hero-top,
  .hero-footer,
  .footer-row,
  .control-row {
    justify-content: space-between;
  }

  .eyebrow,
  .metric-label,
  .section-label,
  .control-meta,
  .footer-link {
    color: var(--text-muted);
  }

  .min-w-0 {
    min-width: 0;
  }

  .eyebrow,
  .metric-label,
  .section-label {
    margin: 0;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }

  .temperature {
    margin: 8px 0 2px;
    font-size: clamp(54px, 17vw, 92px);
    font-weight: 800;
    letter-spacing: -0.08em;
    line-height: 0.88;
  }

  #activeTempMeta {
    display: block;
    min-height: 19px;
    color: var(--text-soft);
    font-size: 13px;
  }

  .status-pill {
    gap: 8px;
    align-self: flex-start;
    padding: 7px 11px;
    border: 1px solid var(--card-border);
    border-radius: 999px;
    background: rgba(0, 0, 0, 0.18);
    color: var(--text-soft);
    font-size: 12px;
    font-weight: 650;
  }

  #statusDot {
    width: 8px;
    height: 8px;
    border-radius: 999px;
    background: var(--red);
  }

  .hero-footer {
    gap: 12px;
    margin-top: 24px;
    padding-top: 18px;
    border-top: 1px solid rgba(255, 255, 255, 0.075);
  }

  .metric-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
    flex: 1;
    min-width: 0;
  }

  .metric-value {
    display: block;
    margin-top: 4px;
    overflow: hidden;
    color: var(--text-main);
    font-size: 17px;
    font-weight: 700;
    letter-spacing: -0.02em;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .refresh-button {
    flex: 0 0 auto;
    min-height: 42px;
    padding: 0 14px;
    border: 1px solid var(--card-border);
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.055);
    color: var(--text-soft);
    font-size: 12px;
    font-weight: 700;
    transition: background 0.18s ease, border-color 0.18s ease, color 0.18s ease, transform 0.18s ease;
  }

  .refresh-button:hover,
  .control-row:hover,
  .utility-button:hover {
    border-color: rgba(255, 255, 255, 0.18);
    background: rgba(255, 255, 255, 0.075);
  }

  .action-grid {
    display: grid;
    grid-template-columns: 1.2fr 0.8fr;
    gap: 12px;
    margin-top: 14px;
  }

  .action-button {
    width: 100%;
    min-height: 76px;
    padding: 16px;
    border: 1px solid transparent;
    border-radius: 16px;
    text-align: left;
    transition: transform 0.18s ease, opacity 0.18s ease, background 0.18s ease, border-color 0.18s ease;
  }

  .action-button span,
  .control-title {
    display: block;
    color: var(--text-main);
    font-size: 16px;
    font-weight: 750;
    letter-spacing: -0.01em;
  }

  .action-button small,
  .control-meta {
    display: block;
    margin-top: 5px;
    font-size: 12px;
    line-height: 1.35;
  }

  .action-primary {
    background: linear-gradient(135deg, rgba(103, 232, 249, 0.96), rgba(116, 230, 178, 0.84));
    color: #052127;
    box-shadow: 0 16px 46px rgba(34, 211, 238, 0.18);
  }

  .action-primary span,
  .action-primary small {
    color: #052127;
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

  .action-quiet span {
    color: var(--text-soft);
  }

  .action-button:active:not(:disabled),
  .control-row:active:not(:disabled),
  .power-slider:active:not(.is-busy),
  .refresh-button:active,
  .utility-button:active {
    transform: scale(0.985);
  }

  .action-button:disabled,
  .control-row:disabled,
  .dashboard-button:disabled {
    opacity: 0.42;
    cursor: not-allowed;
    transform: none;
    filter: grayscale(0.2);
  }

  .section-label {
    margin: 18px 2px 9px;
  }

  .control-list {
    display: grid;
    gap: 9px;
  }

  .control-pair {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 9px;
  }

  .control-row {
    width: 100%;
    min-height: 66px;
    gap: 14px;
    padding: 14px 16px;
    border-radius: 14px;
    color: inherit;
    text-align: left;
    cursor: pointer;
    transition: transform 0.18s ease, opacity 0.18s ease, background 0.18s ease, border-color 0.18s ease;
  }

  .control-copy {
    min-width: 0;
  }

  .control-pair .control-row {
    min-width: 0;
    gap: 10px;
    padding-inline: 14px;
  }

  .control-pair .control-title,
  .control-pair .control-meta,
  .control-pair .control-value {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .control-value {
    flex: 0 0 auto;
    color: var(--text-soft);
    font-size: 14px;
    font-weight: 750;
  }

  .control-value.cool {
    color: var(--cyan);
  }

  .control-value.warm {
    color: var(--amber);
  }

  .switch {
    position: relative;
    flex: 0 0 auto;
    width: 42px;
    height: 24px;
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
    width: 16px;
    height: 16px;
    border-radius: 999px;
    background: #fff;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.28);
    transition: transform 0.18s ease;
  }

  .switch-input:checked + .switch-slider {
    border-color: rgba(103, 232, 249, 0.4);
    background: linear-gradient(135deg, rgba(34, 211, 238, 0.95), rgba(116, 230, 178, 0.84));
  }

  .switch-input:checked + .switch-slider::after {
    transform: translateX(18px);
  }

  .power-slider {
    --power-knob-inset: 6px;
    --power-knob-size: 44px;
    --power-progress: 0;
    position: relative;
    width: 100%;
    min-width: 0;
    min-height: 66px;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    padding: 0 16px 0 58px;
    border: 1px solid var(--card-border);
    border-radius: 14px;
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
    inset: 6px;
    z-index: 0;
    border-radius: 10px;
    background: linear-gradient(135deg, rgba(103, 232, 249, 0.32), rgba(116, 230, 178, 0.26));
    opacity: 0.75;
    transform: scaleX(var(--power-progress));
    transform-origin: left center;
    transition: transform 0.2s ease;
  }

  .power-slider::after {
    content: '';
    position: absolute;
    top: 50%;
    right: 10px;
    z-index: 1;
    width: 2px;
    height: 24px;
    border-radius: 999px;
    background: rgba(103, 232, 249, 0.34);
    transform: translateY(-50%);
    opacity: 0.78;
  }

  .power-slider.power-on {
    border-color: rgba(251, 113, 133, 0.22);
    background: rgba(251, 113, 133, 0.065);
  }

  .power-slider.power-on::before {
    background: linear-gradient(135deg, rgba(251, 113, 133, 0.34), rgba(251, 191, 36, 0.18));
  }

  .power-slider.power-on::after {
    background: rgba(251, 113, 133, 0.38);
  }

  .power-slider.power-off {
    border-color: rgba(103, 232, 249, 0.17);
    background: rgba(103, 232, 249, 0.05);
  }

  .power-slider.is-dragging {
    cursor: grabbing;
  }

  .power-slider.is-confirm-ready {
    border-color: rgba(103, 232, 249, 0.34);
  }

  .power-slider.power-on.is-confirm-ready {
    border-color: rgba(251, 113, 133, 0.36);
  }

  .power-slider.is-busy {
    cursor: wait;
    opacity: 0.72;
    pointer-events: none;
  }

  .power-slider:focus-visible {
    outline: 2px solid rgba(103, 232, 249, 0.55);
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
    border-radius: 12px;
    transform: translateY(-50%);
  }

  .power-slider-knob {
    left: var(--power-knob-inset);
    z-index: 3;
    width: var(--power-knob-size);
    height: var(--power-knob-size);
    color: #052127;
    cursor: grab;
    background: linear-gradient(135deg, rgba(103, 232, 249, 0.98), rgba(116, 230, 178, 0.88));
    box-shadow: 0 12px 30px rgba(34, 211, 238, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.38);
    transition: transform 0.2s ease, background 0.18s ease, box-shadow 0.18s ease;
  }

  .power-slider.power-on .power-slider-knob {
    color: #2a070d;
    background: linear-gradient(135deg, rgba(253, 164, 175, 0.98), rgba(251, 113, 133, 0.86));
    box-shadow: 0 12px 30px rgba(251, 113, 133, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.36);
  }

  .power-slider.is-dragging .power-slider-knob {
    cursor: grabbing;
  }

  .footer-row {
    gap: 10px;
    margin-top: 14px;
  }

  .utility-button,
  .footer-link {
    min-height: 42px;
    border-radius: 15px;
  }

  .utility-button {
    flex: 0 0 auto;
    min-width: 122px;
    padding: 0 14px;
    color: var(--red);
    font-size: 12px;
    font-weight: 700;
    transition: transform 0.18s ease, background 0.18s ease, border-color 0.18s ease;
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

  .shutdown-card {
    width: min(100%, 360px);
    padding: 24px;
    border: 1px solid var(--panel-border);
    border-radius: 20px;
    background: rgba(18, 20, 24, 0.94);
    box-shadow: 0 24px 70px rgba(0, 0, 0, 0.58);
    text-align: center;
  }

  .confirm-card {
    width: min(100%, 380px);
    padding: 22px;
    border: 1px solid var(--panel-border);
    border-radius: 22px;
    background:
      linear-gradient(180deg, rgba(255, 255, 255, 0.06), transparent 28%),
      rgba(18, 20, 24, 0.96);
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
    border-radius: 12px;
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
    border-color: rgba(251, 113, 133, 0.26);
    background: rgba(251, 113, 133, 0.12);
    color: #fecdd3;
  }

  .confirm-danger:hover {
    border-color: rgba(251, 113, 133, 0.42);
    background: rgba(251, 113, 133, 0.18);
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
    color: #bec6e0;
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
      align-items: start;
      place-items: start center;
      padding: 12px;
    }

    .app-shell {
      padding: 12px;
      border-radius: 20px;
    }

    .hero-card {
      padding: 18px;
      border-radius: 17px;
    }

    .hero-footer {
      align-items: stretch;
      flex-direction: column;
      margin-top: 20px;
      padding-top: 16px;
    }

    .refresh-button {
      width: 100%;
    }

    .action-grid {
      grid-template-columns: 1fr;
      gap: 9px;
    }

    .action-button {
      min-height: 64px;
    }

    .control-row {
      min-height: 62px;
      padding: 13px 14px;
    }

    .control-pair {
      gap: 8px;
    }

    .control-pair .control-row {
      padding: 12px;
      gap: 8px;
    }

    .control-pair .control-title {
      font-size: 14px;
    }

    .control-pair .control-meta,
    .control-pair .control-value {
      font-size: 11px;
    }

    .power-slider {
      --power-knob-size: 38px;
      min-height: 62px;
      padding: 0 12px 0 48px;
    }

    .power-slider-label {
      font-size: 11px;
    }

    .footer-row {
      flex-direction: column-reverse;
      align-items: stretch;
    }

    .utility-button,
    .footer-link {
      width: 100%;
    }

    .confirm-actions {
      grid-template-columns: 1fr;
    }
  }
</style>
</head>
<body>
<main class="app-shell">
  <section class="hero-card" aria-label="AC status">
    <div class="hero-top">
      <div class="min-w-0">
        <p class="eyebrow">TCL AC Control</p>
        <div class="temperature" id="activeTempF">--</div>
        <span id="activeTempMeta">Not read yet</span>
      </div>
      <div id="runPill" class="status-pill">
        <span id="statusDot"></span>
        <span id="runText">Loading</span>
      </div>
    </div>
    <div class="hero-footer">
      <div class="metric-grid">
        <div>
          <p class="metric-label">Phase</p>
          <span class="metric-value" id="phase">stopped</span>
        </div>
        <div>
          <p class="metric-label">Remaining</p>
          <span class="metric-value" id="remaining">--:--</span>
        </div>
      </div>
      <button onclick="readDeviceStatus()" class="refresh-button" aria-label="Refresh AC setting">Refresh</button>
    </div>
  </section>

  <div class="action-grid" aria-label="Cycle controls">
    <button id="startBtn" onclick="postAction('/api/start')" class="dashboard-button action-button action-primary" aria-label="Start cycle">
      <span>Start Cycle</span>
      <small>Run the 70F / 80F loop</small>
    </button>
    <button id="stopBtn" onclick="postAction('/api/stop')" class="dashboard-button action-button action-quiet" aria-label="Stop cycle">
      <span>Stop</span>
      <small>Pause the loop</small>
    </button>
  </div>

  <p class="section-label">Manual Control</p>
  <div class="control-list">
    <div class="control-pair">
      <button id="startCompressorBtn" onclick="sendPhase('cooling')" class="dashboard-button control-row" aria-label="Start compressor">
        <span class="control-copy">
          <span class="control-title">Start Compressor</span>
          <span class="control-meta">Set target to cooling</span>
        </span>
      </button>
      <button id="stopCompressorBtn" onclick="sendPhase('resting')" class="dashboard-button control-row" aria-label="Stop compressor">
        <span class="control-copy">
          <span class="control-title">Stop Compressor</span>
          <span class="control-meta">Raise target to resting</span>
        </span>
      </button>
    </div>
    <div class="control-pair">
      <div onclick="toggleSwing()" class="control-row swing-control" role="button" aria-label="Toggle swing">
        <span class="control-copy">
          <span class="control-title">Swing</span>
          <span class="control-meta" id="swingState">Off</span>
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
        <span class="power-slider-label" id="powerLabel">Slide to turn on</span>
      </div>
    </div>
  </div>

  <div class="footer-row">
    <button onclick="openCloseConfirm()" class="utility-button" aria-label="Close server">Close Server</button>
    <a id="phoneUrl" class="footer-link" href="#">loading...</a>
  </div>
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

  function fmtAge(timestamp) {
    if (!timestamp) return 'Not read yet';
    const seconds = Math.max(0, Math.floor(Date.now() / 1000 - timestamp));
    if (seconds < 60) return seconds + ' sec ago';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return minutes + ' min ago';
    return Math.floor(minutes / 60) + ' hr ago';
  }

  function renderTemperature(temperature) {
    const value = document.getElementById('activeTempF');
    const meta = document.getElementById('activeTempMeta');
    if (!temperature) {
      value.textContent = '--';
      meta.textContent = 'Not read yet';
      return;
    }
    if (temperature.error) {
      value.textContent = '--';
      meta.textContent = 'Error: ' + temperature.error;
      return;
    }
    if (temperature.fahrenheit === null || temperature.fahrenheit === undefined) {
      value.textContent = '--';
      meta.textContent = temperature.updated_at ? 'Target not found' : 'Not read yet';
      return;
    }
    value.textContent = fmtTemperature(temperature.fahrenheit, 'F');
    meta.textContent = fmtTemperature(temperature.celsius, 'C') + ' - ' + fmtAge(temperature.updated_at);
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
    return isOn ? 'Slide to turn off' : 'Slide to turn on';
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
    const dot = document.getElementById('statusDot');

    document.getElementById('phase').textContent = state.phase || 'stopped';
    document.getElementById('remaining').textContent = fmtSeconds(state.remaining_seconds);

    if (state.running) {
      document.getElementById('runText').textContent = 'Running';
      dot.classList.add('animate-breathe');
      dot.style.backgroundColor = '#4ad9d9';
    } else {
      document.getElementById('runText').textContent = 'Stopped';
      dot.classList.remove('animate-breathe');
      dot.style.backgroundColor = '#ff6b6b';
    }

    const swingToggle = document.getElementById('swingToggle');
    const swingState = document.getElementById('swingState');
    if (state.swing_wind) {
      swingToggle.checked = true;
      swingState.textContent = 'On';
    } else {
      swingToggle.checked = false;
      swingState.textContent = 'Off';
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

    renderTemperature(state.active_temperature);

    document.getElementById('startBtn').disabled = state.running;
    document.getElementById('stopBtn').disabled = !state.running;
    const startCompressorBtn = document.getElementById('startCompressorBtn');
    const stopCompressorBtn = document.getElementById('stopCompressorBtn');
    const activeTempF = Number(state.active_temperature && state.active_temperature.fahrenheit);
    const coolingSetpointF = Number(state.cycle && state.cycle.cooling_setpoint_f);
    const restingSetpointF = Number(state.cycle && state.cycle.resting_setpoint_f);
    const isPoweredOn = Boolean(state.power_switch);
    const alreadyCooling = Number.isFinite(activeTempF)
      && Number.isFinite(coolingSetpointF)
      && Math.abs(activeTempF - coolingSetpointF) < 0.5;
    const alreadyResting = Number.isFinite(activeTempF)
      && Number.isFinite(restingSetpointF)
      && Math.abs(activeTempF - restingSetpointF) < 0.5;
    startCompressorBtn.disabled = !isPoweredOn || alreadyCooling;
    startCompressorBtn.title = !isPoweredOn
      ? 'Turn AC on first.'
      : (alreadyCooling ? 'AC is already at ' + coolingSetpointF + 'F.' : '');
    stopCompressorBtn.disabled = !isPoweredOn || alreadyResting;
    stopCompressorBtn.title = !isPoweredOn
      ? 'Turn AC on first.'
      : (alreadyResting ? 'AC is already at ' + restingSetpointF + 'F.' : '');

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
    try {
      const data = await requestJson('/api/phase', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phase })
      });
      renderState(data.state);
    } catch (error) {
      console.error(error);
      refreshState();
    }
  }

  async function readDeviceStatus(silent) {
    try {
      const data = await requestJson('/api/device-status');
      if (data.state) renderState(data.state);
      const temperature = data.active_temperature || (data.state && data.state.active_temperature);
      renderTemperature(temperature);
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
      '#bec6e0'
    );
    try {
      await requestJson('/api/shutdown', { method: 'POST' });
      const closed = await waitForServerClose();
      if (closed) {
        showShutdownOverlay(
          'Server closed',
          'The local panel server has stopped. You can close this tab.',
          'check_circle',
          '#6ee7b7'
        );
      } else {
        showShutdownOverlay(
          'Shutdown requested',
          'The close command was sent, but the page could not verify that the server stopped yet.',
          'info',
          '#fcd34d'
        );
      }
    } catch (error) {
      const closed = await waitForServerClose();
      if (closed) {
        showShutdownOverlay(
          'Server closed',
          'The local panel server stopped after the close request. You can close this tab.',
          'check_circle',
          '#6ee7b7'
        );
      } else {
        showShutdownOverlay(
          'Close failed',
          error.message,
          'error',
          '#fda4af'
        );
        refreshTimer = setInterval(refreshState, 2000);
      }
    }
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
            remaining = None
            if self.running and self.phase_end_at is not None:
                remaining = max(0.0, self.phase_end_at - now)
            return {
                "running": self.running,
                "phase": self.phase,
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
            self.stop_event.set()
        thread = self.thread
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        logging.info("Web: cycle stop requested")
        return "Stopping cycle."

    def set_power_switch(self, enabled: bool) -> str:
        status = "on" if enabled else "off"
        prev = self.power_switch
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
        self._ensure_stopped_for_manual_command()
        if phase == "cooling":
            setpoint = float(self.cycle["cooling_setpoint_f"])
            label = "cooling"
        elif phase == "resting":
            setpoint = float(self.cycle["resting_setpoint_f"])
            label = "resting"
        else:
            raise ConfigError("phase must be cooling or resting")
        def updater(done: bool, error: str | None) -> None:
            if done:
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
        return status

    def _safe_apply_sync(self, setpoint_f: float, phase: str) -> None:
        if not self._safe_apply(setpoint_f, phase, threading.Event()):
            raise BackendError("Manual command cancelled")

    def _ensure_stopped_for_manual_command(self) -> None:
        with self.state_lock:
            if self.running:
                raise BackendError("Manual commands are disabled while the cycle is running. Stop the cycle first.")

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
        with self.command_lock:
            elapsed = time.monotonic() - self.last_command_at
            if self.last_command_at and elapsed < self.min_seconds_between_commands:
                wait_seconds = self.min_seconds_between_commands - elapsed
                logging.info("Safety wait: %.0f seconds", wait_seconds)
                if stop_event.wait(wait_seconds):
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
    def __init__(self, server_address: tuple[str, int], controller: WebController):
        super().__init__(server_address, RequestHandler)
        self.controller = controller


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
        controller.stop_cycle()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
