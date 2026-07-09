#!/data/data/com.termux/files/usr/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

if command -v termux-wake-lock >/dev/null 2>&1; then
    termux-wake-lock || true
fi

if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo "Python was not found. In Termux: pkg install python"
    exit 1
fi

exec "$PYTHON" "$ROOT_DIR/relay/cloudflare_wol_relay.py" \
    --config "$ROOT_DIR/relay/web-config.env" \
    "$@"
