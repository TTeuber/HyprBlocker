"""Core blocking logic for the website blocker daemon."""

import fnmatch
import logging
from typing import List, Optional

from scheduler import get_scheduler
from database import BlockRule

logger = logging.getLogger(__name__)


class SiteBlocker:
    """Handles website blocking logic and pattern matching."""

    @staticmethod
    def matches_pattern(hostname: str, pattern: str) -> bool:
        """Check if a hostname matches a blocking pattern.

        Supports:
        - Exact match: 'reddit.com' matches 'reddit.com'
        - Wildcard subdomain: '*.example.com' matches 'www.example.com', 'api.example.com'
        - Subdomain match: 'example.com' matches 'www.example.com'

        Args:
            hostname: The hostname to check
            pattern: The blocking pattern

        Returns:
            bool: True if the hostname matches the pattern
        """
        hostname = hostname.lower().strip()
        pattern = pattern.lower().strip()

        # Remove any protocol prefix from pattern if present
        if pattern.startswith("http://"):
            pattern = pattern[7:]
        elif pattern.startswith("https://"):
            pattern = pattern[8:]

        # Remove trailing slash
        pattern = pattern.rstrip("/")

        # Remove path if present (we only match hostname)
        if "/" in pattern:
            pattern = pattern.split("/")[0]

        # Exact match
        if hostname == pattern:
            return True

        # Wildcard subdomain (*.example.com)
        if pattern.startswith("*."):
            domain = pattern[2:]
            return hostname == domain or hostname.endswith("." + domain)

        # Subdomain match (example.com matches www.example.com)
        if hostname.endswith("." + pattern):
            return True

        # Glob pattern matching for more complex patterns
        if "*" in pattern or "?" in pattern:
            return fnmatch.fnmatch(hostname, pattern)

        return False

    async def is_site_blocked(self, hostname: str) -> Optional[BlockRule]:
        """Check if a site is blocked.

        Args:
            hostname: The hostname to check

        Returns:
            BlockRule if blocked, None otherwise
        """
        scheduler = get_scheduler()
        if scheduler is None:
            return None

        active_rules = await scheduler.get_active_website_rules()

        for rule in active_rules:
            if self.matches_pattern(hostname, rule.target):
                logger.debug(f"Site {hostname} blocked by rule {rule.id}: {rule.target}")
                return rule

        return None

    async def get_blocked_sites(self) -> List[str]:
        """Get list of all currently blocked site patterns.

        Returns:
            List of blocked site patterns
        """
        scheduler = get_scheduler()
        if scheduler is None:
            return []

        active_rules = await scheduler.get_active_website_rules()
        return [rule.target for rule in active_rules]


class AppBlocker:
    """Handles application blocking logic and pattern matching."""

    @staticmethod
    def matches_pattern(app_class: str, pattern: str) -> bool:
        """Check if an application class matches a blocking pattern.

        Args:
            app_class: The application window class
            pattern: The blocking pattern

        Returns:
            bool: True if the app matches the pattern
        """
        app_class = app_class.lower().strip()
        pattern = pattern.lower().strip()

        # Exact match
        if app_class == pattern:
            return True

        # Partial match
        if pattern in app_class:
            return True

        # Glob pattern matching
        if "*" in pattern or "?" in pattern:
            return fnmatch.fnmatch(app_class, pattern)

        return False

    async def is_app_blocked(self, app_class: str) -> Optional[BlockRule]:
        """Check if an application is blocked.

        Args:
            app_class: The application window class

        Returns:
            BlockRule if blocked, None otherwise
        """
        scheduler = get_scheduler()
        if scheduler is None:
            return None

        active_rules = await scheduler.get_active_app_rules()

        for rule in active_rules:
            if self.matches_pattern(app_class, rule.target):
                logger.debug(f"App {app_class} blocked by rule {rule.id}: {rule.target}")
                return rule

        return None

    async def get_blocked_apps(self) -> List[str]:
        """Get list of all currently blocked application patterns.

        Returns:
            List of blocked app patterns
        """
        scheduler = get_scheduler()
        if scheduler is None:
            return []

        active_rules = await scheduler.get_active_app_rules()
        return [rule.target for rule in active_rules]


# Global blocker instances
_site_blocker: Optional[SiteBlocker] = None
_app_blocker: Optional[AppBlocker] = None


def get_site_blocker() -> SiteBlocker:
    """Get the global site blocker instance."""
    global _site_blocker
    if _site_blocker is None:
        _site_blocker = SiteBlocker()
    return _site_blocker


def get_app_blocker() -> AppBlocker:
    """Get the global app blocker instance."""
    global _app_blocker
    if _app_blocker is None:
        _app_blocker = AppBlocker()
    return _app_blocker
