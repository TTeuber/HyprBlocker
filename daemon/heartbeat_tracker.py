"""Heartbeat tracking for browser extensions."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Set, Optional
import logging

from config import get_config

logger = logging.getLogger(__name__)


@dataclass
class BrowserHeartbeat:
    """Represents a browser's heartbeat state."""
    browser: str
    last_seen: datetime
    incognito_last_seen: Optional[datetime] = None


class HeartbeatTracker:
    """Tracks browser extension heartbeats to ensure compliance."""

    def __init__(self):
        # {pid: BrowserHeartbeat}
        self.active_browsers: Dict[int, BrowserHeartbeat] = {}

    @property
    def heartbeat_timeout(self) -> int:
        """Get heartbeat timeout from config."""
        return get_config().monitoring.heartbeat_timeout_seconds

    def register_heartbeat(self, pid: int, browser: str, incognito: bool) -> None:
        """Register a heartbeat from a browser extension.

        Args:
            pid: The browser process ID
            browser: The browser name (e.g., 'firefox', 'chrome')
            incognito: Whether this is from an incognito/private window
        """
        now = datetime.now()

        if pid in self.active_browsers:
            # Update existing heartbeat
            self.active_browsers[pid].last_seen = now
            if incognito:
                self.active_browsers[pid].incognito_last_seen = now
            logger.debug(f"Updated heartbeat for {browser} (PID: {pid}, incognito: {incognito})")
        else:
            # New browser registration
            self.active_browsers[pid] = BrowserHeartbeat(
                browser=browser,
                last_seen=now,
                incognito_last_seen=now if incognito else None
            )
            logger.info(f"Registered new browser: {browser} (PID: {pid})")

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
        compliant = self.get_compliant_browsers()
        return all_browser_pids - compliant

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
        """Remove heartbeats older than the timeout period."""
        now = datetime.now()
        timeout = timedelta(seconds=self.heartbeat_timeout * 2)  # Extra buffer for cleanup

        stale_pids = [
            pid for pid, heartbeat in self.active_browsers.items()
            if now - heartbeat.last_seen > timeout
        ]

        for pid in stale_pids:
            browser = self.active_browsers[pid].browser
            del self.active_browsers[pid]
            logger.info(f"Removed stale heartbeat for {browser} (PID: {pid})")

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

        return {
            "pid": pid,
            "browser": heartbeat.browser,
            "compliant": now - heartbeat.last_seen <= timeout,
            "last_heartbeat": heartbeat.last_seen.isoformat(),
            "incognito_active": heartbeat.incognito_last_seen is not None and \
                                now - heartbeat.incognito_last_seen <= timeout
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
