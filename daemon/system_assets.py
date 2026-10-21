"""Canonical system assets (systemd units, native-messaging manifests, sudoers).

Single source of truth shared between ``install-root.sh`` and the runtime repair
logic in :mod:`daemon.service_enforcer`. The installer renders assets by calling
``python -m daemon.system_assets <name>`` so there is never a second, drifting copy
of the unit content that the enforcer then fails to recognise.

Everything here is pure string rendering — no I/O, no privilege — so it is fully
unit-testable.
"""

from __future__ import annotations

import sys

# The pinned Chrome extension ID (derived from the manifest "key"). Duplicated
# historically in install.sh; centralised here. NEVER change it — see
# docs/TECHNICAL_CONCEPTS.md "Native Messaging and Extension IDs".
EXTENSION_ID = "djngojgikpdalhbiimclpdcfehcphcim"
FIREFOX_EXTENSION_ID = "hyprblocker@hyprblocker.local"

# Root-install locations.
CODE_ROOT = "/opt/hyprblocker"
VENV_PYTHON = f"{CODE_ROOT}/.venv/bin/python"
NATIVE_HOST_PATH = f"{CODE_ROOT}/native-host/host.py"
STATE_DIR = "/var/lib/hyprblocker"

SERVICE_NAME = "hyprblocker.service"
ENFORCER_SERVICE_NAME = "hyprblocker-enforcer.service"
BREAKGLASS_SERVICE_NAME = "hyprblocker-breakglass.service"


def user_unit() -> str:
    """The root-install variant of the per-user daemon unit.

    Runs the daemon from the root-owned /opt venv in isolated mode (``python -I``
    ignores PYTHONPATH and user site-packages, closing the interpreter-env
    injection hole), with an explicit environment so nothing leaks in from
    ``systemctl --user set-environment``.
    """
    return f"""[Unit]
Description=HyprBlocker Daemon
After=graphical-session.target
BindsTo=graphical-session.target
StartLimitIntervalSec=0

[Service]
Type=simple
# Strip anything the user could inject via `systemctl --user set-environment`
# (Environment= only ADDS; UnsetEnvironment= is what actually closes the
# LD_PRELOAD / PYTHONPATH / secure-dir-override injection paths). Review M2.
UnsetEnvironment=LD_PRELOAD LD_LIBRARY_PATH PYTHONPATH PYTHONHOME PYTHONSTARTUP HYPRBLOCKER_STATE_DIR HYPRBLOCKER_CONFIG_DIR HYPRBLOCKER_SECURE_DIR HYPRBLOCKER_LOG_DIR HYPRBLOCKER_CODE_ROOT
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONPATH=
Environment=HYPRBLOCKER_LAYOUT=root
WorkingDirectory={CODE_ROOT}
ExecStart={VENV_PYTHON} -I -m daemon.main
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# Make it harder to kill
KillMode=process
KillSignal=SIGTERM
SendSIGKILL=no

[Install]
WantedBy=graphical-session.target
"""


def enforcer_unit() -> str:
    """The root enforcer system unit (runs as root, Restart=always, clean env)."""
    return f"""[Unit]
Description=HyprBlocker Root Enforcer
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=root
UnsetEnvironment=LD_PRELOAD LD_LIBRARY_PATH PYTHONPATH PYTHONHOME PYTHONSTARTUP HYPRBLOCKER_STATE_DIR HYPRBLOCKER_CONFIG_DIR HYPRBLOCKER_SECURE_DIR HYPRBLOCKER_LOG_DIR HYPRBLOCKER_CODE_ROOT
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONPATH=
Environment=HYPRBLOCKER_LAYOUT=root
WorkingDirectory={CODE_ROOT}
ExecStart={VENV_PYTHON} -I -m enforcer.main
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""


def breakglass_unit() -> str:
    """The break-glass release unit — deliberately tiny and dependency-free.

    Independent of the enforcer so it still works if the enforcer is crash-looping
    (review finding R5). It runs the standalone break-glass module which watches
    for a user-dropped trigger file and releases the credential after the delay.
    """
    return f"""[Unit]
Description=HyprBlocker Break-Glass Release
After=network.target

[Service]
Type=oneshot
User=root
Environment=PYTHONPATH=
Environment=HYPRBLOCKER_LAYOUT=root
ExecStart={VENV_PYTHON} -I -m enforcer.breakglass_runner
StandardOutput=journal
StandardError=journal
"""


def breakglass_timer() -> str:
    """Timer that runs the break-glass check every 15 minutes."""
    return f"""[Unit]
Description=HyprBlocker Break-Glass Timer

[Timer]
OnBootSec=2min
OnUnitActiveSec=15min
Unit={BREAKGLASS_SERVICE_NAME}

[Install]
WantedBy=timers.target
"""


def chrome_manifest() -> str:
    return f"""{{
  "name": "com.hyprblocker.host",
  "description": "HyprBlocker Native Host",
  "path": "{NATIVE_HOST_PATH}",
  "type": "stdio",
  "allowed_origins": [
    "chrome-extension://{EXTENSION_ID}/"
  ]
}}
"""


def firefox_manifest() -> str:
    return f"""{{
  "name": "com.hyprblocker.host",
  "description": "HyprBlocker Native Host",
  "path": "{NATIVE_HOST_PATH}",
  "type": "stdio",
  "allowed_extensions": ["{FIREFOX_EXTENSION_ID}"]
}}
"""


def pacman_sudoers() -> str:
    """Tier-2 deterministic carve-out: exactly ``pacman -Syu``, nothing else.

    No ``-U`` (arbitrary package files), no package-name arguments (which could pull
    a poisoned AUR/user package) — the argv is pinned so exploiting it requires
    poisoning the Arch repos themselves. Uses the login password (normal sudo).
    """
    return "%hyprblocker ALL=(root) /usr/bin/pacman -Syu\n"


# Where system-wide native-messaging manifests live per browser family.
CHROME_MANIFEST_DIRS = [
    "/etc/opt/chrome/native-messaging-hosts",
    "/etc/chromium/native-messaging-hosts",
    "/etc/opt/brave/native-messaging-hosts",
]
FIREFOX_MANIFEST_DIRS = [
    "/usr/lib/mozilla/native-messaging-hosts",
]
MANIFEST_FILENAME = "com.hyprblocker.host.json"


_ASSETS = {
    "user-unit": user_unit,
    "enforcer-unit": enforcer_unit,
    "breakglass-unit": breakglass_unit,
    "breakglass-timer": breakglass_timer,
    "chrome-manifest": chrome_manifest,
    "firefox-manifest": firefox_manifest,
    "pacman-sudoers": pacman_sudoers,
}


def render(name: str) -> str:
    if name not in _ASSETS:
        raise KeyError(f"unknown asset {name!r}; known: {', '.join(sorted(_ASSETS))}")
    return _ASSETS[name]()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: python -m daemon.system_assets <{'|'.join(sorted(_ASSETS))}>", file=sys.stderr)
        return 2
    try:
        sys.stdout.write(render(argv[1]))
    except KeyError as e:
        print(e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
