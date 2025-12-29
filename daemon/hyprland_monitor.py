"""Hyprland window monitoring and management."""

import asyncio
import json
import logging
import subprocess
import sys
import os
from typing import Dict, List, Optional, Set

# Add daemon directory to Python path for absolute imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_config
from heartbeat_tracker import get_heartbeat_tracker
from scheduler import get_scheduler
from blocker import get_app_blocker
from database import BlockEvent

logger = logging.getLogger(__name__)


class HyprlandMonitor:
    """Monitors Hyprland windows and enforces application blocking."""

    def __init__(self, session_factory):
        """Initialize the Hyprland monitor.

        Args:
            session_factory: Async session factory for logging events
        """
        self._session_factory = session_factory

    @property
    def browser_classes(self) -> List[str]:
        """Get the list of browser class names from config."""
        return get_config().browsers

    async def get_all_windows(self) -> List[Dict]:
        """Get all windows from Hyprland.

        Returns:
            List of window dictionaries from hyprctl
        """
        try:
            result = await asyncio.create_subprocess_exec(
                "hyprctl", "clients", "-j",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode != 0:
                logger.error(f"hyprctl failed: {stderr.decode()}")
                return []

            windows = json.loads(stdout.decode())
            return windows

        except FileNotFoundError:
            logger.error("hyprctl not found - Hyprland may not be running")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse hyprctl output: {e}")
            return []
        except Exception as e:
            logger.error(f"Failed to get windows: {e}")
            return []

    def _is_browser_window(self, window: Dict) -> bool:
        """Check if a window is a browser.

        Args:
            window: Window dictionary from hyprctl

        Returns:
            bool: True if this is a browser window
        """
        window_class = window.get("class", "").lower()
        return any(browser in window_class for browser in self.browser_classes)

    def _matches_app_rule(self, window: Dict, target: str) -> bool:
        """Check if a window matches an application blocking rule.

        Args:
            window: Window dictionary from hyprctl
            target: Target class name pattern

        Returns:
            bool: True if the window matches the rule
        """
        window_class = window.get("class", "").lower()
        target_lower = target.lower()

        # Exact match
        if window_class == target_lower:
            return True

        # Partial match (for patterns like 'discord' matching 'discord-canary')
        if target_lower in window_class:
            return True

        return False

    def count_browser_windows_by_pid(self, windows: List[Dict], pid: int) -> int:
        """Count browser windows for a specific PID.

        Args:
            windows: List of window dictionaries from hyprctl
            pid: Process ID to count windows for

        Returns:
            Number of browser windows with this PID
        """
        return sum(1 for w in windows
                   if w.get("pid") == pid and self._is_browser_window(w))

    def get_browsers_with_unmonitored_windows(
        self,
        windows: List[Dict],
        browser_windows: Dict[int, Dict]
    ) -> Set[int]:
        """Find browsers that have more windows than the extension can see.

        This detects guest profiles, other profiles without the extension, etc.

        Args:
            windows: All windows from hyprctl
            browser_windows: Dict mapping PID to a representative browser window

        Returns:
            Set of PIDs for browsers with unmonitored windows
        """
        tracker = get_heartbeat_tracker()
        unmonitored = set()

        # During grace period, skip this check
        if tracker.is_grace_period_active():
            return set()

        for pid in browser_windows.keys():
            # Get TOTAL window count from ALL extension instances for this PID
            extension_count = tracker.get_total_extension_window_count(pid)

            # If no extension instances for this PID, skip
            if extension_count is None:
                logger.debug(f"PID {pid}: No extension instances tracked, skipping check")
                continue

            # Count windows Hyprland sees for this PID
            hyprland_count = self.count_browser_windows_by_pid(windows, pid)

            logger.debug(
                f"PID {pid}: Extension sees {extension_count} windows, "
                f"Hyprland sees {hyprland_count} windows"
            )

            # If Hyprland sees more windows than extension, there are unmonitored windows
            if hyprland_count > extension_count:
                # Increment mismatch counter
                mismatch_count = tracker.increment_window_mismatch(pid)

                # Require 2+ consecutive mismatches to avoid timing issues
                # (e.g., window opened between heartbeats)
                if mismatch_count >= 2:
                    logger.warning(
                        f"Browser PID {pid} has unmonitored windows! "
                        f"Extension sees {extension_count}, Hyprland sees {hyprland_count} "
                        f"(mismatch count: {mismatch_count})"
                    )
                    unmonitored.add(pid)
                else:
                    logger.debug(
                        f"PID {pid}: Window count mismatch ({extension_count} vs {hyprland_count}), "
                        f"waiting for confirmation (count: {mismatch_count}/2)"
                    )
            else:
                # Counts match, reset mismatch counter
                tracker.reset_window_mismatch(pid)

        return unmonitored

    async def close_window(self, window: Dict, reason: str = "blocked") -> bool:
        """Close a window by its address.

        Args:
            window: Window dictionary from hyprctl
            reason: Reason for closing (for logging)

        Returns:
            bool: True if successfully closed
        """
        address = window.get("address")
        if not address:
            return False

        try:
            result = await asyncio.create_subprocess_exec(
                "hyprctl", "dispatch", "closewindow", f"address:{address}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                logger.info(
                    f"Closed window: {window.get('class')} "
                    f"(PID: {window.get('pid')}, reason: {reason})"
                )
                return True
            else:
                logger.error(f"Failed to close window: {stderr.decode()}")
                return False

        except Exception as e:
            logger.error(f"Error closing window: {e}")
            return False

    async def log_block_event(self, target: str, event_type: str, rule_id: Optional[int] = None) -> None:
        """Log a blocking event to the database.

        Args:
            target: What was blocked
            event_type: Type of event
            rule_id: Optional associated rule ID
        """
        try:
            async with self._session_factory() as session:
                event = BlockEvent(
                    rule_id=rule_id,
                    blocked_target=target,
                    event_type=event_type
                )
                session.add(event)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to log block event: {e}")

    async def check_and_close_blocked_apps(self) -> int:
        """Check for and close blocked applications.

        Returns:
            Number of windows closed
        """
        app_blocker = get_app_blocker()
        if app_blocker is None:
            return 0

        windows = await self.get_all_windows()
        closed_count = 0

        for window in windows:
            window_class = window.get("class", "")
            if window_class and await app_blocker.is_app_blocked(window_class):
                if await self.close_window(window, f"blocked app: {window_class}"):
                    await self.log_block_event(
                        window_class,
                        "app_closed",
                        None  # No specific rule ID anymore
                    )
                    closed_count += 1

        return closed_count

    async def check_and_close_non_compliant_browsers(self) -> int:
        """Check for and close browsers without extension heartbeats or with unmonitored windows.

        Returns:
            Number of browsers closed
        """
        # Skip enforcement if browser enforcement is disabled
        if not get_config().security.browser_enforcement_enabled:
            logger.debug("Browser enforcement disabled - skipping")
            return 0

        tracker = get_heartbeat_tracker()
        windows = await self.get_all_windows()

        # Find all browser windows
        browser_windows: Dict[int, Dict] = {}
        for window in windows:
            if self._is_browser_window(window):
                pid = window.get("pid")
                if pid:
                    browser_windows[pid] = window

        if not browser_windows:
            return 0

        # Get non-compliant browsers (no heartbeat)
        all_browser_pids = set(browser_windows.keys())
        non_compliant = tracker.get_non_compliant_browsers(all_browser_pids)

        # Get browsers with unmonitored windows (guest profiles, etc.)
        unmonitored = self.get_browsers_with_unmonitored_windows(windows, browser_windows)

        # Combine both sets
        browsers_to_close = non_compliant | unmonitored

        closed_count = 0
        for pid in browsers_to_close:
            window = browser_windows.get(pid)
            if window:
                if pid in non_compliant:
                    reason = "no extension heartbeat"
                else:
                    reason = "unmonitored windows detected (guest profile?)"

                logger.warning(
                    f"Browser {window.get('class')} (PID: {pid}) - {reason}"
                )
                if await self.close_window(window, reason):
                    await self.log_block_event(
                        f"Browser: {window.get('class')} (PID: {pid})",
                        "browser_killed"
                    )
                    closed_count += 1

        return closed_count

    async def run_check(self) -> Dict:
        """Run a complete monitoring check.

        Returns:
            Dict with check results
        """
        apps_closed = await self.check_and_close_blocked_apps()
        browsers_closed = await self.check_and_close_non_compliant_browsers()

        # Cleanup old heartbeats
        get_heartbeat_tracker().cleanup_old_heartbeats()

        return {
            "apps_closed": apps_closed,
            "browsers_closed": browsers_closed
        }


# Global monitor instance
_monitor: Optional[HyprlandMonitor] = None


def init_hyprland_monitor(session_factory) -> HyprlandMonitor:
    """Initialize and get the global Hyprland monitor instance."""
    global _monitor
    _monitor = HyprlandMonitor(session_factory)
    return _monitor


def get_hyprland_monitor() -> Optional[HyprlandMonitor]:
    """Get the global Hyprland monitor instance."""
    return _monitor
