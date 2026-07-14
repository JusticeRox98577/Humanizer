"""Run Humanizer as a desktop app.

Starts the local server on a free port in a background thread, then shows the
UI in a native window if ``pywebview`` is installed (best experience — feels
like a real Windows app), otherwise falls back to opening the default browser.

Either way there is nothing to `cd` into and no server to restart: launch it,
use it, close the window.
"""

from __future__ import annotations

import socket
import threading
from http.server import ThreadingHTTPServer

from .server import Handler


def _free_port(host: str = "127.0.0.1") -> int:
    """Ask the OS for an unused TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def start_background_server(port: int | None = None, host: str = "127.0.0.1"):
    """Start the HTTP server in a daemon thread. Returns (httpd, url)."""
    port = port or _free_port(host)
    httpd = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://{host}:{port}"


def run_app(port: int | None = None, prefer_window: bool = True) -> None:
    """Launch the desktop app and block until the window/console is closed."""
    httpd, url = start_background_server(port)

    shown_in_window = False
    if prefer_window:
        try:
            import webview  # pywebview

            webview.create_window(
                "Humanizer",
                url,
                width=1240,
                height=880,
                min_size=(940, 680),
            )
            webview.start()  # blocks until the window is closed
            shown_in_window = True
        except Exception:
            shown_in_window = False  # not installed / no WebView2 -> browser

    if not shown_in_window:
        import webbrowser

        webbrowser.open(url)
        print(f"Humanizer is running at {url}")
        print("Keep this window open while you use the app. Close it to stop.")
        try:
            threading.Event().wait()  # keep the process (and server) alive
        except KeyboardInterrupt:
            pass

    httpd.shutdown()
