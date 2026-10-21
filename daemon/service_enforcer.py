"""Keeps the systemd unit and native-messaging registration intact.

Two layers, split by who owns the files being defended:

- **User-side** (safe for the unprivileged daemon to run; the three existing
  call sites): re-create the auto-start ``.wants`` symlink if it was removed, and
  in the root layout delete any user-writable *shadow* files that would override
  the root-owned copies — a shadow unit at ``~/.config/systemd/user/`` (which
  takes precedence over ``/etc/systemd/user/``) or a user-level native-messaging
  manifest pointing at a stubbed host.

- **Root-side** (run by the enforcer, which owns ``/etc``): verify the canonical
  unit content and system-wide manifests are intact and rewrite them if tampered.

Historically this module only guarded the ``.wants`` symlink — the migration's
motivating flaw (``ExecStart=/bin/true`` in a user-writable unit) is closed by
moving the real unit to root-owned ``/etc/systemd/user`` and deleting shadows here.
"""

import hashlib
import logging
import os
import subprocess
from pathlib import Path

from daemon import paths, system_assets

logger = logging.getLogger(__name__)

SERVICE_NAME = "hyprblocker.service"
# Must match WantedBy= in the canonical unit (see daemon.system_assets).
WANTED_BY_TARGET = "graphical-session.target"

_SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"
_WANTS_SYMLINK = _SYSTEMD_USER_DIR / f"{WANTED_BY_TARGET}.wants" / SERVICE_NAME

# The user-writable locations that can *shadow* the root-owned copies.
_SHADOW_UNIT = _SYSTEMD_USER_DIR / SERVICE_NAME
_SHADOW_UNIT_DROPIN = _SYSTEMD_USER_DIR / f"{SERVICE_NAME}.d"

# Root-owned system unit (installed by install-root.sh).
_SYSTEM_USER_UNIT = Path("/etc/systemd/user") / SERVICE_NAME

# User-level native-messaging manifest locations (these override system ones).
_USER_MANIFEST_PATHS = [
    Path.home() / ".mozilla/native-messaging-hosts/com.hyprblocker.host.json",
    Path.home() / ".config/google-chrome/NativeMessagingHosts/com.hyprblocker.host.json",
    Path.home() / ".config/chromium/NativeMessagingHosts/com.hyprblocker.host.json",
    Path.home() / ".config/BraveSoftware/Brave-Browser/NativeMessagingHosts/com.hyprblocker.host.json",
]


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

    logger.warning("Auto-start symlink missing (service was disabled); re-enabling")
    try:
        result = subprocess.run(
            ["systemctl", "--user", "enable", SERVICE_NAME],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            logger.info("Re-enabled hyprblocker service (disable-prevention active)")
            return True
        logger.error(f"Failed to re-enable service: {result.stderr.decode().strip()}")
        return False
    except Exception as e:
        logger.error(f"Failed to re-enable service: {e}")
        return False


# ---------------------------------------------------------------------------
# User-side shadow removal (root layout only; operates on user-owned files)
# ---------------------------------------------------------------------------

def delete_shadow_units() -> int:
    """Remove user-writable systemd units that shadow the root-owned copy.

    ``~/.config/systemd/user/`` takes precedence over ``/etc/systemd/user/``, so a
    user could drop a no-op ``hyprblocker.service`` (or a drop-in override) there to
    neuter the root-installed unit at the next reboot. The daemon owns these files,
    so it can delete them itself. No-op in the user layout (there is no root copy to
    protect). Returns the number of shadow paths removed.
    """
    if paths.layout() != "root":
        return 0

    removed = 0
    try:
        if _SHADOW_UNIT.exists() or _SHADOW_UNIT.is_symlink():
            _SHADOW_UNIT.unlink()
            logger.warning("Removed shadow unit %s", _SHADOW_UNIT)
            removed += 1
    except OSError as e:
        logger.error("Failed to remove shadow unit %s: %s", _SHADOW_UNIT, e)

    try:
        if _SHADOW_UNIT_DROPIN.is_dir():
            for f in _SHADOW_UNIT_DROPIN.iterdir():
                f.unlink()
            _SHADOW_UNIT_DROPIN.rmdir()
            logger.warning("Removed shadow drop-in dir %s", _SHADOW_UNIT_DROPIN)
            removed += 1
    except OSError as e:
        logger.error("Failed to remove shadow drop-in %s: %s", _SHADOW_UNIT_DROPIN, e)

    if removed:
        _daemon_reload_user()
    return removed


def delete_shadow_manifests() -> int:
    """Remove user-level native-messaging manifests so the root system ones win.

    A browser reads the per-user manifest dir in preference to the system dir, so a
    user could point ``~/.config/chromium/NativeMessagingHosts/com.hyprblocker.host.json``
    at a stub host that lies about the browser PID. The daemon owns those files, so
    it deletes them. No-op in user layout. Returns count removed.
    """
    if paths.layout() != "root":
        return 0
    removed = 0
    for p in _USER_MANIFEST_PATHS:
        try:
            if p.exists():
                p.unlink()
                logger.warning("Removed user-level manifest %s", p)
                removed += 1
        except OSError as e:
            logger.error("Failed to remove manifest %s: %s", p, e)
    return removed


def enforce_user_side() -> None:
    """Everything the unprivileged daemon can do to keep enforcement wired.

    Gated by the caller on ``shutdown_prevention_enabled`` like the original symlink
    check. Safe in both layouts (the shadow-removal helpers no-op under user layout).
    """
    ensure_service_enabled()
    delete_shadow_units()
    delete_shadow_manifests()


def _daemon_reload_user() -> None:
    try:
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"], capture_output=True, timeout=30
        )
    except Exception as e:  # pragma: no cover - best effort
        logger.error("systemctl --user daemon-reload failed: %s", e)


# ---------------------------------------------------------------------------
# Root-side repair (run by the enforcer; operates on root-owned /etc files)
# ---------------------------------------------------------------------------

def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def service_unit_intact() -> bool:
    """True iff the root-owned system unit is a regular file matching canonical content."""
    try:
        if _SYSTEM_USER_UNIT.is_symlink() or not _SYSTEM_USER_UNIT.is_file():
            return False
        return _sha(_SYSTEM_USER_UNIT.read_text()) == _sha(system_assets.user_unit())
    except OSError:
        return False


def ensure_service_intact() -> bool:
    """Rewrite the root-owned system unit from canonical if it was tampered/masked.

    Root privilege required — the enforcer calls this. Also unmasks and reloads
    (safe: does not restart the running service). Returns True if intact/repaired.
    """
    if service_unit_intact():
        return True
    logger.warning("System unit %s tampered or missing — restoring canonical", _SYSTEM_USER_UNIT)
    try:
        _SYSTEM_USER_UNIT.parent.mkdir(parents=True, exist_ok=True)
        _SYSTEM_USER_UNIT.write_text(system_assets.user_unit())
        subprocess.run(["systemctl", "unmask", SERVICE_NAME], capture_output=True, timeout=30)
        subprocess.run(["systemctl", "daemon-reload"], capture_output=True, timeout=30)
        return True
    except OSError as e:
        logger.error("Failed to restore system unit: %s", e)
        return False


def repair_native_manifests() -> int:
    """Rewrite any deleted/edited system-wide manifest from canonical. Root only.

    Returns the number of manifests (re)written.
    """
    written = 0
    jobs = [
        (system_assets.CHROME_MANIFEST_DIRS, system_assets.chrome_manifest()),
        (system_assets.FIREFOX_MANIFEST_DIRS, system_assets.firefox_manifest()),
    ]
    for dirs, content in jobs:
        for d in dirs:
            target = Path(d) / system_assets.MANIFEST_FILENAME
            try:
                if not target.exists() or target.read_text() != content:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content)
                    logger.warning("Repaired manifest %s", target)
                    written += 1
            except OSError as e:
                logger.error("Failed to repair manifest %s: %s", target, e)
    return written
