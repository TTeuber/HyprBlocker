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
    browser_enforcement_enabled: bool = True  # Enable browser enforcement
    safe_search_enabled: bool = False  # Enable safe search enforcement on search engines
    shutdown_prevention_enabled: bool = False  # Prevent daemon from being stopped via SIGTERM
    watchdog_enabled: bool = False  # Enable watchdog processes for resilience
    watchdog_count: int = 3  # Number of watchdog processes (2-5)
    settings_lock_until: Optional[str] = None  # ISO datetime string when settings lock expires


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

            # Migrate old dev_mode to browser_enforcement_enabled
            security_data = data.get('security', {})
            if 'dev_mode' in security_data and 'browser_enforcement_enabled' not in security_data:
                # Invert: dev_mode=False meant enforcement ON → browser_enforcement_enabled=True
                security_data['browser_enforcement_enabled'] = not security_data.pop('dev_mode')
                logger.info("Migrated dev_mode to browser_enforcement_enabled")
            elif 'dev_mode' in security_data:
                # Remove old field if both exist
                del security_data['dev_mode']

            config = Config(
                daemon=DaemonConfig(**data.get('daemon', {})),
                monitoring=MonitoringConfig(**data.get('monitoring', {})),
                security=SecurityConfig(**security_data),
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
            "browser_enforcement_enabled": config.security.browser_enforcement_enabled,
            "safe_search_enabled": config.security.safe_search_enabled,
            "shutdown_prevention_enabled": config.security.shutdown_prevention_enabled,
            "watchdog_enabled": config.security.watchdog_enabled,
            "watchdog_count": config.security.watchdog_count,
            "settings_lock_until": config.security.settings_lock_until
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
