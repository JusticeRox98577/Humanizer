"""Entry point for the packaged Windows app (used by PyInstaller).

Double-clicking the built Humanizer.exe runs this, which starts the local
server and opens the app window.
"""

from humanizer.desktop import run_app

if __name__ == "__main__":
    run_app()
