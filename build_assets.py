from __future__ import annotations

import pathlib

from PIL import Image


ASSET_DIR = pathlib.Path("assets")
PNG_PATH = ASSET_DIR / "fan.png"
ICO_PATH = ASSET_DIR / "fan.ico"


def main() -> int:
    if not PNG_PATH.exists():
        raise SystemExit(f"Missing icon: {PNG_PATH}")

    ASSET_DIR.mkdir(exist_ok=True)
    image = Image.open(PNG_PATH).convert("RGBA")
    image.save(
        ICO_PATH,
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"Wrote {ICO_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
