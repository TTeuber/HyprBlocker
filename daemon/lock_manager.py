"""Lock mode management for the website blocker daemon."""

from datetime import datetime, time as dt_time, timedelta
from typing import List, Optional
import json
import logging
import subprocess

from time_verifier import get_time_verifier

logger = logging.getLogger(__name__)


class LockManager:
    """Manages lock mode during scheduled blocking periods."""

    def __init__(self, get_schedules_func):
        """Initialize the lock manager.

        Args:
            get_schedules_func: Async function that returns list of Schedule objects
        """
        self._get_schedules = get_schedules_func
        self._time_verifier = get_time_verifier()
        self._was_locked = False
        self._lock_end_time: Optional[datetime] = None

    def _parse_time(self, time_str: str) -> dt_time:
        """Parse a time string like '09:00' into a time object."""
        parts = time_str.split(':')
        return dt_time(int(parts[0]), int(parts[1]))

    def _is_schedule_active(self, schedule, now: datetime) -> bool:
        """Check if a schedule is currently active.

        Args:
            schedule: A Schedule object
            now: Current datetime

        Returns:
            bool: True if the schedule is active now
        """
        if not schedule.enabled:
            return False

        if schedule.schedule_type == 'locked_until':
            if schedule.locked_until:
                return now < schedule.locked_until
            return False

        elif schedule.schedule_type == 'time_range':
            # Check day of week (0=Monday in Python)
            if schedule.days_of_week:
                days = json.loads(schedule.days_of_week)
                if now.weekday() not in days:
                    return False

            # Check time range
            if schedule.start_time and schedule.end_time:
                start = self._parse_time(schedule.start_time)
                end = self._parse_time(schedule.end_time)
                current_time = now.time()

                # Handle overnight schedules (e.g., 22:00 - 06:00)
                if start <= end:
                    return start <= current_time <= end
                else:
                    return current_time >= start or current_time <= end

        return False

    def _get_next_unlock_time(self, schedule, now: datetime) -> Optional[datetime]:
        """Get when the current lock period will end for a schedule.

        Args:
            schedule: A Schedule object
            now: Current datetime

        Returns:
            datetime or None: When the lock will end
        """
        if schedule.schedule_type == 'locked_until':
            return schedule.locked_until

        elif schedule.schedule_type == 'time_range':
            if schedule.end_time:
                end = self._parse_time(schedule.end_time)
                end_datetime = datetime.combine(now.date(), end)

                # If end time is before now (overnight schedule), it's tomorrow
                if end_datetime <= now:
                    end_datetime += timedelta(days=1)

                return end_datetime

        return None

    async def is_locked(self) -> bool:
        """Check if currently in a locked period.

        Returns:
            bool: True if locked, False otherwise
        """
        now = self._time_verifier.get_verified_time()
        schedules = await self._get_schedules()

        for schedule in schedules:
            if self._is_schedule_active(schedule, now):
                # Update lock end time
                unlock_time = self._get_next_unlock_time(schedule, now)
                if unlock_time:
                    if self._lock_end_time is None or unlock_time > self._lock_end_time:
                        self._lock_end_time = unlock_time

                return True

        self._lock_end_time = None
        return False

    async def get_lock_status(self) -> dict:
        """Get detailed lock status.

        Returns:
            dict with locked state, end time, and active schedules
        """
        now = self._time_verifier.get_verified_time()
        schedules = await self._get_schedules()
        active_schedules = []
        earliest_end = None

        for schedule in schedules:
            if self._is_schedule_active(schedule, now):
                active_schedules.append(schedule.name)
                unlock_time = self._get_next_unlock_time(schedule, now)
                if unlock_time:
                    if earliest_end is None or unlock_time < earliest_end:
                        earliest_end = unlock_time

        is_locked = len(active_schedules) > 0

        return {
            "locked": is_locked,
            "lock_end_time": earliest_end.isoformat() if earliest_end else None,
            "active_schedules": active_schedules,
            "remaining_seconds": int((earliest_end - now).total_seconds()) if earliest_end else None
        }

    async def handle_lock_transition(self, entering_lock: bool) -> None:
        """Handle transition into or out of lock mode.

        Args:
            entering_lock: True if entering lock, False if exiting
        """
        if entering_lock:
            # Verify time with NTP before entering lock
            if not self._time_verifier.verify_at_lock_transitions():
                logger.warning("Time verification failed when entering lock - blocking anyway (fail-safe)")

            self._show_notification(
                "Website Blocker",
                "Lock mode activated. Configuration is now read-only."
            )
            logger.info("Entered lock mode")

        else:
            # Verify time with NTP before exiting lock
            if not self._time_verifier.verify_at_lock_transitions():
                logger.warning("Time verification failed when exiting lock - may be manipulation attempt")
                # Don't exit lock if time seems manipulated
                return

            self._show_notification(
                "Website Blocker",
                "Lock mode ended. Configuration can now be modified."
            )
            logger.info("Exited lock mode")

    async def check_transitions(self) -> None:
        """Check for lock state transitions and handle them."""
        is_locked = await self.is_locked()

        if is_locked and not self._was_locked:
            await self.handle_lock_transition(entering_lock=True)
        elif not is_locked and self._was_locked:
            await self.handle_lock_transition(entering_lock=False)

        self._was_locked = is_locked

    def _show_notification(self, title: str, message: str) -> None:
        """Show a desktop notification.

        Args:
            title: Notification title
            message: Notification message
        """
        try:
            subprocess.run(
                ["notify-send", title, message],
                capture_output=True,
                timeout=5
            )
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            logger.warning(f"Failed to show notification: {e}")


# Global lock manager instance
_lock_manager: Optional[LockManager] = None


def init_lock_manager(get_schedules_func) -> LockManager:
    """Initialize and get the global lock manager instance."""
    global _lock_manager
    _lock_manager = LockManager(get_schedules_func)
    return _lock_manager


def get_lock_manager() -> Optional[LockManager]:
    """Get the global lock manager instance."""
    return _lock_manager
