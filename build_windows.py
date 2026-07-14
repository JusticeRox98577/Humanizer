"""Build a standalone Humanizer.exe for Windows.

Usage (in the repo root, on Windows):

    pip install pyinstaller
    pip install pywebview        # optional, for a true native window
    python build_windows.py

The result is dist\\Humanizer.exe — a single file you can double-click or make
a shortcut to. It bundles the web UI and needs no Python install to run.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is not installed. Run:\n    pip install pyinstaller")
        return 1

    have_webview = False
    try:
        import webview  # noqa: F401

        have_webview = True
    except ImportError:
        pass

    sep = ";" if os.name == "nt" else ":"
    args = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "Humanizer",
        f"--add-data=humanizer/web/index.html{sep}humanizer/web",
        "--collect-submodules", "humanizer",
        "--noconfirm",
        "--clean",
    ]

    icon = ROOT / "humanizer" / "web" / "icon.ico"
    if icon.exists():
        args += ["--icon", str(icon)]

    if have_webview:
        args.append("--noconsole")  # true windowed app; closing the window exits
        args += ["--collect-all", "webview"]
    else:
        print("Note: pywebview not found -> building the browser-based app "
              "(keeps a small console window you close to stop it).")
        print("      For a true app window:  pip install pywebview  then rebuild.")

    args.append("run_app.py")

    print("Running:\n   ", " ".join(args), "\n")
    code = subprocess.call(args, cwd=str(ROOT))
    if code == 0:
        print("\nDone. Your app is at:  dist" + os.sep + "Humanizer.exe")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
