"""Schedule management and checking for the website blocker daemon."""

from datetime import datetime, time as dt_time
from typing import List, Set
import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database import Schedule, ScheduleRule, BlockRule

logger = logging.getLogger(__name__)


class ScheduleChecker:
    """Checks schedules and determines which rules should be active."""

    def __init__(self, session_factory):
        """Initialize the schedule checker.

        Args:
            session_factory: Async session factory for database access
        """
        self._session_factory = session_factory
        self._active_rules: Set[int] = set()

    def _parse_time(self, time_str: str) -> dt_time:
        """Parse a time string like '09:00' into a time object."""
        parts = time_str.split(':')
        return dt_time(int(parts[0]), int(parts[1]))

    def _is_schedule_active(self, schedule: Schedule, now: datetime) -> bool:
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
                try:
                    days = json.loads(schedule.days_of_week)
                    if now.weekday() not in days:
                        return False
                except json.JSONDecodeError:
                    logger.error(f"Invalid days_of_week JSON in schedule {schedule.id}")
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

    async def get_active_rules(self) -> List[BlockRule]:
        """Get all currently active blocking rules based on schedules.

        Returns:
            List of BlockRule objects that should be enforced now
        """
        now = datetime.now()
        active_rule_ids: Set[int] = set()

        async with self._session_factory() as session:
            # Get all schedules with their associated rules
            result = await session.execute(
                select(Schedule).options(selectinload(Schedule.schedule_rules))
            )
            schedules = result.scalars().all()

            for schedule in schedules:
                if self._is_schedule_active(schedule, now):
                    for schedule_rule in schedule.schedule_rules:
                        active_rule_ids.add(schedule_rule.rule_id)

            # Also get rules that are enabled but not attached to any schedule
            # (always-on rules)
            result = await session.execute(
                select(BlockRule).where(BlockRule.enabled == True)
            )
            all_enabled_rules = result.scalars().all()

            # Filter to only rules in active schedules or rules with no schedule
            active_rules = []
            for rule in all_enabled_rules:
                if rule.id in active_rule_ids:
                    active_rules.append(rule)
                elif not rule.schedule_rules:
                    # Rule has no schedule associations - it's always active
                    active_rules.append(rule)

            return active_rules

    async def get_active_website_rules(self) -> List[BlockRule]:
        """Get active website blocking rules.

        Returns:
            List of active BlockRule objects with rule_type='website'
        """
        active = await self.get_active_rules()
        return [r for r in active if r.rule_type == 'website']

    async def get_active_app_rules(self) -> List[BlockRule]:
        """Get active application blocking rules.

        Returns:
            List of active BlockRule objects with rule_type='application'
        """
        active = await self.get_active_rules()
        return [r for r in active if r.rule_type == 'application']

    async def check_schedules(self) -> Set[int]:
        """Check all schedules and return set of active rule IDs.

        This method should be called periodically to update the active rules.

        Returns:
            Set of rule IDs that should currently be active
        """
        active_rules = await self.get_active_rules()
        new_active_rules = {r.id for r in active_rules}

        # Log changes
        activated = new_active_rules - self._active_rules
        deactivated = self._active_rules - new_active_rules

        for rule_id in activated:
            logger.info(f"Rule {rule_id} activated by schedule")

        for rule_id in deactivated:
            logger.info(f"Rule {rule_id} deactivated by schedule")

        self._active_rules = new_active_rules
        return new_active_rules


# Global scheduler instance
_scheduler: 'ScheduleChecker | None' = None


def init_scheduler(session_factory) -> ScheduleChecker:
    """Initialize and get the global schedule checker instance."""
    global _scheduler
    _scheduler = ScheduleChecker(session_factory)
    return _scheduler


def get_scheduler() -> 'ScheduleChecker | None':
    """Get the global schedule checker instance."""
    return _scheduler
