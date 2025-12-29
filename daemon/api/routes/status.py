"""Status, stats, browsers, and blocked-sites API routes."""

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import Block, BlockEvent
from heartbeat_tracker import get_heartbeat_tracker
from lock_manager import get_lock_manager
from ..schemas import StatusResponse, StatsResponse, BrowserStatus
from ..deps import get_session

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/status", response_model=StatusResponse)
async def get_status(session: AsyncSession = Depends(get_session)):
    """Get daemon status and lock state."""
    lock_manager = get_lock_manager()
    tracker = get_heartbeat_tracker()

    lock_status = await lock_manager.get_lock_status() if lock_manager else {
        "locked": False,
        "lock_end_time": None
    }

    # Count active blocks
    result = await session.execute(
        select(func.count(Block.id)).where(Block.enabled == True)
    )
    active_blocks = result.scalar() or 0

    browser_statuses = tracker.get_all_browser_statuses()
    browsers_detected = len(browser_statuses)
    browsers_compliant = sum(1 for b in browser_statuses if b.get("compliant", False))

    return StatusResponse(
        running=True,
        locked=lock_status["locked"],
        lock_end_time=lock_status.get("lock_end_time"),
        active_rules=0,  # Legacy field, no longer used
        active_blocks=active_blocks,
        browsers_detected=browsers_detected,
        browsers_compliant=browsers_compliant
    )


@router.get("/stats", response_model=StatsResponse)
async def get_stats(session: AsyncSession = Depends(get_session)):
    """Get blocking statistics."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = today.replace(day=today.day - 7) if today.day > 7 else today.replace(month=today.month - 1, day=28)
    month_ago = today.replace(month=today.month - 1) if today.month > 1 else today.replace(year=today.year - 1, month=12)

    # Today's stats
    result = await session.execute(
        select(func.count(BlockEvent.id))
        .where(BlockEvent.timestamp >= today)
    )
    total_today = result.scalar() or 0

    result = await session.execute(
        select(func.count(BlockEvent.id))
        .where(BlockEvent.timestamp >= today)
        .where(BlockEvent.event_type == 'website_blocked')
    )
    websites_today = result.scalar() or 0

    result = await session.execute(
        select(func.count(BlockEvent.id))
        .where(BlockEvent.timestamp >= today)
        .where(BlockEvent.event_type == 'app_closed')
    )
    apps_today = result.scalar() or 0

    result = await session.execute(
        select(func.count(BlockEvent.id))
        .where(BlockEvent.timestamp >= today)
        .where(BlockEvent.event_type == 'browser_killed')
    )
    browsers_today = result.scalar() or 0

    # Week stats
    result = await session.execute(
        select(func.count(BlockEvent.id))
        .where(BlockEvent.timestamp >= week_ago)
    )
    total_week = result.scalar() or 0

    # Month stats
    result = await session.execute(
        select(func.count(BlockEvent.id))
        .where(BlockEvent.timestamp >= month_ago)
    )
    total_month = result.scalar() or 0

    return StatsResponse(
        total_blocks_today=total_today,
        total_blocks_week=total_week,
        total_blocks_month=total_month,
        websites_blocked_today=websites_today,
        apps_closed_today=apps_today,
        browsers_killed_today=browsers_today
    )


@router.get("/browsers", response_model=List[BrowserStatus])
async def get_browsers():
    """Get detected browsers and extension status."""
    tracker = get_heartbeat_tracker()
    statuses = tracker.get_all_browser_statuses()

    return [
        BrowserStatus(
            pid=s["pid"],
            browser=s["browser"],
            compliant=s["compliant"],
            last_heartbeat=s["last_heartbeat"],
            incognito_active=s["incognito_active"],
            incognito_enabled=s["incognito_enabled"]
        )
        for s in statuses
    ]


@router.get("/blocked-sites")
async def get_blocked_sites():
    """Get list of currently active blocked website patterns.

    This endpoint is used by the browser extension to get the list
    of sites to block. Returns per-block data so extension can implement
    intersection-based allow list logic.
    """
    from scheduler import get_scheduler
    from config import get_config

    scheduler = get_scheduler()
    config = get_config()

    if scheduler is None:
        return {
            "blocks": [],
            "safe_search_enabled": config.security.safe_search_enabled
        }

    active_blocks = await scheduler.get_active_blocks()

    # Return per-block data
    blocks_data = []

    for block in active_blocks:
        block_data = {
            "id": block.id,
            "name": block.name,
            "blocked": [],
            "allowed": []
        }

        # Parse blocked patterns
        if block.websites_blocked:
            block_data["blocked"] = [
                line.strip()
                for line in block.websites_blocked.split('\n')
                if line.strip()
            ]

        # Parse allowed patterns
        if block.websites_allowed:
            block_data["allowed"] = [
                line.strip()
                for line in block.websites_allowed.split('\n')
                if line.strip()
            ]

        blocks_data.append(block_data)

    return {
        "blocks": blocks_data,
        "safe_search_enabled": config.security.safe_search_enabled
    }
