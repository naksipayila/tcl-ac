from __future__ import annotations

import argparse
import ctypes
import logging
import os
import pathlib
import sys
import threading
import webbrowser
from typing import Any

from tcl_cycle import CONFIG_DEFAULT, BackendError, ConfigError, setup_logging
from web_app import DEFAULT_HOST, DEFAULT_PORT, MemoryLogHandler, WebController, WebServer, browser_url, network_urls

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError as exc:
    pystray = None
    Image = None
    ImageDraw = None
    MISSING_IMPORT: ImportError | None = exc
else:
    MISSING_IMPORT = None


APP_NAME = "TCL AC Panel"
ICON_PATH = pathlib.Path("assets") / "fan.png"


def app_dir() -> pathlib.Path:
    if getattr(sys, "frozen", False):
        return pathlib.Path(sys.executable).resolve().parent
    return pathlib.Path(__file__).resolve().parent


def bundled_dir() -> pathlib.Path | None:
    bundle = getattr(sys, "_MEIPASS", None)
    if not bundle:
        return None
    return pathlib.Path(bundle).resolve()


def resource_path(relative_path: pathlib.Path) -> pathlib.Path:
    candidates = [app_dir() / relative_path]
    bundle = bundled_dir()
    if bundle is not None:
        candidates.append(bundle / relative_path)
    candidates.append(pathlib.Path.cwd() / relative_path)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def default_config_path() -> pathlib.Path:
    config_path = app_dir() / CONFIG_DEFAULT
    if config_path.exists():
        return config_path
    return pathlib.Path(CONFIG_DEFAULT)


def show_error(title: str, message: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
    except Exception:
        logging.error("%s: %s", title, message)


def load_tray_image() -> Any:
    if Image is None or ImageDraw is None:
        raise RuntimeError("Pillow is required for the tray icon")

    icon_file = resource_path(ICON_PATH)
    if icon_file.exists():
        return Image.open(icon_file).convert("RGBA")

    image = Image.new("RGBA", (64, 64), (13, 17, 23, 255))
    draw = ImageDraw.Draw(image)
    draw.ellipse((6, 6, 58, 58), fill=(31, 111, 235, 255))
    draw.ellipse((24, 24, 40, 40), fill=(230, 237, 243, 255))
    for box in [(28, 4, 36, 28), (36, 28, 60, 36), (28, 36, 36, 60), (4, 28, 28, 36)]:
        draw.rounded_rectangle(box, radius=4, fill=(230, 237, 243, 230))
    return image


class TrayApp:
    def __init__(self, config_path: pathlib.Path, host: str, port: int, open_browser: bool):
        self.config_path = config_path
        self.host = host
        self.port = port
        self.open_browser_at_start = open_browser
        self.bind_url = f"http://{host}:{port}/"
        self.url = browser_url(host, port)
        self.log_handler = MemoryLogHandler()
        self.log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logging.getLogger().addHandler(self.log_handler)

        self.controller = WebController(config_path, self.log_handler, host, port)
        self.server = WebServer((host, port), self.controller)
        self.server_thread = threading.Thread(target=self.server.serve_forever, name="tcl-web-server", daemon=True)
        self.icon = pystray.Icon("tcl_klima_panel", load_tray_image(), APP_NAME, self._menu())

    def _menu(self) -> Any:
        return pystray.Menu(
            pystray.MenuItem("Open Panel", self.open_panel, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Start Cycle", self.start_cycle),
            pystray.MenuItem("Stop Cycle", self.stop_cycle),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Swing Startup", self.send_startup),
            pystray.MenuItem("Send 70F", self.send_cooling),
            pystray.MenuItem("Send 80F", self.send_resting),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self.quit),
        )

    def run(self) -> None:
        logging.info("Starting tray app with config %s", self.config_path)
        self.server_thread.start()
        logging.info("Local web panel listening on %s", self.bind_url)
        for url in network_urls(self.host, self.port):
            logging.info("Phone URL: %s", url)
        if self.open_browser_at_start:
            threading.Timer(0.6, self.open_panel).start()
        self.icon.run()

    def open_panel(self, *args: Any) -> None:
        webbrowser.open(self.url)

    def start_cycle(self, *args: Any) -> None:
        self._run_action("Cycle started.", self.controller.start_cycle)

    def stop_cycle(self, *args: Any) -> None:
        self._run_action("Stopping cycle.", self.controller.stop_cycle)

    def send_startup(self, *args: Any) -> None:
        self._run_action("Swing startup command sent.", self.controller.send_startup)

    def send_cooling(self, *args: Any) -> None:
        self._run_action("70F command sent.", lambda: self.controller.send_phase("cooling"))

    def send_resting(self, *args: Any) -> None:
        self._run_action("80F command sent.", lambda: self.controller.send_phase("resting"))

    def quit(self, *args: Any) -> None:
        logging.info("Tray exit requested")
        try:
            self.controller.stop_cycle()
            self.server.shutdown()
            self.server_thread.join(timeout=4.0)
            self.server.server_close()
        finally:
            self.icon.stop()

    def _run_action(self, success_message: str, action: Any) -> None:
        thread = threading.Thread(
            target=self._execute_action,
            args=(success_message, action),
            name="tcl-tray-action",
            daemon=True,
        )
        thread.start()

    def _execute_action(self, success_message: str, action: Any) -> None:
        try:
            message = action() or success_message
            logging.info("Tray action: %s", message)
            self._notify(message)
        except (BackendError, ConfigError) as exc:
            logging.error("Tray action failed: %s", exc)
            self._notify(str(exc))
        except Exception as exc:
            logging.exception("Tray action crashed")
            self._notify(str(exc))

    def _notify(self, message: str) -> None:
        try:
            self.icon.notify(message, APP_NAME)
        except Exception:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Windows tray app for the TCL AC web panel")
    parser.add_argument("--config", default=str(default_config_path()), help="Config file path")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host to bind, default allows LAN access with 0.0.0.0")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to listen on")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser automatically")
    return parser


def main(argv: list[str] | None = None) -> int:
    os.chdir(app_dir())
    setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)

    if MISSING_IMPORT is not None:
        message = f"Missing dependency: {MISSING_IMPORT}\n\nRun: py -m pip install -r requirements.txt"
        logging.error(message)
        show_error(APP_NAME, message)
        return 1

    try:
        app = TrayApp(pathlib.Path(args.config), args.host, args.port, not args.no_browser)
    except (ConfigError, BackendError, OSError) as exc:
        message = str(exc)
        logging.error("Could not start tray app: %s", message)
        show_error(APP_NAME, message)
        return 1

    try:
        app.run()
    except KeyboardInterrupt:
        app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
