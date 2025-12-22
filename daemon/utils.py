"""Utility functions for the website blocker daemon."""

import os
import subprocess
from typing import Optional


def show_notification(title: str, message: str, urgency: str = "normal") -> bool:
    """Show a desktop notification.

    Args:
        title: Notification title
        message: Notification message
        urgency: Notification urgency (low, normal, critical)

    Returns:
        bool: True if notification was sent successfully
    """
    try:
        subprocess.run(
            ["notify-send", "-u", urgency, title, message],
            capture_output=True,
            timeout=5
        )
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def get_xdg_config_dir() -> str:
    """Get the XDG config directory.

    Returns:
        Path to the config directory
    """
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return os.path.join(xdg_config, "website-blocker")
    return os.path.expanduser("~/.config/website-blocker")


def get_xdg_data_dir() -> str:
    """Get the XDG data directory.

    Returns:
        Path to the data directory
    """
    xdg_data = os.environ.get("XDG_DATA_HOME")
    if xdg_data:
        return os.path.join(xdg_data, "website-blocker")
    return os.path.expanduser("~/.local/share/website-blocker")


def ensure_directories() -> None:
    """Ensure all required directories exist."""
    directories = [
        get_xdg_config_dir(),
        get_xdg_data_dir(),
    ]
    for directory in directories:
        os.makedirs(directory, exist_ok=True)


def format_duration(seconds: int) -> str:
    """Format a duration in seconds to a human-readable string.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted string like "2h 30m" or "45m 10s"
    """
    if seconds < 60:
        return f"{seconds}s"

    minutes = seconds // 60
    remaining_seconds = seconds % 60

    if minutes < 60:
        if remaining_seconds > 0:
            return f"{minutes}m {remaining_seconds}s"
        return f"{minutes}m"

    hours = minutes // 60
    remaining_minutes = minutes % 60

    if hours < 24:
        if remaining_minutes > 0:
            return f"{hours}h {remaining_minutes}m"
        return f"{hours}h"

    days = hours // 24
    remaining_hours = hours % 24

    if remaining_hours > 0:
        return f"{days}d {remaining_hours}h"
    return f"{days}d"
