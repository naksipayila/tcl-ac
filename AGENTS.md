# AGENTS.md

## Safety
- `config.json` defaults to the real `tcl_home_aws` backend; do not run device-changing commands unless the user explicitly asks.
- Device-changing paths include CLI `once`, `run`, `startup` and web API POSTs to `/api/start`, `/api/power`, `/api/swing`, `/api/phase`, `/api/restart`, `/api/shutdown`.
- `status` and `/api/device-status` read the real device shadow when backend is `tcl_home_aws`; treat them as credentialed network calls.
- Loading the web page calls `/api/device-status` immediately via `loadInitialState`; `--no-browser` avoids that automatic read.
- For dry-run work, use backend `mock`; `MockBackend` logs actions and does not contact the AC.
- Never print, commit, or paste `TCL_SSO_TOKEN`, captured `ssotoken`, AWS credentials, Authorization headers, or cookies.

## Commands
- Install dependency: `py -m pip install -r requirements.txt`.
- Safe syntax check: `py -m py_compile web_app.py tcl_cycle.py`.
- Validate config without device commands: `py tcl_cycle.py validate --config config.json`; unresolved `TCL_SSO_TOKEN` makes validation fail.
- Run visible web panel: `py web_app.py --config config.json --no-browser`; default bind is `0.0.0.0:8787` for LAN access.
- Hidden launcher: double-click `start-server.cmd`; it runs `pyw.exe web_app.py --config config.json --no-browser`.
- CLI command effects: `once cooling` sends 70F, `once resting` sends 80F, `run` starts the 20 min 70F / 20 min 80F loop.

## Architecture
- `tcl_cycle.py` owns config loading/env expansion, logging, CLI, `CycleRunner`, `MockBackend`, and the AWS IoT Shadow backend.
- `web_app.py` owns the HTTP server, `WebController`, REST endpoints, restart/shutdown behavior, and all HTML/CSS/JS in the `PAGE_HTML` raw string.
- The web controller queues manual commands through one worker and enforces `safety.min_seconds_between_commands`; do not bypass `_safe_apply`.
- `config.json` sets cycle timings and safety values; `${TCL_SSO_TOKEN}` is expanded by `os.path.expandvars`.

## UI/Docs
- Trust current `web_app.py` over the README Web Panel table if labels differ; README can lag behind UI changes.
- Keep frontend edits inside `PAGE_HTML`; there are no separate static asset files except `favicon.png`.
- Current panel is compact and monochrome; keep UI labels English and keep buttons text-only except the power slider knob and shutdown overlay icons.
- Server controls and phone URL are intentionally hidden behind the small footer arrow toggle (`footerControls`).
- When `state.power_switch` is false, Start Cycle, Compressor, and Swing should render disabled/off and avoid sending commands.
- Power toggle is a confirmation slider: drag starts from `.power-slider-knob` and uses `POWER_SLIDE_THRESHOLD = 0.95`; do not replace it with a simple click toggle.
- `Close Server` stops the cycle and shuts down the process; `Restart Server` uses `os.execv` after socket close.

## Repo Notes
- There is no test suite, lint config, formatter config, CI, or package manifest beyond `requirements.txt`.
- Logs go to `logs/tcl_cycle.log`; `logs/`, `__pycache__/`, virtualenvs, and `opencode.json` are ignored by git.
- `opencode.json` is local/user-specific HTTP Toolkit MCP config; do not rely on it being present in other checkouts.
