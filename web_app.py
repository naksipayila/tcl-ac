from __future__ import annotations

import argparse
import collections
import json
import logging
import pathlib
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
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TCL Klima Paneli</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #080b10;
      --card: rgba(18, 24, 33, 0.86);
      --card-2: rgba(255, 255, 255, 0.045);
      --line: rgba(255, 255, 255, 0.09);
      --text: #f3f7fb;
      --muted: #8d98a8;
      --blue: #62a8ff;
      --green: #38d47a;
      --red: #ff5d5d;
      --amber: #ffc35a;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: Inter, "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
      background:
        radial-gradient(circle at 18% 0%, rgba(98, 168, 255, 0.18), transparent 34%),
        linear-gradient(180deg, #0b1018, var(--bg));
      color: var(--text);
    }
    main {
      width: min(920px, calc(100% - 28px));
      margin: 0 auto;
      padding: 22px 0;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
    }
    h1 { margin: 0; font-size: 22px; letter-spacing: -0.03em; }
    .sub { margin-top: 3px; color: var(--muted); font-size: 12px; }
    .phone-url { margin-top: 4px; color: var(--blue); font-size: 12px; font-weight: 700; }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      min-width: 132px;
      justify-content: center;
      padding: 8px 11px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.045);
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--red); }
    .running .dot { background: var(--green); box-shadow: 0 0 14px rgba(56, 212, 122, 0.72); }
    .panel, details {
      border: 1px solid var(--line);
      border-radius: 18px;
      background: var(--card);
      box-shadow: 0 18px 55px rgba(0, 0, 0, 0.28);
      backdrop-filter: blur(18px);
    }
    .panel { padding: 16px; }
    .topline {
      display: grid;
      grid-template-columns: 1.05fr 1fr;
      gap: 12px;
      align-items: stretch;
    }
    .phase-card, .stat {
      border: 1px solid var(--line);
      border-radius: 15px;
      background: var(--card-2);
    }
    .phase-card {
      min-height: 150px;
      padding: 18px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }
    .label {
      color: var(--muted);
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.16em;
      text-transform: uppercase;
    }
    .phase { margin-top: 8px; font-size: clamp(34px, 8vw, 58px); line-height: 0.94; letter-spacing: -0.07em; }
    .remaining { color: var(--blue); font-size: 22px; font-weight: 800; }
    .last { margin-top: 10px; color: var(--muted); font-size: 12px; line-height: 1.45; }
    .stats { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; }
    .stat { padding: 12px; }
    .stat b { display: block; margin-bottom: 3px; font-size: 22px; line-height: 1; }
    .stat span { color: var(--muted); font-size: 11px; }
    .temp-stat { grid-column: 1 / -1; }
    .temp-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 5px; }
    .temp-row b { margin: 0; font-size: 32px; color: var(--blue); }
    .temp-row button { min-height: 32px; padding: 6px 10px; font-size: 12px; }
    .temp-meta { margin-top: 5px; color: var(--muted); font-size: 11px; line-height: 1.35; }
    .actions {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 9px;
      margin-top: 12px;
    }
    button {
      appearance: none;
      border: 1px solid var(--line);
      border-radius: 13px;
      background: rgba(255, 255, 255, 0.065);
      color: var(--text);
      min-height: 40px;
      padding: 9px 11px;
      font: inherit;
      font-size: 13px;
      font-weight: 800;
      cursor: pointer;
      transition: transform 0.12s ease, border-color 0.12s ease, background 0.12s ease;
    }
    button:hover:not(:disabled) { transform: translateY(-1px); border-color: rgba(98, 168, 255, 0.65); }
    button:disabled { opacity: 0.42; cursor: not-allowed; }
    .primary { background: rgba(56, 212, 122, 0.18); border-color: rgba(56, 212, 122, 0.38); }
    .danger { background: rgba(255, 93, 93, 0.15); border-color: rgba(255, 93, 93, 0.35); }
    .cool { background: rgba(98, 168, 255, 0.18); border-color: rgba(98, 168, 255, 0.38); }
    .warm { background: rgba(255, 195, 90, 0.18); border-color: rgba(255, 195, 90, 0.38); }
    .wide { grid-column: span 2; }
    .message { min-height: 18px; margin-top: 10px; color: var(--muted); font-size: 12px; }
    .message.error { color: var(--red); }
    .message.ok { color: var(--green); }
    .details-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px; }
    details { overflow: hidden; }
    summary {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 12px 14px;
      cursor: pointer;
      color: var(--text);
      font-size: 13px;
      font-weight: 800;
      list-style: none;
    }
    summary::-webkit-details-marker { display: none; }
    .summary-note { color: var(--muted); font-size: 11px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    pre {
      max-height: 260px;
      margin: 0;
      padding: 12px 14px 14px;
      border-top: 1px solid var(--line);
      overflow: auto;
      white-space: pre-wrap;
      background: rgba(0, 0, 0, 0.18);
      color: #cfd8e3;
      font-size: 12px;
      line-height: 1.42;
    }
    @media (max-width: 760px) {
      main { width: min(100% - 18px, 920px); padding: 12px 0; }
      header { align-items: flex-start; }
      .topline, .details-grid { grid-template-columns: 1fr; }
      .actions { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>TCL Klima</h1>
        <div class="sub">Local panel | 70F / 80F cycle</div>
        <div id="phoneUrl" class="phone-url">Telefon URL yukleniyor...</div>
      </div>
      <div id="runPill" class="pill"><span class="dot"></span><span id="runText">Yukleniyor</span></div>
    </header>

    <section class="panel">
      <div class="topline">
        <div class="phase-card">
          <div>
            <div class="label">Aktif faz</div>
            <div id="phase" class="phase">-</div>
          </div>
          <div>
            <div id="remaining" class="remaining">--:--</div>
            <div id="lastAction" class="last">Son islem bekleniyor.</div>
          </div>
        </div>

        <div class="stats">
          <div class="stat temp-stat">
            <span>Klima ayari</span>
            <div class="temp-row">
              <b id="activeTempF">--</b>
              <button onclick="readDeviceStatus()">Yenile</button>
            </div>
            <div id="activeTempMeta" class="temp-meta">Henuz okunmadi.</div>
          </div>
          <div class="stat"><b id="coolingSetpoint">70F</b><span>Sogutma hedefi</span></div>
          <div class="stat"><b id="restingSetpoint">80F</b><span>Dinlenme hedefi</span></div>
          <div class="stat"><b id="coolingMinutes">20</b><span>Sogutma dakika</span></div>
          <div class="stat"><b id="restingMinutes">20</b><span>Dinlenme dakika</span></div>
        </div>
      </div>

      <div class="actions">
        <button id="startBtn" class="primary" onclick="postAction('/api/start')">Baslat</button>
        <button id="stopBtn" class="danger" onclick="postAction('/api/stop')">Durdur</button>
        <button id="coolBtn" class="cool" onclick="sendPhase('cooling')">70F</button>
        <button id="restBtn" class="warm" onclick="sendPhase('resting')">80F</button>
        <button id="startupBtn" onclick="postAction('/api/startup')">Swing</button>
        <button onclick="readDeviceStatus()">Yenile</button>
        <button class="wide" onclick="shutdownServer()">Serveri Kapat</button>
      </div>
      <div id="message" class="message"></div>
    </section>

    <section class="details-grid">
      <details>
        <summary><span>Canli Log</span><span id="configPath" class="summary-note"></span></summary>
        <pre id="logs">Loglar yukleniyor...</pre>
      </details>

      <details>
        <summary><span>Cihaz Status</span><span class="summary-note">Yenile butonu okur</span></summary>
        <pre id="deviceStatus">Henuz okunmadi.</pre>
      </details>
    </section>
  </main>

  <script>
    const message = document.getElementById('message');

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
      if (!timestamp) return 'Henuz okunmadi';
      const seconds = Math.max(0, Math.floor(Date.now() / 1000 - timestamp));
      if (seconds < 60) return seconds + ' sn once';
      const minutes = Math.floor(seconds / 60);
      if (minutes < 60) return minutes + ' dk once';
      return Math.floor(minutes / 60) + ' sa once';
    }

    function setMessage(text, kind) {
      message.textContent = text || '';
      message.className = 'message ' + (kind || '');
    }

    function renderTemperature(temperature) {
      const value = document.getElementById('activeTempF');
      const meta = document.getElementById('activeTempMeta');
      if (!temperature) {
        value.textContent = '--';
        meta.textContent = 'Henuz okunmadi.';
        meta.title = '';
        return;
      }
      if (temperature.error) {
        value.textContent = '--';
        meta.textContent = 'Hata: ' + temperature.error;
        meta.title = '';
        return;
      }
      if (temperature.fahrenheit === null || temperature.fahrenheit === undefined) {
        value.textContent = '--';
        meta.textContent = temperature.updated_at ? 'Status okundu, hedef derece alani bulunamadi.' : 'Henuz okunmadi.';
        meta.title = '';
        return;
      }
      value.textContent = fmtTemperature(temperature.fahrenheit, 'F');
      meta.textContent = fmtTemperature(temperature.celsius, 'C') + ' | Son okuma ' + fmtAge(temperature.updated_at);
      meta.title = temperature.source ? 'Kaynak: ' + temperature.source : '';
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
        setMessage(error.message, 'error');
      }
    }

    function renderState(state) {
      const pill = document.getElementById('runPill');
      pill.classList.toggle('running', state.running);
      document.getElementById('runText').textContent = state.running ? 'Dongu calisiyor' : 'Dongu durdu';
      document.getElementById('phase').textContent = state.phase || 'stopped';
      document.getElementById('remaining').textContent = fmtSeconds(state.remaining_seconds);
      document.getElementById('lastAction').textContent = state.last_action || 'Son islem yok.';
      document.getElementById('coolingSetpoint').textContent = state.cycle.cooling_setpoint_f + 'F';
      document.getElementById('restingSetpoint').textContent = state.cycle.resting_setpoint_f + 'F';
      document.getElementById('coolingMinutes').textContent = state.cycle.cooling_minutes;
      document.getElementById('restingMinutes').textContent = state.cycle.resting_minutes;
      document.getElementById('configPath').textContent = state.config_path;
      document.getElementById('logs').textContent = state.logs.length ? state.logs.join('\n') : 'Log yok.';
      const phoneUrl = document.getElementById('phoneUrl');
      const urls = state.network_urls || [];
      if (urls.length) {
        phoneUrl.textContent = 'Telefon: ' + urls[0];
        phoneUrl.title = urls.join('\n');
      } else {
        phoneUrl.textContent = 'Telefon erisimi icin ayni Wi-Fi gerekli';
        phoneUrl.title = state.local_url || '';
      }
      renderTemperature(state.active_temperature);
      document.getElementById('startBtn').disabled = state.running;
      document.getElementById('stopBtn').disabled = !state.running;
      document.getElementById('startupBtn').disabled = state.running;
      document.getElementById('coolBtn').disabled = state.running;
      document.getElementById('restBtn').disabled = state.running;
      if (state.last_error) setMessage(state.last_error, 'error');
    }

    async function postAction(path) {
      try {
        const data = await requestJson(path, { method: 'POST' });
        setMessage(data.message || 'Tamam.', 'ok');
        renderState(data.state);
      } catch (error) {
        setMessage(error.message, 'error');
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
        setMessage(data.message || 'Komut gonderildi.', 'ok');
        renderState(data.state);
      } catch (error) {
        setMessage(error.message, 'error');
        refreshState();
      }
    }

    async function readDeviceStatus() {
      try {
        setMessage('Cihaz durumu okunuyor...', '');
        const data = await requestJson('/api/device-status');
        document.getElementById('deviceStatus').textContent = JSON.stringify(data.device_status, null, 2);
        if (data.state) renderState(data.state);
        const temperature = data.active_temperature || (data.state && data.state.active_temperature);
        renderTemperature(temperature);
        if (temperature && temperature.fahrenheit !== null && temperature.fahrenheit !== undefined) {
          setMessage('Klima ayari yenilendi: ' + fmtTemperature(temperature.fahrenheit, 'F'), 'ok');
        } else {
          setMessage('Status okundu, hedef derece alani bulunamadi.', 'ok');
        }
      } catch (error) {
        setMessage(error.message, 'error');
      }
    }

    async function shutdownServer() {
      if (!confirm('Panel serveri kapatilsin mi? Dongu de durdurulur.')) return;
      try {
        await requestJson('/api/shutdown', { method: 'POST' });
        setMessage('Panel serveri kapatiliyor. Bu sekmeyi kapatabilirsin.', 'ok');
      } catch (error) {
        setMessage(error.message, 'error');
      }
    }

    refreshState();
    setInterval(refreshState, 2000);
  </script>
</body>
</html>
"""


class MemoryLogHandler(logging.Handler):
    def __init__(self, limit: int = 250):
        super().__init__(logging.INFO)
        self.records: collections.deque[str] = collections.deque(maxlen=limit)
        self.records_lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:
            message = record.getMessage()
        with self.records_lock:
            self.records.append(message)

    def tail(self, limit: int = 120) -> list[str]:
        with self.records_lock:
            return list(self.records)[-limit:]


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
    def __init__(self, config_path: pathlib.Path, log_handler: MemoryLogHandler, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.config_path = config_path
        self.log_handler = log_handler
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
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.last_command_at = 0.0
        self.running = False
        self.phase = "stopped"
        self.cycle_number = 0
        self.phase_started_at: float | None = None
        self.phase_end_at: float | None = None
        self.started_at: float | None = None
        self.stopped_at: float | None = None
        self.last_action = "Panel ready."
        self.last_error: str | None = None
        self.active_temperature = empty_temperature()

    def snapshot(self) -> dict[str, Any]:
        with self.state_lock:
            now = time.time()
            remaining = None
            if self.running and self.phase_end_at is not None:
                remaining = max(0.0, self.phase_end_at - now)
            return {
                "running": self.running,
                "phase": self.phase,
                "cycle_number": self.cycle_number,
                "phase_started_at": self.phase_started_at,
                "phase_end_at": self.phase_end_at,
                "remaining_seconds": remaining,
                "started_at": self.started_at,
                "stopped_at": self.stopped_at,
                "last_action": self.last_action,
                "last_error": self.last_error,
                "backend": str(self.config.get("backend", "mock")),
                "config_path": str(self.config_path),
                "local_url": browser_url(self.host, self.port),
                "network_urls": network_urls(self.host, self.port),
                "cycle": {
                    "cooling_setpoint_f": float(self.cycle["cooling_setpoint_f"]),
                    "resting_setpoint_f": float(self.cycle["resting_setpoint_f"]),
                    "cooling_minutes": float(self.cycle["cooling_minutes"]),
                    "resting_minutes": float(self.cycle["resting_minutes"]),
                },
                "active_temperature": dict(self.active_temperature),
                "logs": self.log_handler.tail(),
            }

    def start_cycle(self) -> str:
        with self.state_lock:
            if self.running:
                return "Dongu zaten calisiyor."
            self.stop_event = threading.Event()
            self.running = True
            self.phase = "starting"
            self.phase_started_at = None
            self.phase_end_at = None
            self.started_at = time.time()
            self.stopped_at = None
            self.last_error = None
            self.last_action = "Dongu baslatildi."
            self.thread = threading.Thread(target=self._run_cycle, name="tcl-web-cycle", daemon=True)
            self.thread.start()
        logging.info("Web: cycle start requested")
        return "Dongu baslatildi."

    def stop_cycle(self) -> str:
        with self.state_lock:
            if not self.running:
                return "Dongu zaten durmus."
            self.stop_event.set()
            self.last_action = "Dongu durduruluyor."
        thread = self.thread
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        logging.info("Web: cycle stop requested")
        return "Dongu durduruluyor."

    def send_startup(self) -> str:
        self._ensure_stopped_for_manual_command()
        with self.command_lock:
            logging.info("Web: startup command requested")
            self.backend.startup()
        with self.state_lock:
            self.last_action = "Swing baslangic komutu gonderildi."
            self.last_error = None
        return "Swing baslangic komutu gonderildi."

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
        if not self._safe_apply(setpoint, label, threading.Event()):
            raise BackendError("Manual command cancelled")
        with self.state_lock:
            self.last_action = f"{setpoint:g}F {label} komutu gonderildi."
            self.last_error = None
        return f"{setpoint:g}F komutu gonderildi."

    def read_device_status(self) -> Any:
        with self.command_lock:
            logging.info("Web: device status requested")
            status = self.backend.status()
        temperature = extract_active_temperature(status)
        with self.state_lock:
            self.active_temperature = temperature
        return status

    def _ensure_stopped_for_manual_command(self) -> None:
        with self.state_lock:
            if self.running:
                raise BackendError("Dongu calisirken manuel komut gonderme kapali. Once donguyu durdur.")

    def _run_cycle(self) -> None:
        try:
            with self.command_lock:
                logging.info("Web: sending startup command before cycle")
                self.backend.startup()
            while not self.stop_event.is_set():
                with self.state_lock:
                    self.cycle_number += 1
                    cycle_number = self.cycle_number
                    self.last_action = f"Cycle {cycle_number} basladi."
                logging.info("Web cycle %d started", cycle_number)

                if not self._run_phase("cooling", float(self.cycle["cooling_setpoint_f"]), float(self.cycle["cooling_minutes"])):
                    break
                if not self._run_phase("resting", float(self.cycle["resting_setpoint_f"]), float(self.cycle["resting_minutes"])):
                    break
                logging.info("Web cycle %d finished", cycle_number)
        except Exception as exc:
            logging.exception("Web cycle failed")
            with self.state_lock:
                self.last_error = str(exc)
                self.last_action = "Dongu hata ile durdu."
        finally:
            with self.state_lock:
                self.running = False
                self.phase = "stopped"
                self.phase_started_at = None
                self.phase_end_at = None
                self.stopped_at = time.time()
                if self.last_error is None:
                    self.last_action = "Dongu durdu."
            logging.info("Web cycle stopped")

    def _run_phase(self, phase: str, setpoint_f: float, minutes: float) -> bool:
        now = time.time()
        with self.state_lock:
            self.phase = phase
            self.phase_started_at = now
            self.phase_end_at = now + (minutes * 60.0)
            self.last_action = f"{phase} fazi: {setpoint_f:g}F hedef gonderiliyor."
        if not self._safe_apply(setpoint_f, phase, self.stop_event):
            return False
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
        if parsed.path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
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
            if parsed.path == "/api/startup":
                message = self.server.controller.send_startup()
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
    log_handler = MemoryLogHandler()
    log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger().addHandler(log_handler)

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        controller = WebController(pathlib.Path(args.config), log_handler, args.host, args.port)
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
