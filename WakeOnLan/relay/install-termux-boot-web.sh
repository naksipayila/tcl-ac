#!/data/data/com.termux/files/usr/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
BOOT_DIR=$HOME/.termux/boot
BOOT_FILE=$BOOT_DIR/wol-web-relay
LOG_FILE=$HOME/wol-web-relay.log

mkdir -p "$BOOT_DIR"

{
    printf '%s\n' '#!/data/data/com.termux/files/usr/bin/sh'
    printf '%s\n' 'set -eu'
    printf '%s\n' 'termux-wake-lock || true'
    printf 'cd "%s"\n' "$ROOT_DIR"
    printf 'sh "%s/relay/run-web-relay.sh" >> "%s" 2>&1 &\n' "$ROOT_DIR" "$LOG_FILE"
} > "$BOOT_FILE"

chmod +x "$BOOT_FILE"

echo "Created: $BOOT_FILE"
echo "If Termux:Boot is installed, the Cloudflare WOL relay will start automatically when the phone boots."
echo "Log file: $LOG_FILE"
