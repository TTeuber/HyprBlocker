"""Lock mode management for the website blocker daemon."""

from datetime import datetime, time as dt_time, timedelta
from typing import List, Optional
import json
import logging
import sys
import os

# Add daemon directory to Python path for absolute imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select
from database import Block
from time_verifier import get_time_verifier

logger = logging.getLogger(__name__)


class LockManager:
    """Manages lock mode during locked blocking periods.

    Lock mode is separate from blocking:
    - block_mode determines when content is blocked
    - lock_mode determines when configuration is read-only
    """

    def __init__(self, get_blocks_func, session_factory=None):
        """Initialize the lock manager.

        Args:
            get_blocks_func: Async function that returns list of Block objects
            session_factory: Async session factory for database operations
        """
        self._get_blocks = get_blocks_func
        self._session_factory = session_factory
        self._time_verifier = get_time_verifier()

    def _parse_time(self, time_str: str) -> dt_time:
        """Parse a time string like '09:00' into a time object."""
        parts = time_str.split(':')
        return dt_time(int(parts[0]), int(parts[1]))

    def _parse_days_of_week(self, days_of_week: str) -> List[int]:
        """Parse days of week string into list of integers.

        Handles both JSON arrays like "[0,1,2]" and comma-separated strings like "0,1,2".

        Args:
            days_of_week: Days string in either format

        Returns:
            List of day integers (0=Monday)
        """
        if not days_of_week:
            return []

        # Try JSON first
        try:
            days = json.loads(days_of_week)
            if isinstance(days, list):
                return [int(d) for d in days]
        except (json.JSONDecodeError, ValueError):
            pass

        # Try comma-separated
        try:
            return [int(d.strip()) for d in days_of_week.split(',') if d.strip()]
        except ValueError:
            logger.error(f"Invalid days_of_week format: {days_of_week}")
            return []

    def _is_block_locked(self, block, now: datetime) -> bool:
        """Check if a block's configuration is currently locked.

        Args:
            block: A Block object
            now: Current datetime

        Returns:
            bool: True if the block's config is locked
        """
        if not block.enabled:
            return False

        if block.lock_mode == 'none':
            return False

        if block.lock_mode == 'locked_until':
            if block.lock_until:
                return now < block.lock_until
            return False

        elif block.lock_mode == 'time_range':
            # Check day of week (0=Monday in Python)
            if block.lock_days_of_week:
                days = self._parse_days_of_week(block.lock_days_of_week)
                if days and now.weekday() not in days:
                    return False

            # Check time range
            if block.lock_start_time and block.lock_end_time:
                start = self._parse_time(block.lock_start_time)
                end = self._parse_time(block.lock_end_time)
                current_time = now.time()

                # Handle overnight schedules (e.g., 22:00 - 06:00)
                if start <= end:
                    return start <= current_time <= end
                else:
                    return current_time >= start or current_time <= end

        return False

    def _get_next_unlock_time(self, block, now: datetime) -> Optional[datetime]:
        """Get when the current lock period will end for a block.

        Args:
            block: A Block object
            now: Current datetime

        Returns:
            datetime or None: When the lock will end
        """
        if block.lock_mode == 'locked_until':
            return block.lock_until

        elif block.lock_mode == 'time_range':
            if block.lock_end_time:
                end = self._parse_time(block.lock_end_time)
                end_datetime = datetime.combine(now.date(), end)

                # If end time is before now (overnight schedule), it's tomorrow
                if end_datetime <= now:
                    end_datetime += timedelta(days=1)

                return end_datetime

        return None

    async def is_block_locked(self, block_id: int) -> bool:
        """Check if a specific block is currently locked.

        Args:
            block_id: The block ID to check

        Returns:
            bool: True if this specific block is locked
        """
        now = self._time_verifier.get_verified_time()
        blocks = await self._get_blocks()

        for block in blocks:
            if block.id == block_id:
                return self._is_block_locked(block, now)

        return False

    async def get_locked_blocks_for_rule(self, rule_id: int) -> List[int]:
        """Get list of locked block IDs that contain a specific rule.

        Args:
            rule_id: The rule ID to check

        Returns:
            List of locked block IDs containing this rule
        """
        now = self._time_verifier.get_verified_time()
        blocks = await self._get_blocks()
        locked_block_ids = []

        for block in blocks:
            if self._is_block_locked(block, now):
                # Check if this block contains the rule
                for block_rule in block.block_rules:
                    if block_rule.rule_id == rule_id:
                        locked_block_ids.append(block.id)
                        break

        return locked_block_ids

    async def _reset_expired_locked_until_blocks(self, now: datetime) -> None:
        """Reset lock_mode to 'none' for blocks with expired lock_until.

        Args:
            now: Current datetime
        """
        if not self._session_factory:
            return

        try:
            async with self._session_factory() as session:
                # Query blocks with expired locked_until mode
                result = await session.execute(
                    select(Block).where(
                        Block.lock_mode == 'locked_until',
                        Block.lock_until < now
                    )
                )
                expired_blocks = result.scalars().all()

                if expired_blocks:
                    for block in expired_blocks:
                        logger.info(f"Resetting expired lock for block '{block.name}' (lock_until was {block.lock_until})")
                        block.lock_mode = 'none'
                        block.lock_until = None

                    await session.commit()
                    logger.info(f"Reset {len(expired_blocks)} expired locked_until block(s)")

        except Exception as e:
            logger.error(f"Failed to reset expired locked_until blocks: {e}")

    async def check_transitions(self) -> None:
        """Check for lock state transitions and reset expired locks."""
        now = self._time_verifier.get_verified_time()
        await self._reset_expired_locked_until_blocks(now)


# Global lock manager instance
_lock_manager: Optional[LockManager] = None


def init_lock_manager(get_blocks_func, session_factory=None) -> LockManager:
    """Initialize and get the global lock manager instance."""
    global _lock_manager
    _lock_manager = LockManager(get_blocks_func, session_factory)
    return _lock_manager


def get_lock_manager() -> Optional[LockManager]:
    """Get the global lock manager instance."""
    return _lock_manager
