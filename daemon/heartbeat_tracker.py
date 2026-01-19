"""Heartbeat tracking for browser extensions."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Set, Optional
import logging
import sys
import os

# Add daemon directory to Python path for absolute imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_config

logger = logging.getLogger(__name__)


@dataclass
class BrowserHeartbeat:
    """Represents a browser's heartbeat state."""
    browser: str
    last_seen: datetime
    incognito_last_seen: Optional[datetime] = None
    incognito_enabled: bool = True
    window_mismatch_count: int = 0  # Consecutive mismatches with Hyprland count


@dataclass
class ExtensionInstance:
    """Tracks a single extension instance (one per browser profile)."""
    extension_id: str
    window_count: int
    last_seen: datetime


class HeartbeatTracker:
    """Tracks browser extension heartbeats to ensure compliance."""

    # Grace period for newly-seen PIDs (safety net for native messaging race)
    NEW_BROWSER_GRACE_SECONDS = 10

    def __init__(self):
        # {pid: BrowserHeartbeat}
        self.active_browsers: Dict[int, BrowserHeartbeat] = {}
        # Track extension instances per PID: {pid: {extension_id: ExtensionInstance}}
        self.extension_instances: Dict[int, Dict[str, ExtensionInstance]] = {}
        # Grace period for adding extensions
        self._grace_period_until: Optional[datetime] = None
        # Track when PIDs are first seen from Hyprland (for per-PID grace period)
        self._first_seen_pids: Dict[int, datetime] = {}

    @property
    def heartbeat_timeout(self) -> int:
        """Get heartbeat timeout from config."""
        return get_config().monitoring.heartbeat_timeout_seconds

    def start_grace_period(self, duration_seconds: int = 30) -> datetime:
        """Start a grace period during which browser compliance isn't enforced.

        Args:
            duration_seconds: Duration of the grace period in seconds

        Returns:
            datetime: When the grace period will end
        """
        self._grace_period_until = datetime.now() + timedelta(seconds=duration_seconds)
        logger.info(f"Grace period started, expires at {self._grace_period_until}")
        return self._grace_period_until

    def is_grace_period_active(self) -> bool:
        """Check if currently in a grace period.

        Returns:
            bool: True if grace period is active
        """
        if self._grace_period_until is None:
            return False
        return datetime.now() < self._grace_period_until

    def _is_new_browser(self, pid: int) -> bool:
        """Check if PID was first seen recently (within per-PID grace period).

        Args:
            pid: The browser process ID

        Returns:
            True if this is a new PID or was first seen within NEW_BROWSER_GRACE_SECONDS
        """
        if pid not in self._first_seen_pids:
            return True
        age = (datetime.now() - self._first_seen_pids[pid]).total_seconds()
        return age < self.NEW_BROWSER_GRACE_SECONDS

    def _register_first_seen(self, pid: int) -> None:
        """Track when we first saw a PID from Hyprland.

        Args:
            pid: The browser process ID
        """
        if pid not in self._first_seen_pids:
            self._first_seen_pids[pid] = datetime.now()
            logger.info(f"First time seeing browser PID {pid}, starting {self.NEW_BROWSER_GRACE_SECONDS}s grace period")

    def get_grace_period_remaining(self) -> Optional[int]:
        """Get remaining seconds in the grace period.

        Returns:
            int or None: Seconds remaining, or None if no active grace period
        """
        if not self.is_grace_period_active():
            return None
        remaining = (self._grace_period_until - datetime.now()).total_seconds()
        return max(0, int(remaining))

    def register_heartbeat(
        self,
        pid: int,
        browser: str,
        incognito: bool,
        incognito_enabled: bool = True,
        extension_id: str = "",
        window_count: int = 0
    ) -> None:
        """Register a heartbeat from a browser extension.

        Args:
            pid: The browser process ID
            browser: The browser name (e.g., 'firefox', 'chrome')
            incognito: Whether this is from an incognito/private window
            incognito_enabled: Whether extension has incognito permission
            extension_id: Unique ID for this extension instance (per browser profile)
            window_count: Number of windows visible to this extension
        """
        now = datetime.now()

        # Track browser-level heartbeat
        if pid in self.active_browsers:
            self.active_browsers[pid].last_seen = now
            self.active_browsers[pid].incognito_enabled = incognito_enabled
            if incognito:
                self.active_browsers[pid].incognito_last_seen = now
        else:
            self.active_browsers[pid] = BrowserHeartbeat(
                browser=browser,
                last_seen=now,
                incognito_last_seen=now if incognito else None,
                incognito_enabled=incognito_enabled
            )
            logger.info(f"Registered new browser: {browser} (PID: {pid})")

        # Track extension instance (per-profile window count)
        if extension_id:
            if pid not in self.extension_instances:
                self.extension_instances[pid] = {}
            self.extension_instances[pid][extension_id] = ExtensionInstance(
                extension_id=extension_id,
                window_count=window_count,
                last_seen=now
            )
            logger.debug(
                f"Updated extension instance: {extension_id[:8]}... "
                f"(PID: {pid}, windows: {window_count})"
            )

    def get_compliant_browsers(self) -> Set[int]:
        """Get PIDs of browsers with recent heartbeats.

        Returns:
            Set of PIDs for browsers that have sent heartbeats within the timeout period.
        """
        now = datetime.now()
        timeout = timedelta(seconds=self.heartbeat_timeout)
        compliant = set()

        for pid, heartbeat in self.active_browsers.items():
            if now - heartbeat.last_seen <= timeout:
                compliant.add(pid)

        return compliant

    def get_non_compliant_browsers(self, all_browser_pids: Set[int]) -> Set[int]:
        """Find browsers without recent heartbeats.

        Args:
            all_browser_pids: Set of all currently running browser PIDs

        Returns:
            Set of PIDs for browsers that haven't sent heartbeats within the timeout.
        """
        # During global grace period, all browsers are considered compliant
        if self.is_grace_period_active():
            logger.debug("Grace period active - all browsers considered compliant")
            return set()

        compliant = self.get_compliant_browsers()
        non_compliant = all_browser_pids - compliant

        # Filter out PIDs that are still in their new-browser grace period
        truly_non_compliant = set()
        for pid in non_compliant:
            # Register first-seen time for new PIDs
            self._register_first_seen(pid)

            if self._is_new_browser(pid):
                logger.debug(f"PID {pid} is new (within {self.NEW_BROWSER_GRACE_SECONDS}s grace period), skipping")
            else:
                truly_non_compliant.add(pid)

        return truly_non_compliant

    def get_total_extension_window_count(self, pid: int) -> Optional[int]:
        """Get the total window count from all extension instances for a PID.

        Sums window counts from all extension instances (profiles) for this browser.

        Args:
            pid: The browser process ID

        Returns:
            Total windows across all extensions, or None if no extensions tracked
        """
        if pid not in self.extension_instances:
            return None

        now = datetime.now()
        timeout = timedelta(seconds=self.heartbeat_timeout)
        total = 0

        for instance in self.extension_instances[pid].values():
            if now - instance.last_seen <= timeout:
                total += instance.window_count

        return total if total > 0 else None

    def increment_window_mismatch(self, pid: int) -> int:
        """Increment the window mismatch counter for a browser.

        Args:
            pid: The browser process ID

        Returns:
            The new mismatch count, or 0 if browser not tracked
        """
        if pid not in self.active_browsers:
            return 0
        self.active_browsers[pid].window_mismatch_count += 1
        return self.active_browsers[pid].window_mismatch_count

    def reset_window_mismatch(self, pid: int) -> None:
        """Reset the window mismatch counter for a browser.

        Args:
            pid: The browser process ID
        """
        if pid in self.active_browsers:
            self.active_browsers[pid].window_mismatch_count = 0

    def get_browsers_missing_incognito_heartbeat(self) -> Set[int]:
        """Find browsers that have incognito windows but no recent incognito heartbeat.

        Returns:
            Set of PIDs for browsers missing incognito heartbeats.
        """
        now = datetime.now()
        timeout = timedelta(seconds=self.heartbeat_timeout)
        missing = set()

        for pid, heartbeat in self.active_browsers.items():
            # If we've ever seen an incognito heartbeat but it's now stale
            if heartbeat.incognito_last_seen is not None:
                if now - heartbeat.incognito_last_seen > timeout:
                    # Only flag if the main heartbeat is still recent (browser still running)
                    if now - heartbeat.last_seen <= timeout:
                        missing.add(pid)

        return missing

    def cleanup_old_heartbeats(self) -> None:
        """Remove heartbeats and extension instances older than the timeout period."""
        now = datetime.now()
        timeout = timedelta(seconds=self.heartbeat_timeout * 2)  # Extra buffer for cleanup

        # Clean up stale browsers
        stale_pids = [
            pid for pid, heartbeat in self.active_browsers.items()
            if now - heartbeat.last_seen > timeout
        ]

        for pid in stale_pids:
            browser = self.active_browsers[pid].browser
            del self.active_browsers[pid]
            # Also remove extension instances for this PID
            if pid in self.extension_instances:
                del self.extension_instances[pid]
            logger.info(f"Removed stale heartbeat for {browser} (PID: {pid})")

        # Clean up stale extension instances (even if browser is still active)
        for pid in list(self.extension_instances.keys()):
            stale_extensions = [
                ext_id for ext_id, instance in self.extension_instances[pid].items()
                if now - instance.last_seen > timeout
            ]
            for ext_id in stale_extensions:
                del self.extension_instances[pid][ext_id]
                logger.debug(f"Removed stale extension instance: {ext_id[:8]}... (PID: {pid})")
            # Remove empty dicts
            if not self.extension_instances[pid]:
                del self.extension_instances[pid]

        # Clean up old first-seen entries (keep for 2 minutes max)
        first_seen_timeout = timedelta(seconds=120)
        stale_first_seen = [
            pid for pid, seen in self._first_seen_pids.items()
            if now - seen > first_seen_timeout
        ]
        for pid in stale_first_seen:
            del self._first_seen_pids[pid]
            logger.debug(f"Removed stale first-seen entry for PID {pid}")

    def get_browser_status(self, pid: int) -> Optional[Dict]:
        """Get the status of a specific browser.

        Args:
            pid: The browser process ID

        Returns:
            Dictionary with browser status or None if not tracked.
        """
        if pid not in self.active_browsers:
            return None

        heartbeat = self.active_browsers[pid]
        now = datetime.now()
        timeout = timedelta(seconds=self.heartbeat_timeout)

        incognito_active = heartbeat.incognito_last_seen is not None and \
                           now - heartbeat.incognito_last_seen <= timeout

        # Browser is compliant if BOTH:
        # 1. Heartbeat is recent (extension running)
        # 2. Extension has incognito permission enabled
        is_compliant = (now - heartbeat.last_seen <= timeout) and heartbeat.incognito_enabled

        return {
            "pid": pid,
            "browser": heartbeat.browser,
            "compliant": is_compliant,
            "last_heartbeat": heartbeat.last_seen.isoformat(),
            "incognito_active": incognito_active,
            "incognito_enabled": heartbeat.incognito_enabled
        }

    def get_all_browser_statuses(self) -> list:
        """Get status of all tracked browsers.

        Returns:
            List of browser status dictionaries.
        """
        return [
            self.get_browser_status(pid)
            for pid in self.active_browsers
            if self.get_browser_status(pid) is not None
        ]


# Global heartbeat tracker instance
_tracker: Optional[HeartbeatTracker] = None


def get_heartbeat_tracker() -> HeartbeatTracker:
    """Get the global heartbeat tracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = HeartbeatTracker()
    return _tracker
