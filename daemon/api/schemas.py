"""Pydantic models for the website blocker API."""

from typing import List, Optional
from pydantic import BaseModel


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
    lock_mode: str = 'none'  # 'none', 'locked_until'
    lock_until: Optional[str] = None  # ISO format datetime
    enabled: bool = True
    websites_blocked: Optional[str] = None  # Newline-separated list
    websites_allowed: Optional[str] = None  # Newline-separated allow list
    apps_blocked: Optional[str] = None      # Newline-separated list


class BlockUpdate(BaseModel):
    name: Optional[str] = None
    block_mode: Optional[str] = None
    block_days_of_week: Optional[str] = None
    block_start_time: Optional[str] = None
    block_end_time: Optional[str] = None
    lock_mode: Optional[str] = None
    lock_until: Optional[str] = None
    enabled: Optional[bool] = None
    websites_blocked: Optional[str] = None
    websites_allowed: Optional[str] = None
    apps_blocked: Optional[str] = None


class BlockStrictUpdate(BaseModel):
    """Update a block with stricter rules only (allowed even when locked).

    These operations make the block more restrictive:
    - Adding items to blocked lists
    - Removing items from allowed lists
    """
    websites_blocked_add: Optional[str] = None      # Newline-separated items to ADD to blocked
    apps_blocked_add: Optional[str] = None          # Newline-separated items to ADD to blocked
    websites_allowed_remove: Optional[str] = None   # Newline-separated items to REMOVE from allowed


class BlockResponse(BaseModel):
    id: int
    name: str
    block_mode: str
    block_days_of_week: Optional[str]
    block_start_time: Optional[str]
    block_end_time: Optional[str]
    lock_mode: str
    lock_until: Optional[str]
    websites_blocked: Optional[str]
    websites_allowed: Optional[str]
    apps_blocked: Optional[str]
    enabled: bool
    created_at: str

    class Config:
        from_attributes = True


class StatusResponse(BaseModel):
    running: bool
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


class BrowserEnforcementStatusResponse(BaseModel):
    enabled: bool
    source: str  # 'config' or 'default'


class BrowserEnforcementUpdateRequest(BaseModel):
    enabled: bool


class SafeSearchStatusResponse(BaseModel):
    enabled: bool
    source: str  # 'config' or 'default'


class SafeSearchUpdateRequest(BaseModel):
    enabled: bool


class ShutdownPreventionStatusResponse(BaseModel):
    enabled: bool
    source: str  # 'config' or 'default'


class ShutdownPreventionUpdateRequest(BaseModel):
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
