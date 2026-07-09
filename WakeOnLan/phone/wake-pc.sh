#!/data/data/com.termux/files/usr/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
CONFIG_FILE=${WOL_CONFIG:-"$SCRIPT_DIR/config.env"}

if [ -f "$CONFIG_FILE" ]; then
    # shellcheck disable=SC1090
    . "$CONFIG_FILE"
fi

case "${1:-}" in
    "")
        MAC=${WOL_MAC:-}
        ;;
    -*)
        MAC=${WOL_MAC:-}
        ;;
    *)
        MAC=$1
        shift
        ;;
esac

if [ -z "${MAC:-}" ]; then
    echo "Usage: sh phone/wake-pc.sh AA:BB:CC:DD:EE:FF"
    echo "Or set WOL_MAC in phone/config.env."
    exit 2
fi

if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
elif command -v python.exe >/dev/null 2>&1; then
    PYTHON=python.exe
else
    echo "Python was not found. If you are running this in Termux: pkg install python"
    exit 1
fi

exec "$PYTHON" "$ROOT_DIR/wol.py" "$MAC" \
    --broadcast "${WOL_BROADCAST:-255.255.255.255}" \
    --port "${WOL_PORT:-9}" \
    --repeat "${WOL_REPEAT:-3}" \
    "$@"
