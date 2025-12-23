"""Block schedule management and checking for the website blocker daemon."""

from datetime import datetime, time as dt_time
from typing import List, Set
import json
import logging
import sys
import os

from sqlalchemy import select
from sqlalchemy.orm import selectinload

# Add daemon directory to Python path for absolute imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Block

logger = logging.getLogger(__name__)


class BlockChecker:
    """Checks blocks and determines which blocks should be active based on block_mode."""

    def __init__(self, session_factory):
        """Initialize the block checker.

        Args:
            session_factory: Async session factory for database access
        """
        self._session_factory = session_factory
        self._active_blocks: Set[int] = set()

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

    def _is_time_in_range(self, days_of_week: str, start_time: str, end_time: str, now: datetime) -> bool:
        """Check if current time is within the specified time range.

        Args:
            days_of_week: Days string (JSON array or comma-separated)
            start_time: Start time string like "09:00"
            end_time: End time string like "17:00"
            now: Current datetime

        Returns:
            bool: True if current time is in the range
        """
        # Check day of week
        if days_of_week:
            days = self._parse_days_of_week(days_of_week)
            if days and now.weekday() not in days:
                return False

        # Check time range
        if start_time and end_time:
            start = self._parse_time(start_time)
            end = self._parse_time(end_time)
            current_time = now.time()

            # Handle overnight schedules (e.g., 22:00 - 06:00)
            if start <= end:
                return start <= current_time <= end
            else:
                return current_time >= start or current_time <= end

        return True  # No time range specified means always active

    def _is_block_active(self, block: Block, now: datetime) -> bool:
        """Check if a block's rules should currently be enforced.

        Args:
            block: A Block object
            now: Current datetime

        Returns:
            bool: True if the block's rules should be active
        """
        if not block.enabled:
            return False

        if block.block_mode == 'disabled':
            return False

        if block.block_mode == 'always':
            return True

        if block.block_mode == 'time_range':
            return self._is_time_in_range(
                block.block_days_of_week,
                block.block_start_time,
                block.block_end_time,
                now
            )

        return False

    async def get_active_blocks(self) -> List[Block]:
        """Get all currently active blocks based on schedules.

        Returns:
            List of Block objects that should be enforced now
        """
        now = datetime.now()
        active_blocks = []

        async with self._session_factory() as session:
            result = await session.execute(select(Block))
            blocks = result.scalars().all()

            for block in blocks:
                if self._is_block_active(block, now):
                    active_blocks.append(block)

        return active_blocks

    async def check_schedules(self) -> Set[int]:
        """Check all blocks and return set of active block IDs.

        This method should be called periodically to update the active blocks.

        Returns:
            Set of block IDs that should currently be active
        """
        active_blocks = await self.get_active_blocks()
        new_active_blocks = {b.id for b in active_blocks}

        # Log changes
        activated = new_active_blocks - self._active_blocks
        deactivated = self._active_blocks - new_active_blocks

        for block_id in activated:
            logger.info(f"Block {block_id} activated")

        for block_id in deactivated:
            logger.info(f"Block {block_id} deactivated")

        self._active_blocks = new_active_blocks
        return new_active_blocks


# Global checker instance
_scheduler: 'BlockChecker | None' = None


def init_scheduler(session_factory) -> BlockChecker:
    """Initialize and get the global block checker instance."""
    global _scheduler
    _scheduler = BlockChecker(session_factory)
    return _scheduler


def get_scheduler() -> 'BlockChecker | None':
    """Get the global block checker instance."""
    return _scheduler
