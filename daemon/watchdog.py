"""Watchdog system for daemon resilience.

Spawns independent processes that monitor the daemon and each other,
restarting any that are killed. Uses obfuscated process names for resilience.
"""

import ctypes
import json
import logging
import os
import random
import signal
import string
import subprocess
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# Process name pools for obfuscation
SYSTEM_NAMES = [
    "kworker", "ksoftirqd", "migration", "watchdog",
    "systemd-helper", "dbus-daemon", "gdbus", "gvfsd"
]
COMMON_NAMES = [
    "update-notifier", "gsd-color", "gsd-power", "gsd-media-keys",
    "at-spi-bus", "ibus-daemon", "pulseaudio", "pipewire"
]

# Paths
CONFIG_DIR = Path.home() / ".config" / "website-blocker"
WATCHDOG_STATE_FILE = CONFIG_DIR / "watchdog_state.json"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Timing constants
DAEMON_CHECK_INTERVAL = 5  # seconds
SIBLING_CHECK_INTERVAL = 10  # seconds
HEARTBEAT_INTERVAL = 30  # seconds
HEARTBEAT_TIMEOUT = 60  # seconds
DAEMON_FAIL_THRESHOLD = 3  # consecutive failures before restart
SERVICE_ENABLE_CHECK_INTERVAL = 30  # seconds — how often to re-check the enable symlink


def generate_obfuscated_name() -> str:
    """Generate a random obfuscated process name."""
    name_type = random.choice(["system", "common", "random"])

    if name_type == "system":
        base = random.choice(SYSTEM_NAMES)
        suffix = random.randint(0, 99)
        return f"{base}/{suffix}"
    elif name_type == "common":
        base = random.choice(COMMON_NAMES)
        return base
    else:
        # Random alphanumeric name
        return ''.join(random.choices(string.ascii_lowercase, k=8))


def set_process_name(name: str) -> bool:
    """Set the process name visible in ps/top (Linux only).

    Uses prctl PR_SET_NAME to change the process name.
    Name is truncated to 15 characters (Linux limit).
    """
    try:
        libc = ctypes.CDLL("libc.so.6")
        PR_SET_NAME = 15
        # Name must be <= 15 bytes for prctl
        truncated_name = name.encode()[:15]
        result = libc.prctl(PR_SET_NAME, truncated_name, 0, 0, 0)
        return result == 0
    except Exception as e:
        logger.warning(f"Failed to set process name: {e}")
        return False


@dataclass
class WatchdogEntry:
    """Represents a watchdog process in the state file."""
    pid: int
    name: str
    started: str  # ISO format datetime
    last_heartbeat: str  # ISO format datetime


@dataclass
class WatchdogState:
    """Persistent state shared between watchdog processes."""
    enabled: bool = True
    watchdog_count: int = 3
    watchdogs: List[Dict[str, Any]] = None
    daemon_pid: Optional[int] = None
    shutdown_requested: bool = False

    def __post_init__(self):
        if self.watchdogs is None:
            self.watchdogs = []

    @classmethod
    def load(cls) -> "WatchdogState":
        """Load state from file."""
        if not WATCHDOG_STATE_FILE.exists():
            return cls()

        try:
            with open(WATCHDOG_STATE_FILE, 'r') as f:
                data = json.load(f)
            return cls(**data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Failed to load watchdog state: {e}")
            return cls()

    def save(self) -> None:
        """Save state to file."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(WATCHDOG_STATE_FILE, 'w') as f:
            json.dump(asdict(self), f, indent=2)


def read_config_lock_until() -> Optional[datetime]:
    """Read settings_lock_until from config file."""
    try:
        if not CONFIG_FILE.exists():
            return None

        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)

        lock_until_str = data.get('security', {}).get('settings_lock_until')
        if not lock_until_str:
            return None

        return datetime.fromisoformat(lock_until_str)
    except Exception as e:
        logger.error(f"Failed to read config lock_until: {e}")
        return None


def is_settings_locked_ntp() -> bool:
    """Check if settings are locked, using NTP time verification.

    Returns True if locked (fail-safe: returns True on NTP failure during lock).
    """
    lock_until = read_config_lock_until()
    if lock_until is None:
        return False

    # Try NTP verification
    try:
        import ntplib
        ntp_client = ntplib.NTPClient()
        ntp_servers = ["pool.ntp.org", "time.google.com", "time.cloudflare.com"]

        for server in ntp_servers:
            try:
                response = ntp_client.request(server, timeout=5)
                ntp_time = datetime.fromtimestamp(response.tx_time, tz=timezone.utc)

                # Compare with lock_until (ensure timezone awareness)
                if lock_until.tzinfo is None:
                    lock_until = lock_until.replace(tzinfo=timezone.utc)

                return ntp_time < lock_until
            except Exception:
                continue

        # All NTP servers failed - fail-safe: assume locked
        logger.warning("NTP verification failed, assuming settings locked (fail-safe)")
        return True

    except ImportError:
        # ntplib not available, use system time
        now = datetime.now(timezone.utc)
        if lock_until.tzinfo is None:
            lock_until = lock_until.replace(tzinfo=timezone.utc)
        return now < lock_until


def check_daemon_health(port: int = 8765) -> bool:
    """Check if daemon is responding to HTTP requests."""
    try:
        url = f"http://127.0.0.1:{port}/api/status"
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status == 200
    except Exception:
        return False


def is_process_alive(pid: int) -> bool:
    """Check if a process with given PID exists."""
    try:
        os.kill(pid, 0)  # Signal 0 doesn't kill, just checks existence
        return True
    except (OSError, ProcessLookupError):
        return False


def restart_daemon() -> bool:
    """Restart the daemon via systemctl."""
    try:
        result = subprocess.run(
            ["systemctl", "--user", "restart", "website-blocker"],
            capture_output=True,
            timeout=30
        )
        if result.returncode == 0:
            logger.info("Daemon restarted successfully")
            return True
        else:
            logger.error(f"Failed to restart daemon: {result.stderr.decode()}")
            return False
    except Exception as e:
        logger.error(f"Failed to restart daemon: {e}")
        return False


class WatchdogManager:
    """Manages spawning and coordination of watchdog processes."""

    def __init__(self, watchdog_count: int = 3, daemon_port: int = 8765):
        self.watchdog_count = max(2, min(5, watchdog_count))  # Clamp to 2-5
        self.daemon_port = daemon_port
        self._spawned_pids: List[int] = []

    def spawn_watchdogs(self) -> List[int]:
        """Fork watchdog processes with obfuscated names.

        Returns list of spawned PIDs.
        """
        state = WatchdogState.load()
        state.enabled = True
        state.watchdog_count = self.watchdog_count
        state.daemon_pid = os.getpid()
        state.shutdown_requested = False
        state.watchdogs = []

        pids = []
        runner_path = Path(__file__).parent / "watchdog_runner.py"

        for i in range(self.watchdog_count):
            name = generate_obfuscated_name()

            try:
                # Fork a new process
                pid = os.fork()

                if pid == 0:
                    # Child process - become the watchdog
                    # Detach from parent
                    os.setsid()

                    # Close file descriptors
                    try:
                        os.close(0)  # stdin
                        os.close(1)  # stdout
                        os.close(2)  # stderr
                    except OSError:
                        pass

                    # Redirect to /dev/null
                    devnull = os.open('/dev/null', os.O_RDWR)
                    os.dup2(devnull, 0)
                    os.dup2(devnull, 1)
                    os.dup2(devnull, 2)

                    # Execute the watchdog runner
                    os.execv(sys.executable, [
                        sys.executable,
                        str(runner_path),
                        "--name", name,
                        "--port", str(self.daemon_port)
                    ])
                else:
                    # Parent process
                    pids.append(pid)
                    now = datetime.now(timezone.utc).isoformat()
                    state.watchdogs.append({
                        "pid": pid,
                        "name": name,
                        "started": now,
                        "last_heartbeat": now
                    })
                    logger.info(f"Spawned watchdog {i+1}/{self.watchdog_count}: PID {pid}, name '{name}'")

            except OSError as e:
                logger.error(f"Failed to fork watchdog: {e}")

        state.save()
        self._spawned_pids = pids
        return pids

    def signal_shutdown(self) -> None:
        """Signal all watchdogs to exit cleanly."""
        state = WatchdogState.load()

        # Check if settings are locked - if so, don't request shutdown
        if is_settings_locked_ntp():
            logger.info("Settings are locked, not signaling watchdog shutdown")
            return

        state.shutdown_requested = True
        state.save()
        logger.info("Signaled watchdogs to shutdown")

    def get_active_watchdogs(self) -> List[Dict[str, Any]]:
        """Get list of active watchdog processes with their info."""
        state = WatchdogState.load()
        active = []

        for wd in state.watchdogs:
            if is_process_alive(wd["pid"]):
                # Calculate uptime
                started = datetime.fromisoformat(wd["started"])
                uptime = (datetime.now(timezone.utc) - started).total_seconds()
                active.append({
                    "pid": wd["pid"],
                    "name": wd["name"],
                    "uptime_seconds": int(uptime)
                })

        return active


class Watchdog:
    """Individual watchdog process logic.

    This class is used by watchdog_runner.py, not by the daemon directly.
    """

    def __init__(self, name: str, daemon_port: int = 8765):
        self.name = name
        self.daemon_port = daemon_port
        self.daemon_fail_count = 0
        self._running = True

        # Set up signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, signum, frame):
        """Handle termination signals."""
        # Check if settings are locked
        if is_settings_locked_ntp():
            logger.info(f"Ignoring signal {signum} - settings are locked")
            return

        logger.info(f"Received signal {signum}, shutting down")
        self._running = False

    def run(self) -> None:
        """Main watchdog loop."""
        # Set obfuscated process name
        set_process_name(self.name)

        logger.info(f"Watchdog started: name={self.name}, pid={os.getpid()}")

        last_daemon_check = 0
        last_sibling_check = 0
        last_heartbeat = 0
        last_enable_check = 0

        while self._running:
            now = time.time()

            # Check for shutdown request (unless settings locked)
            state = WatchdogState.load()
            if state.shutdown_requested and not is_settings_locked_ntp():
                logger.info("Shutdown requested, exiting")
                break

            # Check daemon health
            if now - last_daemon_check >= DAEMON_CHECK_INTERVAL:
                last_daemon_check = now

                if check_daemon_health(self.daemon_port):
                    self.daemon_fail_count = 0
                else:
                    self.daemon_fail_count += 1
                    logger.warning(f"Daemon health check failed ({self.daemon_fail_count}/{DAEMON_FAIL_THRESHOLD})")

                    if self.daemon_fail_count >= DAEMON_FAIL_THRESHOLD:
                        logger.error("Daemon unresponsive, restarting...")
                        if restart_daemon():
                            self.daemon_fail_count = 0
                            # Wait for daemon to start
                            time.sleep(5)

            # Check sibling watchdogs
            if now - last_sibling_check >= SIBLING_CHECK_INTERVAL:
                last_sibling_check = now
                self._check_and_respawn_siblings()

            # Update heartbeat
            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                last_heartbeat = now
                self._update_heartbeat()

            # Prevent `systemctl --user disable` from sticking.
            # Watchdogs only exist when shutdown prevention is on, so no need
            # to re-read that flag here. Skip if a legitimate shutdown is underway.
            if now - last_enable_check >= SERVICE_ENABLE_CHECK_INTERVAL:
                last_enable_check = now
                if not state.shutdown_requested:
                    from service_enforcer import ensure_service_enabled
                    ensure_service_enabled()

            time.sleep(1)

        logger.info("Watchdog exiting")

    def _check_and_respawn_siblings(self) -> None:
        """Check sibling watchdogs and respawn any that are dead."""
        state = WatchdogState.load()
        now = datetime.now(timezone.utc)
        my_pid = os.getpid()

        # Clean up stale entries and check for missing siblings
        active_watchdogs = []
        missing_count = 0

        for wd in state.watchdogs:
            if wd["pid"] == my_pid:
                active_watchdogs.append(wd)
                continue

            if is_process_alive(wd["pid"]):
                # Check heartbeat timeout
                last_hb = datetime.fromisoformat(wd["last_heartbeat"])
                if (now - last_hb).total_seconds() > HEARTBEAT_TIMEOUT:
                    logger.warning(f"Sibling {wd['pid']} heartbeat stale, considering dead")
                    missing_count += 1
                else:
                    active_watchdogs.append(wd)
            else:
                logger.warning(f"Sibling {wd['pid']} is dead")
                missing_count += 1

        # Respawn missing siblings
        if missing_count > 0:
            logger.info(f"Need to respawn {missing_count} sibling(s)")

            runner_path = Path(__file__).parent / "watchdog_runner.py"

            for _ in range(missing_count):
                name = generate_obfuscated_name()

                try:
                    pid = os.fork()

                    if pid == 0:
                        # Child - become new watchdog
                        os.setsid()

                        try:
                            os.close(0)
                            os.close(1)
                            os.close(2)
                        except OSError:
                            pass

                        devnull = os.open('/dev/null', os.O_RDWR)
                        os.dup2(devnull, 0)
                        os.dup2(devnull, 1)
                        os.dup2(devnull, 2)

                        os.execv(sys.executable, [
                            sys.executable,
                            str(runner_path),
                            "--name", name,
                            "--port", str(self.daemon_port)
                        ])
                    else:
                        now_iso = now.isoformat()
                        active_watchdogs.append({
                            "pid": pid,
                            "name": name,
                            "started": now_iso,
                            "last_heartbeat": now_iso
                        })
                        logger.info(f"Respawned sibling: PID {pid}, name '{name}'")

                except OSError as e:
                    logger.error(f"Failed to respawn sibling: {e}")

        # Update state
        state.watchdogs = active_watchdogs
        state.save()

    def _update_heartbeat(self) -> None:
        """Update this watchdog's heartbeat in the state file."""
        state = WatchdogState.load()
        my_pid = os.getpid()
        now = datetime.now(timezone.utc).isoformat()

        for wd in state.watchdogs:
            if wd["pid"] == my_pid:
                wd["last_heartbeat"] = now
                break

        state.save()
