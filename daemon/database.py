"""Database models and setup for the website blocker daemon."""

from datetime import datetime
from typing import List, Optional
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker
from sqlalchemy.ext.asyncio import async_sessionmaker
import os


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


class BlockRule(Base):
    """A rule for blocking a website or application."""
    __tablename__ = 'block_rules'

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_type = Column(String(20), nullable=False)  # 'website' or 'application'
    target = Column(String(500), nullable=False)  # URL pattern or app class name
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship to schedule associations
    schedule_rules = relationship("ScheduleRule", back_populates="rule", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "rule_type": self.rule_type,
            "target": self.target,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class Schedule(Base):
    """A schedule that determines when blocking rules are active."""
    __tablename__ = 'schedules'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    schedule_type = Column(String(20), nullable=False)  # 'time_range' or 'locked_until'

    # TIME_RANGE fields
    days_of_week = Column(Text, nullable=True)  # JSON: [0,1,2,3,4] (0=Monday, 6=Sunday)
    start_time = Column(String(10), nullable=True)  # "09:00"
    end_time = Column(String(10), nullable=True)  # "17:00"

    # LOCKED_UNTIL fields
    locked_until = Column(DateTime, nullable=True)  # Absolute timestamp

    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship to rule associations
    schedule_rules = relationship("ScheduleRule", back_populates="schedule", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "schedule_type": self.schedule_type,
            "days_of_week": self.days_of_week,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "locked_until": self.locked_until.isoformat() if self.locked_until else None,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "rule_ids": [sr.rule_id for sr in self.schedule_rules]
        }


class ScheduleRule(Base):
    """Association between schedules and blocking rules."""
    __tablename__ = 'schedule_rules'

    id = Column(Integer, primary_key=True, autoincrement=True)
    schedule_id = Column(Integer, ForeignKey('schedules.id'), nullable=False)
    rule_id = Column(Integer, ForeignKey('block_rules.id'), nullable=False)

    schedule = relationship("Schedule", back_populates="schedule_rules")
    rule = relationship("BlockRule", back_populates="schedule_rules")


class BlockEvent(Base):
    """Log of blocking events."""
    __tablename__ = 'block_events'

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, ForeignKey('block_rules.id'), nullable=True)
    blocked_target = Column(String(500), nullable=False)  # What was blocked
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    event_type = Column(String(50), nullable=False)  # 'website_blocked', 'app_closed', 'browser_killed'


class HeartbeatLog(Base):
    """Log of browser extension heartbeats."""
    __tablename__ = 'heartbeat_logs'

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
    engine = create_async_engine(get_database_url(), echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


def create_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory."""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
