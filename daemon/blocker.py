"""Core blocking logic for the website blocker daemon."""

import fnmatch
import logging
import sys
import os
from typing import List, Optional

# Add daemon directory to Python path for absolute imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scheduler import get_scheduler

logger = logging.getLogger(__name__)


def parse_rules_from_text(text: Optional[str]) -> List[str]:
    """Parse newline-separated rules from text field."""
    if not text:
        return []
    return [line.strip() for line in text.split('\n') if line.strip()]


class SiteBlocker:
    """Handles website blocking logic and pattern matching."""

    @staticmethod
    def url_matches_pattern(url: str, pattern: str) -> bool:
        """Check if URL matches blocking pattern.

        Supports:
        - Domain matching: reddit.com matches www.reddit.com and reddit.com/anything
        - Path-specific: youtube.com/shorts only matches that specific path
        - Wildcard subdomains: *.reddit.com matches all subdomains

        Args:
            url: The URL to check (can include path)
            pattern: The blocking pattern

        Returns:
            bool: True if URL matches the pattern
        """
        # Remove protocol if present
        url = url.split('://')[-1] if '://' in url else url
        pattern = pattern.split('://')[-1] if '://' in pattern else pattern

        url = url.lower().strip()
        pattern = pattern.lower().strip()

        # Handle wildcard subdomains
        if pattern.startswith('*.'):
            base_domain = pattern[2:]
            url_domain = url.split('/')[0]
            return url_domain == base_domain or url_domain.endswith('.' + base_domain)

        # Check if pattern includes path
        if '/' in pattern:
            # Path-specific matching - URL must match exactly or be a subpath
            return url.startswith(pattern)
        else:
            # Domain-only pattern - match domain and all subpaths
            url_domain = url.split('/')[0]
            return url_domain == pattern or url.startswith(pattern + '/')

    def should_block_url(self, url: str, blocked: List[str], allowed: List[str]) -> bool:
        """Check if URL should be blocked.

        Allow list takes precedence over block list.

        Args:
            url: The URL to check
            blocked: List of blocked patterns
            allowed: List of allowed patterns

        Returns:
            bool: True if URL should be blocked
        """
        # Check if explicitly allowed
        for allow_pattern in allowed:
            if self.url_matches_pattern(url, allow_pattern):
                logger.debug(f"URL {url} explicitly allowed by pattern {allow_pattern}")
                return False  # Allowed, don't block

        # Check if blocked
        for block_pattern in blocked:
            if self.url_matches_pattern(url, block_pattern):
                logger.debug(f"URL {url} blocked by pattern {block_pattern}")
                return True  # Blocked

        return False  # Not in any list, don't block

    async def is_site_blocked(self, url: str) -> bool:
        """Check if a site is blocked using intersection-based allow logic.

        A URL is allowed only if:
        1. No active blocks would block it, OR
        2. It appears in the allow list of EVERY block that would block it

        Args:
            url: The URL to check (hostname or full URL)

        Returns:
            bool: True if blocked, False otherwise
        """
        scheduler = get_scheduler()
        if scheduler is None:
            return False

        active_blocks = await scheduler.get_active_blocks()

        # Find all blocks that would block this URL (ignoring allow lists)
        blocking_blocks = []

        for block in active_blocks:
            blocked_patterns = parse_rules_from_text(block.websites_blocked)

            # Check if this block's block patterns match the URL
            for pattern in blocked_patterns:
                if self.url_matches_pattern(url, pattern):
                    blocking_blocks.append(block)
                    break  # This block would block it, move to next block

        # If no blocks would block this URL, it's allowed
        if not blocking_blocks:
            logger.debug(f"URL {url} not blocked by any block")
            return False

        # Check if URL is in the allow list of EVERY blocking block
        for block in blocking_blocks:
            allowed_patterns = parse_rules_from_text(block.websites_allowed)

            # Check if this block's allow list contains the URL
            url_allowed_by_this_block = False
            for pattern in allowed_patterns:
                if self.url_matches_pattern(url, pattern):
                    url_allowed_by_this_block = True
                    break

            # If this blocking block doesn't allow the URL, it's blocked
            if not url_allowed_by_this_block:
                logger.debug(f"URL {url} blocked by block {block.id} ({block.name}) - not in allow list")
                return True

        # URL is in the allow list of ALL blocking blocks
        logger.debug(f"URL {url} allowed by all {len(blocking_blocks)} blocking blocks")
        return False

    async def get_blocked_sites(self) -> List[str]:
        """Get list of all currently blocked site patterns.

        Returns:
            List of blocked site patterns
        """
        scheduler = get_scheduler()
        if scheduler is None:
            return []

        active_blocks = await scheduler.get_active_blocks()
        all_blocked = []

        for block in active_blocks:
            all_blocked.extend(parse_rules_from_text(block.websites_blocked))

        return all_blocked


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

    def should_block_app(self, app_class: str, blocked: List[str], allowed: List[str]) -> bool:
        """Check if app should be blocked.

        Allow list takes precedence over block list.

        Args:
            app_class: The application window class
            blocked: List of blocked patterns
            allowed: List of allowed patterns

        Returns:
            bool: True if app should be blocked
        """
        # Check if explicitly allowed
        for allow_pattern in allowed:
            if self.matches_pattern(app_class, allow_pattern):
                logger.debug(f"App {app_class} explicitly allowed by pattern {allow_pattern}")
                return False  # Allowed, don't block

        # Check if blocked
        for block_pattern in blocked:
            if self.matches_pattern(app_class, block_pattern):
                logger.debug(f"App {app_class} blocked by pattern {block_pattern}")
                return True  # Blocked

        return False  # Not in any list, don't block

    async def is_app_blocked(self, app_class: str) -> bool:
        """Check if an application is blocked.

        An app is blocked if ANY active block has it in apps_blocked.

        Args:
            app_class: The application window class

        Returns:
            bool: True if blocked, False otherwise
        """
        scheduler = get_scheduler()
        if scheduler is None:
            return False

        active_blocks = await scheduler.get_active_blocks()

        for block in active_blocks:
            blocked_patterns = parse_rules_from_text(block.apps_blocked)

            for pattern in blocked_patterns:
                if self.matches_pattern(app_class, pattern):
                    logger.debug(f"App {app_class} blocked by block {block.id} ({block.name})")
                    return True

        logger.debug(f"App {app_class} not blocked by any block")
        return False

    async def get_blocked_apps(self) -> List[str]:
        """Get list of all currently blocked application patterns.

        Returns:
            List of blocked app patterns
        """
        scheduler = get_scheduler()
        if scheduler is None:
            return []

        active_blocks = await scheduler.get_active_blocks()
        all_blocked = []

        for block in active_blocks:
            all_blocked.extend(parse_rules_from_text(block.apps_blocked))

        return all_blocked


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
