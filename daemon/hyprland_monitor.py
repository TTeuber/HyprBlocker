"""Hyprland window monitoring and management."""

import asyncio
import json
import logging
import subprocess
from typing import Dict, List, Optional, Set

from config import get_config
from heartbeat_tracker import get_heartbeat_tracker
from scheduler import get_scheduler
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
        scheduler = get_scheduler()
        if scheduler is None:
            return 0

        active_app_rules = await scheduler.get_active_app_rules()
        if not active_app_rules:
            return 0

        windows = await self.get_all_windows()
        closed_count = 0

        for window in windows:
            for rule in active_app_rules:
                if self._matches_app_rule(window, rule.target):
                    if await self.close_window(window, f"blocked by rule {rule.id}"):
                        await self.log_block_event(
                            window.get("class", "unknown"),
                            "app_closed",
                            rule.id
                        )
                        closed_count += 1
                    break

        return closed_count

    async def check_and_close_non_compliant_browsers(self) -> int:
        """Check for and close browsers without extension heartbeats.

        Returns:
            Number of browsers closed
        """
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

        # Get non-compliant browsers
        all_browser_pids = set(browser_windows.keys())
        non_compliant = tracker.get_non_compliant_browsers(all_browser_pids)

        closed_count = 0
        for pid in non_compliant:
            window = browser_windows.get(pid)
            if window:
                logger.warning(
                    f"Browser {window.get('class')} (PID: {pid}) has no extension heartbeat"
                )
                if await self.close_window(window, "no extension heartbeat"):
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
