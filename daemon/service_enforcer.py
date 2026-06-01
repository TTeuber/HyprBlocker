"""Ensures the systemd unit stays enabled (auto-start symlink present).

`systemctl --user disable website-blocker` only removes the .wants symlink —
it doesn't signal the running daemon, so the SIGTERM-refusal in handle_signal()
never fires. This module detects the missing symlink and re-creates it.

Self-control friction only — no root, no sudo, no chattr.
Tied to the existing shutdown_prevention_enabled toggle.
"""

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

SERVICE_NAME = "website-blocker.service"
# Must match WantedBy= written by install.sh (see install.sh, [Install] section)
WANTED_BY_TARGET = "wayland-session@hyprland.desktop.target"

_SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"
_WANTS_SYMLINK = _SYSTEMD_USER_DIR / f"{WANTED_BY_TARGET}.wants" / SERVICE_NAME


def is_service_enabled() -> bool:
    """Cheap check: is the auto-start symlink present? (single lstat, no subprocess)."""
    return os.path.lexists(_WANTS_SYMLINK)


def ensure_service_enabled() -> bool:
    """Re-enable the unit if the .wants symlink was removed.

    Returns True if the service is (or was made) enabled, False on failure.
    Cheap in the common case: lexists short-circuits before any subprocess.
    """
    if is_service_enabled():
        return True

    logger.warning(
        "Auto-start symlink missing (service was disabled); re-enabling"
    )
    try:
        result = subprocess.run(
            ["systemctl", "--user", "enable", SERVICE_NAME],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            logger.info("Re-enabled website-blocker service (disable-prevention active)")
            return True
        logger.error(
            f"Failed to re-enable service: {result.stderr.decode().strip()}"
        )
        return False
    except Exception as e:
        logger.error(f"Failed to re-enable service: {e}")
        return False
