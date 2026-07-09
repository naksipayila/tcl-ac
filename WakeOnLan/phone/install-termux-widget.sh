#!/data/data/com.termux/files/usr/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
SHORTCUT_DIR=$HOME/.shortcuts
SHORTCUT_FILE=$SHORTCUT_DIR/Wake-PC

mkdir -p "$SHORTCUT_DIR"

{
    printf '%s\n' '#!/data/data/com.termux/files/usr/bin/sh'
    printf '%s\n' 'set -eu'
    printf 'cd "%s"\n' "$ROOT_DIR"
    printf 'exec sh "%s/wake-pc.sh"\n' "$SCRIPT_DIR"
} > "$SHORTCUT_FILE"

chmod +x "$SHORTCUT_FILE"

echo "Created: $SHORTCUT_FILE"
echo "You can add the Wake-PC shortcut to the home screen from the Termux:Widget app."
