"""Database models and setup for the website blocker daemon."""

from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker
from sqlalchemy.ext.asyncio import async_sessionmaker
import os
import logging

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass




class Block(Base):
    """A block configuration with separate blocking and locking schedules.

    block_mode determines when content is blocked:
    - 'always': content is always blocked
    - 'time_range': blocked during specific days/times
    - 'disabled': not blocking (rules inactive)

    lock_mode determines when configuration is locked:
    - 'none': config can be changed anytime
    - 'time_range': config locked during specific days/times
    - 'locked_until': config locked until specific datetime
    """

    __tablename__ = "blocks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)

    # Block mode: when content is blocked
    block_mode = Column(
        String(20), nullable=False, default="always"
    )  # 'always', 'time_range', 'disabled'
    block_days_of_week = Column(
        Text, nullable=True
    )  # JSON: [0,1,2,3,4] (0=Monday, 6=Sunday)
    block_start_time = Column(String(10), nullable=True)  # "09:00"
    block_end_time = Column(String(10), nullable=True)  # "17:00"

    # Lock mode: when configuration is locked
    lock_mode = Column(
        String(20), nullable=False, default="none"
    )  # 'none', 'time_range', 'locked_until'
    lock_days_of_week = Column(Text, nullable=True)  # JSON: [0,1,2,3,4]
    lock_start_time = Column(String(10), nullable=True)  # "09:00"
    lock_end_time = Column(String(10), nullable=True)  # "17:00"
    lock_until = Column(DateTime, nullable=True)  # For 'locked_until' mode

    # Rule storage as text fields (newline-separated)
    websites_blocked = Column(Text, nullable=True)  # Newline-separated list
    websites_allowed = Column(Text, nullable=True)  # Newline-separated allow list
    apps_blocked = Column(Text, nullable=True)      # Newline-separated list
    apps_allowed = Column(Text, nullable=True)      # Newline-separated allow list

    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "block_mode": self.block_mode,
            "block_days_of_week": self.block_days_of_week,
            "block_start_time": self.block_start_time,
            "block_end_time": self.block_end_time,
            "lock_mode": self.lock_mode,
            "lock_days_of_week": self.lock_days_of_week,
            "lock_start_time": self.lock_start_time,
            "lock_end_time": self.lock_end_time,
            "lock_until": self.lock_until.isoformat() if self.lock_until else None,
            "websites_blocked": self.websites_blocked,
            "websites_allowed": self.websites_allowed,
            "apps_blocked": self.apps_blocked,
            "apps_allowed": self.apps_allowed,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }



class BlockEvent(Base):
    """Log of blocking events."""

    __tablename__ = "block_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, nullable=True)  # Legacy field, no longer used
    blocked_target = Column(String(500), nullable=False)  # What was blocked
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    event_type = Column(
        String(50), nullable=False
    )  # 'website_blocked', 'app_closed', 'browser_killed'


class HeartbeatLog(Base):
    """Log of browser extension heartbeats."""

    __tablename__ = "heartbeat_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    browser_pid = Column(Integer, nullable=False)
    browser_name = Column(String(50), nullable=False)
    incognito = Column(Boolean, default=False, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)


def get_database_path() -> str:
    """Get the path to the SQLite database file."""
    config_dir = os.path.expanduser("~/.config/website-blocker")
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, "blocker.db")


def get_database_url() -> str:
    """Get the async SQLite database URL."""
    return f"sqlite+aiosqlite:///{get_database_path()}"


async def init_database():
    """Initialize the database and create all tables."""
    from migrations import migrate_schedules_to_blocks, migrate_rules_to_text_fields

    engine = create_async_engine(get_database_url(), echo=False)

    async with engine.begin() as conn:
        # Run migrations first (check for old schema and migrate)
        async with AsyncSession(conn) as session:
            try:
                await migrate_schedules_to_blocks(session)
                await migrate_rules_to_text_fields(session)
            except Exception as e:
                logger.warning(f"Migration check failed (may be first run): {e}")

        # Create any new tables that don't exist
        await conn.run_sync(Base.metadata.create_all)

    return engine


def create_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory."""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
