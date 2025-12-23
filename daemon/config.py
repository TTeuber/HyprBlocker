"""Configuration management for the website blocker daemon."""

import json
import os
from dataclasses import dataclass, field
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class DaemonConfig:
    """Daemon server configuration."""
    host: str = "127.0.0.1"
    port: int = 8765
    log_level: str = "INFO"


@dataclass
class MonitoringConfig:
    """Monitoring intervals configuration."""
    check_interval_seconds: int = 5
    heartbeat_timeout_seconds: int = 60
    schedule_check_interval_seconds: int = 10


@dataclass
class SecurityConfig:
    """Security-related configuration."""
    ntp_servers: List[str] = field(default_factory=lambda: [
        "pool.ntp.org",
        "time.google.com",
        "time.cloudflare.com"
    ])
    max_time_diff_seconds: int = 300
    verify_time_on_transitions: bool = True
    dev_mode: bool = False  # Disable browser enforcement in dev mode


@dataclass
class Config:
    """Main configuration class."""
    daemon: DaemonConfig = field(default_factory=DaemonConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    browsers: List[str] = field(default_factory=lambda: [
        "firefox",
        "firefox-esr",
        "chromium",
        "google-chrome",
        "brave-browser",
        "microsoft-edge",
        "opera",
        "vivaldi-stable"
    ])


def get_config_path() -> str:
    """Get the path to the configuration file."""
    config_dir = os.path.expanduser("~/.config/website-blocker")
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, "config.json")


def load_config() -> Config:
    """Load configuration from file or create default."""
    config_path = get_config_path()

    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)

            config = Config(
                daemon=DaemonConfig(**data.get('daemon', {})),
                monitoring=MonitoringConfig(**data.get('monitoring', {})),
                security=SecurityConfig(**data.get('security', {})),
                browsers=data.get('browsers', Config().browsers)
            )
            logger.info(f"Loaded configuration from {config_path}")
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.error(f"Failed to load config: {e}. Using defaults (fail-safe).")
            config = Config()
    else:
        # Create default config file
        config = Config()
        save_config(config)
        logger.info(f"Created default configuration at {config_path}")

    # Check for dev mode environment variable (overrides config file)
    dev_mode_env = os.getenv('BLOCKER_DEV_MODE', 'false').lower()
    if dev_mode_env in ('true', '1', 'yes'):
        config.security.dev_mode = True
        logger.warning("🚨 DEV MODE ENABLED via environment variable - Browser enforcement disabled!")
    elif config.security.dev_mode:
        logger.warning("🚨 DEV MODE ENABLED via config file - Browser enforcement disabled!")

    return config


def save_config(config: Config) -> None:
    """Save configuration to file."""
    config_path = get_config_path()

    data = {
        "daemon": {
            "host": config.daemon.host,
            "port": config.daemon.port,
            "log_level": config.daemon.log_level
        },
        "monitoring": {
            "check_interval_seconds": config.monitoring.check_interval_seconds,
            "heartbeat_timeout_seconds": config.monitoring.heartbeat_timeout_seconds,
            "schedule_check_interval_seconds": config.monitoring.schedule_check_interval_seconds
        },
        "security": {
            "ntp_servers": config.security.ntp_servers,
            "max_time_diff_seconds": config.security.max_time_diff_seconds,
            "verify_time_on_transitions": config.security.verify_time_on_transitions,
            "dev_mode": config.security.dev_mode
        },
        "browsers": config.browsers
    }

    with open(config_path, 'w') as f:
        json.dump(data, f, indent=4)


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config() -> Config:
    """Reload configuration from file."""
    global _config
    _config = load_config()
    return _config
