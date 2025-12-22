"""FastAPI REST API for the website blocker daemon."""

from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from database import BlockRule, Schedule, ScheduleRule, BlockEvent, create_session_factory
from heartbeat_tracker import get_heartbeat_tracker
from lock_manager import get_lock_manager
from blocker import get_site_blocker

# Pydantic models for API
class HeartbeatRequest(BaseModel):
    pid: int
    browser: str
    incognito: bool = False
    timestamp: Optional[int] = None


class HeartbeatResponse(BaseModel):
    status: str


class RuleCreate(BaseModel):
    rule_type: str  # 'website' or 'application'
    target: str
    enabled: bool = True


class RuleUpdate(BaseModel):
    rule_type: Optional[str] = None
    target: Optional[str] = None
    enabled: Optional[bool] = None


class RuleResponse(BaseModel):
    id: int
    rule_type: str
    target: str
    enabled: bool
    created_at: str

    class Config:
        from_attributes = True


class ScheduleCreate(BaseModel):
    name: str
    schedule_type: str  # 'time_range' or 'locked_until'
    days_of_week: Optional[str] = None  # JSON array
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    locked_until: Optional[str] = None  # ISO format datetime
    enabled: bool = True
    rule_ids: List[int] = []


class ScheduleUpdate(BaseModel):
    name: Optional[str] = None
    schedule_type: Optional[str] = None
    days_of_week: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    locked_until: Optional[str] = None
    enabled: Optional[bool] = None
    rule_ids: Optional[List[int]] = None


class ScheduleResponse(BaseModel):
    id: int
    name: str
    schedule_type: str
    days_of_week: Optional[str]
    start_time: Optional[str]
    end_time: Optional[str]
    locked_until: Optional[str]
    enabled: bool
    created_at: str
    rule_ids: List[int]

    class Config:
        from_attributes = True


class StatusResponse(BaseModel):
    running: bool
    locked: bool
    lock_end_time: Optional[str]
    active_rules: int
    active_schedules: int
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


async def check_lock_mode():
    """Check if the system is in lock mode."""
    lock_manager = get_lock_manager()
    if lock_manager and await lock_manager.is_locked():
        raise HTTPException(
            status_code=403,
            detail="Cannot modify configuration during lock period"
        )


# Heartbeat endpoint
@app.post("/api/heartbeat", response_model=HeartbeatResponse)
async def receive_heartbeat(heartbeat: HeartbeatRequest):
    """Receive a heartbeat from a browser extension."""
    tracker = get_heartbeat_tracker()
    tracker.register_heartbeat(
        pid=heartbeat.pid,
        browser=heartbeat.browser,
        incognito=heartbeat.incognito
    )
    return HeartbeatResponse(status="ok")


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

    # Count active rules
    result = await session.execute(
        select(func.count(BlockRule.id)).where(BlockRule.enabled == True)
    )
    active_rules = result.scalar() or 0

    # Count active schedules
    result = await session.execute(
        select(func.count(Schedule.id)).where(Schedule.enabled == True)
    )
    active_schedules = result.scalar() or 0

    browser_statuses = tracker.get_all_browser_statuses()
    browsers_detected = len(browser_statuses)
    browsers_compliant = sum(1 for b in browser_statuses if b.get("compliant", False))

    return StatusResponse(
        running=True,
        locked=lock_status["locked"],
        lock_end_time=lock_status.get("lock_end_time"),
        active_rules=active_rules,
        active_schedules=active_schedules,
        browsers_detected=browsers_detected,
        browsers_compliant=browsers_compliant
    )


# Rules endpoints
@app.get("/api/rules", response_model=List[RuleResponse])
async def get_rules(session: AsyncSession = Depends(get_session)):
    """Get all blocking rules."""
    result = await session.execute(select(BlockRule))
    rules = result.scalars().all()
    return [
        RuleResponse(
            id=r.id,
            rule_type=r.rule_type,
            target=r.target,
            enabled=r.enabled,
            created_at=r.created_at.isoformat() if r.created_at else ""
        )
        for r in rules
    ]


@app.post("/api/rules", response_model=RuleResponse)
async def create_rule(rule: RuleCreate, session: AsyncSession = Depends(get_session)):
    """Create a new blocking rule."""
    await check_lock_mode()

    if rule.rule_type not in ('website', 'application'):
        raise HTTPException(status_code=400, detail="Invalid rule_type")

    db_rule = BlockRule(
        rule_type=rule.rule_type,
        target=rule.target,
        enabled=rule.enabled
    )
    session.add(db_rule)
    await session.commit()
    await session.refresh(db_rule)

    return RuleResponse(
        id=db_rule.id,
        rule_type=db_rule.rule_type,
        target=db_rule.target,
        enabled=db_rule.enabled,
        created_at=db_rule.created_at.isoformat() if db_rule.created_at else ""
    )


@app.put("/api/rules/{rule_id}", response_model=RuleResponse)
async def update_rule(rule_id: int, rule: RuleUpdate, session: AsyncSession = Depends(get_session)):
    """Update a blocking rule."""
    await check_lock_mode()

    result = await session.execute(select(BlockRule).where(BlockRule.id == rule_id))
    db_rule = result.scalar_one_or_none()

    if db_rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")

    if rule.rule_type is not None:
        if rule.rule_type not in ('website', 'application'):
            raise HTTPException(status_code=400, detail="Invalid rule_type")
        db_rule.rule_type = rule.rule_type

    if rule.target is not None:
        db_rule.target = rule.target

    if rule.enabled is not None:
        db_rule.enabled = rule.enabled

    await session.commit()
    await session.refresh(db_rule)

    return RuleResponse(
        id=db_rule.id,
        rule_type=db_rule.rule_type,
        target=db_rule.target,
        enabled=db_rule.enabled,
        created_at=db_rule.created_at.isoformat() if db_rule.created_at else ""
    )


@app.delete("/api/rules/{rule_id}")
async def delete_rule(rule_id: int, session: AsyncSession = Depends(get_session)):
    """Delete a blocking rule."""
    await check_lock_mode()

    result = await session.execute(select(BlockRule).where(BlockRule.id == rule_id))
    db_rule = result.scalar_one_or_none()

    if db_rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")

    await session.delete(db_rule)
    await session.commit()

    return {"status": "deleted"}


# Schedules endpoints
@app.get("/api/schedules", response_model=List[ScheduleResponse])
async def get_schedules(session: AsyncSession = Depends(get_session)):
    """Get all schedules."""
    result = await session.execute(
        select(Schedule).options(selectinload(Schedule.schedule_rules))
    )
    schedules = result.scalars().all()

    return [
        ScheduleResponse(
            id=s.id,
            name=s.name,
            schedule_type=s.schedule_type,
            days_of_week=s.days_of_week,
            start_time=s.start_time,
            end_time=s.end_time,
            locked_until=s.locked_until.isoformat() if s.locked_until else None,
            enabled=s.enabled,
            created_at=s.created_at.isoformat() if s.created_at else "",
            rule_ids=[sr.rule_id for sr in s.schedule_rules]
        )
        for s in schedules
    ]


@app.post("/api/schedules", response_model=ScheduleResponse)
async def create_schedule(schedule: ScheduleCreate, session: AsyncSession = Depends(get_session)):
    """Create a new schedule."""
    await check_lock_mode()

    if schedule.schedule_type not in ('time_range', 'locked_until'):
        raise HTTPException(status_code=400, detail="Invalid schedule_type")

    locked_until = None
    if schedule.locked_until:
        try:
            locked_until = datetime.fromisoformat(schedule.locked_until)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid locked_until datetime format")

    db_schedule = Schedule(
        name=schedule.name,
        schedule_type=schedule.schedule_type,
        days_of_week=schedule.days_of_week,
        start_time=schedule.start_time,
        end_time=schedule.end_time,
        locked_until=locked_until,
        enabled=schedule.enabled
    )
    session.add(db_schedule)
    await session.flush()

    # Add rule associations
    for rule_id in schedule.rule_ids:
        # Verify rule exists
        result = await session.execute(select(BlockRule).where(BlockRule.id == rule_id))
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=400, detail=f"Rule {rule_id} not found")

        schedule_rule = ScheduleRule(schedule_id=db_schedule.id, rule_id=rule_id)
        session.add(schedule_rule)

    await session.commit()
    await session.refresh(db_schedule)

    return ScheduleResponse(
        id=db_schedule.id,
        name=db_schedule.name,
        schedule_type=db_schedule.schedule_type,
        days_of_week=db_schedule.days_of_week,
        start_time=db_schedule.start_time,
        end_time=db_schedule.end_time,
        locked_until=db_schedule.locked_until.isoformat() if db_schedule.locked_until else None,
        enabled=db_schedule.enabled,
        created_at=db_schedule.created_at.isoformat() if db_schedule.created_at else "",
        rule_ids=schedule.rule_ids
    )


@app.put("/api/schedules/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: int,
    schedule: ScheduleUpdate,
    session: AsyncSession = Depends(get_session)
):
    """Update a schedule."""
    await check_lock_mode()

    result = await session.execute(
        select(Schedule).where(Schedule.id == schedule_id)
        .options(selectinload(Schedule.schedule_rules))
    )
    db_schedule = result.scalar_one_or_none()

    if db_schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")

    if schedule.name is not None:
        db_schedule.name = schedule.name

    if schedule.schedule_type is not None:
        if schedule.schedule_type not in ('time_range', 'locked_until'):
            raise HTTPException(status_code=400, detail="Invalid schedule_type")
        db_schedule.schedule_type = schedule.schedule_type

    if schedule.days_of_week is not None:
        db_schedule.days_of_week = schedule.days_of_week

    if schedule.start_time is not None:
        db_schedule.start_time = schedule.start_time

    if schedule.end_time is not None:
        db_schedule.end_time = schedule.end_time

    if schedule.locked_until is not None:
        try:
            db_schedule.locked_until = datetime.fromisoformat(schedule.locked_until)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid locked_until datetime format")

    if schedule.enabled is not None:
        db_schedule.enabled = schedule.enabled

    if schedule.rule_ids is not None:
        # Remove existing associations
        for sr in db_schedule.schedule_rules:
            await session.delete(sr)

        # Add new associations
        for rule_id in schedule.rule_ids:
            result = await session.execute(select(BlockRule).where(BlockRule.id == rule_id))
            if result.scalar_one_or_none() is None:
                raise HTTPException(status_code=400, detail=f"Rule {rule_id} not found")

            schedule_rule = ScheduleRule(schedule_id=db_schedule.id, rule_id=rule_id)
            session.add(schedule_rule)

    await session.commit()
    await session.refresh(db_schedule)

    # Re-fetch to get updated rule_ids
    result = await session.execute(
        select(Schedule).where(Schedule.id == schedule_id)
        .options(selectinload(Schedule.schedule_rules))
    )
    db_schedule = result.scalar_one()

    return ScheduleResponse(
        id=db_schedule.id,
        name=db_schedule.name,
        schedule_type=db_schedule.schedule_type,
        days_of_week=db_schedule.days_of_week,
        start_time=db_schedule.start_time,
        end_time=db_schedule.end_time,
        locked_until=db_schedule.locked_until.isoformat() if db_schedule.locked_until else None,
        enabled=db_schedule.enabled,
        created_at=db_schedule.created_at.isoformat() if db_schedule.created_at else "",
        rule_ids=[sr.rule_id for sr in db_schedule.schedule_rules]
    )


@app.delete("/api/schedules/{schedule_id}")
async def delete_schedule(schedule_id: int, session: AsyncSession = Depends(get_session)):
    """Delete a schedule."""
    await check_lock_mode()

    result = await session.execute(select(Schedule).where(Schedule.id == schedule_id))
    db_schedule = result.scalar_one_or_none()

    if db_schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")

    await session.delete(db_schedule)
    await session.commit()

    return {"status": "deleted"}


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
            incognito_active=s["incognito_active"]
        )
        for s in statuses
    ]
