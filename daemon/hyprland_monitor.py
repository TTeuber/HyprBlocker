"""Wayland compositor window monitoring and management."""

import asyncio
import json
import logging
import os

from daemon.blocker import get_app_blocker
from daemon.config import get_config
from daemon.database import BlockEvent
from daemon.heartbeat_tracker import get_heartbeat_tracker

logger = logging.getLogger(__name__)


class CompositorMonitor:
    """Monitor windows through Hyprland or Niri IPC."""

    def __init__(self, session_factory):
        """Initialize the compositor monitor.

        Args:
            session_factory: Async session factory for logging events
        """
        self._session_factory = session_factory

    @property
    def browser_classes(self) -> list[str]:
        """Get the list of browser class names from config."""
        return get_config().browsers

    async def _run_ipc(self, compositor: str) -> list[dict] | None:
        """Run a compositor query and return its raw window list."""
        command = (
            ["niri", "msg", "-j", "windows"]
            if compositor == "niri"
            else ["hyprctl", "clients", "-j"]
        )
        try:
            result = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await result.communicate()
        except FileNotFoundError:
            return None
        except OSError as e:
            logger.error("%s IPC failed: %s", compositor, e)
            return None

        if result.returncode != 0:
            logger.debug("%s IPC unavailable: %s", compositor, stderr.decode().strip())
            return None
        try:
            windows = json.loads(stdout.decode())
        except json.JSONDecodeError as e:
            logger.error("Failed to parse %s window data: %s", compositor, e)
            return None
        if not isinstance(windows, list):
            logger.error("%s returned invalid window data", compositor)
            return None
        return windows

    async def get_all_windows(self) -> list[dict]:
        """Get and normalize windows from the active compositor.

        Returns:
            List of window dictionaries with ``class``, ``pid``, and ``address``.
        """
        # The environment variables make the common case a single IPC call,
        # while the fallback keeps startup robust when a service inherited a
        # minimal environment.
        preferred = "niri" if os.environ.get("NIRI_SOCKET") else "hyprland"
        compositors = [preferred, "hyprland" if preferred == "niri" else "niri"]
        for compositor in compositors:
            windows = await self._run_ipc(compositor)
            if windows is None:
                continue
            normalized = []
            for window in windows:
                if not isinstance(window, dict):
                    continue
                item = dict(window)
                if compositor == "niri":
                    item.setdefault("class", item.get("app_id", ""))
                    item.setdefault("address", item.get("id"))
                item["_compositor"] = compositor
                normalized.append(item)
            return normalized
        logger.debug("No supported compositor IPC is available")
        return []

    def _is_browser_window(self, window: dict) -> bool:
        """Check if a window is a browser.

        Args:
            window: Normalized window dictionary from the compositor

        Returns:
            bool: True if this is a browser window
        """
        window_class = str(window.get("class") or "").lower()
        return any(browser in window_class for browser in self.browser_classes)

    def _matches_app_rule(self, window: dict, target: str) -> bool:
        """Check if a window matches an application blocking rule.

        Args:
            window: Normalized window dictionary from the compositor
            target: Target class name pattern

        Returns:
            bool: True if the window matches the rule
        """
        window_class = str(window.get("class") or "").lower()
        target_lower = target.lower()

        # Exact match
        if window_class == target_lower:
            return True

        # Partial match (for patterns like 'discord' matching 'discord-canary')
        if target_lower in window_class:
            return True

        return False

    def count_browser_windows_by_pid(self, windows: list[dict], pid: int) -> int:
        """Count browser windows for a specific PID.

        Args:
            windows: List of normalized window dictionaries from the compositor
            pid: Process ID to count windows for

        Returns:
            Number of browser windows with this PID
        """
        return sum(1 for w in windows
                   if w.get("pid") == pid and self._is_browser_window(w))

    def get_browsers_with_unmonitored_windows(
        self,
        windows: list[dict],
        browser_windows: dict[int, dict]
    ) -> set[int]:
        """Find browsers that have more windows than the extension can see.

        This detects guest profiles, other profiles without the extension, etc.

        Args:
            windows: All normalized windows from the compositor
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

            # Count windows the compositor sees for this PID
            compositor_count = self.count_browser_windows_by_pid(windows, pid)

            logger.debug(
                f"PID {pid}: Extension sees {extension_count} windows, "
                f"compositor sees {compositor_count} windows"
            )

            # If the compositor sees more windows than the extension, there are
            # unmonitored windows.
            if compositor_count > extension_count:
                # Increment mismatch counter
                mismatch_count = tracker.increment_window_mismatch(pid)

                # Require 2+ consecutive mismatches to avoid timing issues
                # (e.g., window opened between heartbeats)
                if mismatch_count >= 2:
                    logger.warning(
                        f"Browser PID {pid} has unmonitored windows! "
                        f"Extension sees {extension_count}, compositor sees {compositor_count} "
                        f"(mismatch count: {mismatch_count})"
                    )
                    unmonitored.add(pid)
                else:
                    logger.debug(
                        f"PID {pid}: Window count mismatch ({extension_count} vs {compositor_count}), "
                        f"waiting for confirmation (count: {mismatch_count}/2)"
                    )
            else:
                # Counts match, reset mismatch counter
                tracker.reset_window_mismatch(pid)

        return unmonitored

    async def close_window(self, window: dict, reason: str = "blocked") -> bool:
        """Close a window by its compositor-specific identifier.

        Args:
            window: Normalized window dictionary from the compositor
            reason: Reason for closing (for logging)

        Returns:
            bool: True if successfully closed
        """
        address = window.get("address")
        compositor = window.get("_compositor", "hyprland")
        if address is None:
            return False

        try:
            command = (
                ["niri", "msg", "action", "close-window", "--id", str(address)]
                if compositor == "niri"
                else ["hyprctl", "dispatch", "closewindow", f"address:{address}"]
            )
            result = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                logger.info(
                    f"Closed window: {window.get('class')} "
                    f"(PID: {window.get('pid')}, reason: {reason})"
                )
                return True
            else:
                logger.error(f"Failed to close window via {compositor}: {stderr.decode()}")
                return False

        except Exception as e:
            logger.error(f"Error closing window: {e}")
            return False

    async def log_block_event(self, target: str, event_type: str, rule_id: int | None = None) -> None:
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
            window_class = str(window.get("class") or "")
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
        browser_windows: dict[int, dict] = {}
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

    async def run_check(self) -> dict:
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
HyprlandMonitor = CompositorMonitor
_monitor: CompositorMonitor | None = None


def init_hyprland_monitor(session_factory) -> CompositorMonitor:
    """Initialize and get the global compositor monitor instance."""
    global _monitor
    _monitor = CompositorMonitor(session_factory)
    return _monitor


def get_hyprland_monitor() -> CompositorMonitor | None:
    """Get the global compositor monitor instance."""
    return _monitor
