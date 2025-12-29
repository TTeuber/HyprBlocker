"""FastAPI REST API for the website blocker daemon."""

import logging
import sys
import os

# Add daemon directory to Python path for absolute imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from database import Block, BlockEvent, create_session_factory
from heartbeat_tracker import get_heartbeat_tracker
from lock_manager import get_lock_manager
from blocker import get_site_blocker

# Pydantic models for API
class HeartbeatRequest(BaseModel):
    pid: int
    browser: str
    incognito: bool = False
    incognito_enabled: bool = True
    extension_id: str  # Unique per browser profile
    window_count: int  # Windows visible to this extension
    timestamp: Optional[int] = None


class HeartbeatResponse(BaseModel):
    status: str



class BlockCreate(BaseModel):
    name: str
    block_mode: str = 'always'  # 'always', 'time_range', 'disabled'
    block_days_of_week: Optional[str] = None  # JSON array
    block_start_time: Optional[str] = None
    block_end_time: Optional[str] = None
    lock_mode: str = 'none'  # 'none', 'time_range', 'locked_until'
    lock_days_of_week: Optional[str] = None
    lock_start_time: Optional[str] = None
    lock_end_time: Optional[str] = None
    lock_until: Optional[str] = None  # ISO format datetime
    enabled: bool = True
    websites_blocked: Optional[str] = None  # Newline-separated list
    websites_allowed: Optional[str] = None  # Newline-separated allow list
    apps_blocked: Optional[str] = None      # Newline-separated list
    apps_allowed: Optional[str] = None      # Newline-separated allow list


class BlockUpdate(BaseModel):
    name: Optional[str] = None
    block_mode: Optional[str] = None
    block_days_of_week: Optional[str] = None
    block_start_time: Optional[str] = None
    block_end_time: Optional[str] = None
    lock_mode: Optional[str] = None
    lock_days_of_week: Optional[str] = None
    lock_start_time: Optional[str] = None
    lock_end_time: Optional[str] = None
    lock_until: Optional[str] = None
    enabled: Optional[bool] = None
    websites_blocked: Optional[str] = None
    websites_allowed: Optional[str] = None
    apps_blocked: Optional[str] = None
    apps_allowed: Optional[str] = None


class BlockResponse(BaseModel):
    id: int
    name: str
    block_mode: str
    block_days_of_week: Optional[str]
    block_start_time: Optional[str]
    block_end_time: Optional[str]
    lock_mode: str
    lock_days_of_week: Optional[str]
    lock_start_time: Optional[str]
    lock_end_time: Optional[str]
    lock_until: Optional[str]
    websites_blocked: Optional[str]
    websites_allowed: Optional[str]
    apps_blocked: Optional[str]
    apps_allowed: Optional[str]
    enabled: bool
    created_at: str

    class Config:
        from_attributes = True


class StatusResponse(BaseModel):
    running: bool
    locked: bool
    lock_end_time: Optional[str]
    active_rules: int
    active_blocks: int
    browsers_detected: int
    browsers_compliant: int


class StatsResponse(BaseModel):
    total_blocks_today: int
    total_blocks_week: int
    total_blocks_month: int
    websites_blocked_today: int
    apps_closed_today: int
    browsers_killed_today: int


class BrowserStatus(BaseModel):
    pid: int
    browser: str
    compliant: bool
    last_heartbeat: str
    incognito_active: bool
    incognito_enabled: bool


class GracePeriodResponse(BaseModel):
    active: bool
    expires_at: Optional[str]
    remaining_seconds: Optional[int]


class DevModeStatusResponse(BaseModel):
    enabled: bool
    source: str  # 'environment', 'config', or 'default'


class DevModeUpdateRequest(BaseModel):
    enabled: bool


class WatchdogStatusResponse(BaseModel):
    enabled: bool
    count: int
    active_watchdogs: List[dict]  # [{pid, name, uptime_seconds}]


class WatchdogUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    count: Optional[int] = None


class SettingsLockResponse(BaseModel):
    locked: bool
    lock_until: Optional[str]  # ISO datetime
    remaining_seconds: Optional[int]


class SettingsLockRequest(BaseModel):
    lock_until: str  # ISO datetime


# Create FastAPI app
app = FastAPI(
    title="Website Blocker Daemon",
    description="REST API for the website blocker daemon",
    version="1.0.0"
)

# Add CORS middleware for local access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session factory - will be set during startup
_session_factory = None


def set_session_factory(factory):
    """Set the session factory for API routes."""
    global _session_factory
    _session_factory = factory


async def get_session():
    """Dependency to get a database session."""
    if _session_factory is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    async with _session_factory() as session:
        yield session


async def check_block_lock(block_id: int):
    """Check if a specific block is locked.

    Raises:
        HTTPException: 403 if block is locked
    """
    lock_manager = get_lock_manager()
    if lock_manager and await lock_manager.is_block_locked(block_id):
        raise HTTPException(
            status_code=403,
            detail=f"Cannot modify block {block_id}: currently locked"
        )




# Heartbeat endpoint
@app.post("/api/heartbeat", response_model=HeartbeatResponse)
async def receive_heartbeat(heartbeat: HeartbeatRequest):
    """Receive a heartbeat from a browser extension."""
    tracker = get_heartbeat_tracker()
    tracker.register_heartbeat(
        pid=heartbeat.pid,
        browser=heartbeat.browser,
        incognito=heartbeat.incognito,
        incognito_enabled=heartbeat.incognito_enabled,
        extension_id=heartbeat.extension_id,
        window_count=heartbeat.window_count
    )
    return HeartbeatResponse(status="ok")


# Grace period endpoints
@app.post("/api/grace-period", response_model=GracePeriodResponse)
async def start_grace_period():
    """Start a 30-second grace period for adding browser extensions."""
    tracker = get_heartbeat_tracker()
    expires_at = tracker.start_grace_period(duration_seconds=30)

    return GracePeriodResponse(
        active=True,
        expires_at=expires_at.isoformat(),
        remaining_seconds=30
    )


@app.get("/api/grace-period", response_model=GracePeriodResponse)
async def get_grace_period_status():
    """Get the current grace period status."""
    tracker = get_heartbeat_tracker()

    if tracker.is_grace_period_active():
        return GracePeriodResponse(
            active=True,
            expires_at=tracker._grace_period_until.isoformat() if tracker._grace_period_until else None,
            remaining_seconds=tracker.get_grace_period_remaining()
        )

    return GracePeriodResponse(
        active=False,
        expires_at=None,
        remaining_seconds=None
    )


# Status endpoint
@app.get("/api/status", response_model=StatusResponse)
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


# Blocks endpoints
@app.get("/api/blocks", response_model=List[BlockResponse])
async def get_blocks(session: AsyncSession = Depends(get_session)):
    """Get all blocks."""
    result = await session.execute(select(Block))
    blocks = result.scalars().all()

    return [BlockResponse(**b.to_dict()) for b in blocks]


@app.post("/api/blocks", response_model=BlockResponse)
async def create_block(block: BlockCreate, session: AsyncSession = Depends(get_session)):
    """Create a new block."""
    if block.block_mode not in ('always', 'time_range', 'disabled'):
        raise HTTPException(status_code=400, detail="Invalid block_mode")

    if block.lock_mode not in ('none', 'time_range', 'locked_until'):
        raise HTTPException(status_code=400, detail="Invalid lock_mode")

    lock_until = None
    if block.lock_until:
        try:
            lock_until = datetime.fromisoformat(block.lock_until)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid lock_until datetime format")

    db_block = Block(
        name=block.name,
        block_mode=block.block_mode,
        block_days_of_week=block.block_days_of_week,
        block_start_time=block.block_start_time,
        block_end_time=block.block_end_time,
        lock_mode=block.lock_mode,
        lock_days_of_week=block.lock_days_of_week,
        lock_start_time=block.lock_start_time,
        lock_end_time=block.lock_end_time,
        lock_until=lock_until,
        websites_blocked=block.websites_blocked,
        websites_allowed=block.websites_allowed,
        apps_blocked=block.apps_blocked,
        apps_allowed=block.apps_allowed,
        enabled=block.enabled
    )
    session.add(db_block)
    await session.commit()
    await session.refresh(db_block)

    return BlockResponse(**db_block.to_dict())


@app.put("/api/blocks/{block_id}", response_model=BlockResponse)
async def update_block(
    block_id: int,
    block: BlockUpdate,
    session: AsyncSession = Depends(get_session)
):
    """Update a block."""
    await check_block_lock(block_id)

    result = await session.execute(select(Block).where(Block.id == block_id))
    db_block = result.scalar_one_or_none()

    if db_block is None:
        raise HTTPException(status_code=404, detail="Block not found")

    if block.name is not None:
        db_block.name = block.name

    if block.block_mode is not None:
        if block.block_mode not in ('always', 'time_range', 'disabled'):
            raise HTTPException(status_code=400, detail="Invalid block_mode")
        db_block.block_mode = block.block_mode

    if block.block_days_of_week is not None:
        db_block.block_days_of_week = block.block_days_of_week

    if block.block_start_time is not None:
        db_block.block_start_time = block.block_start_time

    if block.block_end_time is not None:
        db_block.block_end_time = block.block_end_time

    # Handle lock_mode and lock_until together for consistency
    if block.lock_mode is not None:
        if block.lock_mode not in ('none', 'time_range', 'locked_until'):
            raise HTTPException(status_code=400, detail="Invalid lock_mode")
        db_block.lock_mode = block.lock_mode

        # Clear lock_until if changing away from locked_until mode
        if block.lock_mode != 'locked_until':
            db_block.lock_until = None

    if block.lock_days_of_week is not None:
        db_block.lock_days_of_week = block.lock_days_of_week

    if block.lock_start_time is not None:
        db_block.lock_start_time = block.lock_start_time

    if block.lock_end_time is not None:
        db_block.lock_end_time = block.lock_end_time

    # Handle lock_until with validation
    if block.lock_until is not None:
        # Skip empty strings
        if block.lock_until.strip() == '':
            # If explicitly setting to empty, clear it
            db_block.lock_until = None
        else:
            try:
                db_block.lock_until = datetime.fromisoformat(block.lock_until)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid lock_until datetime format. Expected ISO format like '2024-12-25T14:30'")

    # Validate that locked_until mode has a lock_until value
    if db_block.lock_mode == 'locked_until' and db_block.lock_until is None:
        raise HTTPException(status_code=400, detail="lock_until datetime is required when lock_mode is 'locked_until'")

    if block.enabled is not None:
        db_block.enabled = block.enabled

    if block.websites_blocked is not None:
        db_block.websites_blocked = block.websites_blocked

    if block.websites_allowed is not None:
        db_block.websites_allowed = block.websites_allowed

    if block.apps_blocked is not None:
        db_block.apps_blocked = block.apps_blocked

    if block.apps_allowed is not None:
        db_block.apps_allowed = block.apps_allowed

    await session.commit()
    await session.refresh(db_block)

    return BlockResponse(**db_block.to_dict())


@app.delete("/api/blocks/{block_id}")
async def delete_block(block_id: int, session: AsyncSession = Depends(get_session)):
    """Delete a block."""
    await check_block_lock(block_id)

    result = await session.execute(select(Block).where(Block.id == block_id))
    db_block = result.scalar_one_or_none()

    if db_block is None:
        raise HTTPException(status_code=404, detail="Block not found")

    await session.delete(db_block)
    await session.commit()

    return {"status": "deleted"}


@app.get("/api/blocks/{block_id}/lock-status")
async def get_block_lock_status(block_id: int):
    """Get lock status for a specific block."""
    lock_manager = get_lock_manager()
    if lock_manager:
        is_locked = await lock_manager.is_block_locked(block_id)
        return {"locked": is_locked}
    return {"locked": False}


# Stats endpoint
@app.get("/api/stats", response_model=StatsResponse)
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


# Browsers endpoint
@app.get("/api/browsers", response_model=List[BrowserStatus])
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


# Blocked sites endpoint for browser extension
@app.get("/api/blocked-sites")
async def get_blocked_sites():
    """Get list of currently active blocked website patterns.

    This endpoint is used by the browser extension to get the list
    of sites to block. Returns per-block data so extension can implement
    intersection-based allow list logic.
    """
    from scheduler import get_scheduler

    scheduler = get_scheduler()
    if scheduler is None:
        return {"blocks": []}

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
        "blocks": blocks_data
    }


# Settings endpoints
@app.get("/api/settings/dev-mode", response_model=DevModeStatusResponse)
async def get_dev_mode_status():
    """Get current dev mode status."""
    from config import get_config
    import os

    config = get_config()

    # Check if set via environment (takes precedence)
    dev_mode_env = os.getenv('BLOCKER_DEV_MODE', 'false').lower()
    if dev_mode_env in ('true', '1', 'yes'):
        return DevModeStatusResponse(
            enabled=True,
            source='environment'
        )

    return DevModeStatusResponse(
        enabled=config.security.dev_mode,
        source='config' if config.security.dev_mode else 'default'
    )


@app.put("/api/settings/dev-mode")
async def update_dev_mode_status(request: DevModeUpdateRequest):
    """Update dev mode setting.

    Note: This only works if dev mode is not set via environment variable.
    """
    from config import get_config, save_config, reload_config
    import os

    logger = logging.getLogger(__name__)

    # Check if environment variable is set
    dev_mode_env = os.getenv('BLOCKER_DEV_MODE', 'false').lower()
    if dev_mode_env in ('true', '1', 'yes'):
        raise HTTPException(
            status_code=403,
            detail="Dev mode is set via environment variable and cannot be changed through the UI"
        )

    # Update config
    config = get_config()
    config.security.dev_mode = request.enabled
    save_config(config)

    # Reload config to apply changes immediately
    reload_config()

    if request.enabled:
        logger.warning("🚨 DEV MODE ENABLED via UI - Browser enforcement disabled!")
    else:
        logger.info("✅ DEV MODE DISABLED via UI - Browser enforcement active")

    return {"success": True, "enabled": request.enabled}


# Watchdog settings endpoints
@app.get("/api/settings/watchdog", response_model=WatchdogStatusResponse)
async def get_watchdog_status():
    """Get current watchdog status and active processes."""
    from config import get_config
    from watchdog import WatchdogManager

    config = get_config()
    manager = WatchdogManager(
        watchdog_count=config.security.watchdog_count,
        daemon_port=config.daemon.port
    )

    active = manager.get_active_watchdogs()

    return WatchdogStatusResponse(
        enabled=config.security.watchdog_enabled,
        count=config.security.watchdog_count,
        active_watchdogs=active
    )


@app.put("/api/settings/watchdog")
async def update_watchdog_settings(request: WatchdogUpdateRequest):
    """Update watchdog settings.

    Blocked if settings are locked.
    """
    from config import get_config, save_config, reload_config
    from watchdog import WatchdogManager, is_settings_locked_ntp

    logger = logging.getLogger(__name__)

    # Check if settings are locked
    if is_settings_locked_ntp():
        raise HTTPException(
            status_code=403,
            detail="Settings are locked and cannot be changed"
        )

    config = get_config()

    if request.enabled is not None:
        old_enabled = config.security.watchdog_enabled
        config.security.watchdog_enabled = request.enabled

        # If enabling, spawn watchdogs
        if request.enabled and not old_enabled:
            manager = WatchdogManager(
                watchdog_count=config.security.watchdog_count,
                daemon_port=config.daemon.port
            )
            manager.spawn_watchdogs()
            logger.info("Watchdog processes spawned")

        # If disabling, signal shutdown
        elif not request.enabled and old_enabled:
            manager = WatchdogManager(
                watchdog_count=config.security.watchdog_count,
                daemon_port=config.daemon.port
            )
            manager.signal_shutdown()
            logger.info("Watchdog shutdown signaled")

    if request.count is not None:
        # Clamp to valid range
        config.security.watchdog_count = max(2, min(5, request.count))

    save_config(config)
    reload_config()

    return {
        "success": True,
        "enabled": config.security.watchdog_enabled,
        "count": config.security.watchdog_count
    }


# Settings lock endpoints
@app.get("/api/settings/lock", response_model=SettingsLockResponse)
async def get_settings_lock():
    """Get current settings lock status."""
    from config import get_config
    from watchdog import is_settings_locked_ntp
    from datetime import datetime, timezone

    config = get_config()
    lock_until_str = config.security.settings_lock_until

    if not lock_until_str:
        return SettingsLockResponse(
            locked=False,
            lock_until=None,
            remaining_seconds=None
        )

    # Check if actually locked (NTP verified)
    is_locked = is_settings_locked_ntp()

    if not is_locked:
        return SettingsLockResponse(
            locked=False,
            lock_until=lock_until_str,
            remaining_seconds=0
        )

    # Calculate remaining time
    try:
        lock_until = datetime.fromisoformat(lock_until_str)
        if lock_until.tzinfo is None:
            lock_until = lock_until.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        remaining = int((lock_until - now).total_seconds())
    except Exception:
        remaining = None

    return SettingsLockResponse(
        locked=True,
        lock_until=lock_until_str,
        remaining_seconds=max(0, remaining) if remaining else None
    )


@app.post("/api/settings/lock")
async def lock_settings(request: SettingsLockRequest):
    """Lock settings until a specific datetime.

    Uses NTP verification to prevent clock manipulation.
    """
    from config import get_config, save_config, reload_config
    from time_verifier import get_time_verifier
    from datetime import datetime, timezone

    logger = logging.getLogger(__name__)

    # Parse and validate lock_until
    try:
        lock_until = datetime.fromisoformat(request.lock_until)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid datetime format. Use ISO format like '2024-12-25T14:30:00'"
        )

    # Ensure it's in the future (use NTP time)
    verifier = get_time_verifier()
    if not verifier.is_system_time_valid():
        raise HTTPException(
            status_code=403,
            detail="System time appears to be manipulated. Cannot set lock."
        )

    now = datetime.now(timezone.utc)
    if lock_until.tzinfo is None:
        lock_until = lock_until.replace(tzinfo=timezone.utc)

    if lock_until <= now:
        raise HTTPException(
            status_code=400,
            detail="lock_until must be in the future"
        )

    # Save the lock
    config = get_config()
    config.security.settings_lock_until = lock_until.isoformat()
    save_config(config)
    reload_config()

    logger.info(f"Settings locked until {lock_until.isoformat()}")

    return {
        "success": True,
        "lock_until": lock_until.isoformat()
    }


@app.delete("/api/settings/lock")
async def unlock_settings():
    """Unlock settings.

    Only works if the lock has expired (verified via NTP).
    """
    from config import get_config, save_config, reload_config
    from watchdog import is_settings_locked_ntp

    logger = logging.getLogger(__name__)

    # Check if still locked
    if is_settings_locked_ntp():
        raise HTTPException(
            status_code=403,
            detail="Settings are still locked. Cannot unlock before expiry."
        )

    # Clear the lock
    config = get_config()
    config.security.settings_lock_until = None
    save_config(config)
    reload_config()

    logger.info("Settings lock cleared")

    return {"success": True}
