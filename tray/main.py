#!/usr/bin/env python3
"""System tray application for Website Blocker."""

# CRITICAL: Set backend BEFORE importing pystray
import os
os.environ["PYSTRAY_BACKEND"] = "appindicator"

import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Optional

import requests
from PIL import Image
import pystray


@dataclass
class DaemonStatus:
    """Represents the daemon status."""
    running: bool
    active_rules: int
    active_blocks: int
    browsers_detected: int
    browsers_compliant: int


class DaemonClient:
    """Minimal client for checking daemon status."""

    def __init__(self, base_url: str = "http://127.0.0.1:8765"):
        self.base_url = base_url.rstrip('/')
        self.timeout = 5

    def is_daemon_running(self) -> bool:
        """Check if the daemon is reachable."""
        try:
            response = requests.get(
                f"{self.base_url}/api/status",
                timeout=self.timeout
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def get_status(self) -> Optional[DaemonStatus]:
        """Get the daemon status."""
        try:
            response = requests.get(
                f"{self.base_url}/api/status",
                timeout=self.timeout
            )
            if response.status_code == 200:
                data = response.json()
                return DaemonStatus(**data)
        except requests.RequestException:
            pass
        return None


class TrayApp:
    """System tray application for Website Blocker."""

    def __init__(self):
        self.client = DaemonClient()
        self.icon: Optional[pystray.Icon] = None
        self.running = True
        self._status_text = "Checking..."

        # Load icon
        self.tray_icon = self._load_icon("icon-tray-22.png")

    def _get_icon_paths(self, name: str) -> list[str]:
        """Get list of possible icon paths."""
        paths = []

        # PyInstaller bundled path
        if hasattr(sys, '_MEIPASS'):
            paths.append(os.path.join(sys._MEIPASS, 'icons', name))

        # Development path (relative to script)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        paths.append(os.path.join(script_dir, '..', 'icons', name))

        # Installed path
        paths.append(os.path.expanduser(
            f'~/.local/share/website-blocker/icons/{name}'
        ))

        return paths

    def _load_icon(self, name: str) -> Image.Image:
        """Load icon from various possible locations."""
        for path in self._get_icon_paths(name):
            if os.path.exists(path):
                return Image.open(path)

        # Fallback: create a simple colored square
        img = Image.new('RGB', (22, 22), color='#3b82f6')
        return img

    def _get_status_text(self) -> str:
        """Get current daemon status for menu display."""
        return self._status_text

    def _update_status(self):
        """Background thread to update daemon status."""
        while self.running:
            try:
                if self.client.is_daemon_running():
                    status = self.client.get_status()
                    if status:
                        self._status_text = (
                            f"Running - {status.active_blocks} active blocks"
                        )
                    else:
                        self._status_text = "Running"
                else:
                    self._status_text = "Daemon Stopped"
            except Exception:
                self._status_text = "Error checking status"

            # Update menu
            if self.icon:
                self.icon.update_menu()

            time.sleep(5)

    def _get_desktop_app_paths(self) -> list[str]:
        """Get list of possible desktop app executable paths."""
        paths = []

        # Installed location
        paths.append(os.path.expanduser('~/.local/bin/website-blocker'))

        # Development location
        script_dir = os.path.dirname(os.path.abspath(__file__))
        dev_python = os.path.join(script_dir, '..', 'desktop-app', '.venv', 'bin', 'python')
        dev_main = os.path.join(script_dir, '..', 'desktop-app', 'main.py')
        if os.path.exists(dev_python) and os.path.exists(dev_main):
            paths.append((dev_python, dev_main))

        return paths

    def _open_desktop_app(self):
        """Launch the desktop application."""
        for path in self._get_desktop_app_paths():
            if isinstance(path, tuple):
                # Development mode: (python, main.py)
                python_path, main_path = path
                if os.path.exists(python_path) and os.path.exists(main_path):
                    subprocess.Popen(
                        [python_path, main_path],
                        start_new_session=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    return
            elif os.path.exists(path):
                subprocess.Popen(
                    [path],
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return

        print("Could not find desktop app executable", file=sys.stderr)

    def _quit(self):
        """Quit the tray application."""
        self.running = False
        if self.icon:
            self.icon.stop()

    def _create_menu(self) -> pystray.Menu:
        """Create the tray menu."""
        return pystray.Menu(
            pystray.MenuItem(
                lambda text: self._get_status_text(),
                None,
                enabled=False
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Open Website Blocker', lambda: self._open_desktop_app()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit', lambda: self._quit())
        )

    def run(self):
        """Run the tray application."""
        # Start status update thread
        status_thread = threading.Thread(target=self._update_status, daemon=True)
        status_thread.start()

        # Create and run tray icon
        self.icon = pystray.Icon(
            name="website-blocker",
            icon=self.tray_icon,
            title="Website Blocker",
            menu=self._create_menu()
        )

        self.icon.run()


def main():
    app = TrayApp()
    app.run()


if __name__ == '__main__':
    main()
