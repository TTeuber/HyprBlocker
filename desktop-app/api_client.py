"""API client for communicating with the Website Blocker daemon."""

import requests
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class Block:
    """Represents a block configuration."""
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
    enabled: bool
    created_at: str
    websites_blocked: Optional[str]
    websites_allowed: Optional[str]
    apps_blocked: Optional[str]
    apps_allowed: Optional[str]


@dataclass
class DaemonStatus:
    """Represents the daemon status."""
    running: bool
    locked: bool
    lock_end_time: Optional[str]
    active_rules: int
    active_blocks: int
    browsers_detected: int
    browsers_compliant: int


@dataclass
class Stats:
    """Represents blocking statistics."""
    total_blocks_today: int
    total_blocks_week: int
    total_blocks_month: int
    websites_blocked_today: int
    apps_closed_today: int
    browsers_killed_today: int


@dataclass
class BrowserStatus:
    """Represents a browser's status."""
    pid: int
    browser: str
    compliant: bool
    last_heartbeat: str
    incognito_active: bool
    incognito_enabled: bool


@dataclass
class GracePeriodStatus:
    """Represents grace period status."""
    active: bool
    expires_at: Optional[str]
    remaining_seconds: Optional[int]


@dataclass
class BrowserEnforcementStatus:
    """Represents browser enforcement status."""
    enabled: bool
    source: str  # 'config' or 'default'


@dataclass
class WatchdogStatus:
    """Represents watchdog status."""
    enabled: bool
    count: int
    active_watchdogs: list  # [{pid, name, uptime_seconds}]


@dataclass
class SettingsLockStatus:
    """Represents settings lock status."""
    locked: bool
    lock_until: Optional[str]
    remaining_seconds: Optional[int]


class DaemonClient:
    """Client for the Website Blocker daemon API."""

    def __init__(self, base_url: str = "http://127.0.0.1:8765"):
        """Initialize the client.

        Args:
            base_url: Base URL of the daemon API
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = 5

    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make an HTTP request to the daemon.

        Args:
            method: HTTP method
            endpoint: API endpoint
            **kwargs: Additional arguments for requests

        Returns:
            Response object
        """
        url = f"{self.base_url}{endpoint}"
        kwargs.setdefault('timeout', self.timeout)
        return requests.request(method, url, **kwargs)

    def is_daemon_running(self) -> bool:
        """Check if the daemon is reachable.

        Returns:
            True if daemon is running and reachable
        """
        try:
            response = self._request('GET', '/api/status')
            return response.status_code == 200
        except requests.RequestException:
            return False

    def get_status(self) -> Optional[DaemonStatus]:
        """Get the daemon status.

        Returns:
            DaemonStatus object or None if unreachable
        """
        try:
            response = self._request('GET', '/api/status')
            if response.status_code == 200:
                data = response.json()
                return DaemonStatus(**data)
        except requests.RequestException:
            pass
        return None

    def get_blocks(self) -> List[Block]:
        """Get all blocks.

        Returns:
            List of Block objects
        """
        try:
            response = self._request('GET', '/api/blocks')
            if response.status_code == 200:
                return [Block(**b) for b in response.json()]
        except requests.RequestException:
            pass
        return []

    def add_block(self, name: str, block_mode: str = 'always', lock_mode: str = 'none', **kwargs) -> Optional[Block]:
        """Add a new block.

        Args:
            name: Block name
            block_mode: 'always', 'time_range', or 'disabled'
            lock_mode: 'none', 'time_range', or 'locked_until'
            **kwargs: Additional block fields

        Returns:
            Created Block or None if failed
        """
        try:
            data = {
                'name': name,
                'block_mode': block_mode,
                'lock_mode': lock_mode,
                **kwargs
            }
            response = self._request('POST', '/api/blocks', json=data)
            if response.status_code == 200:
                return Block(**response.json())
            elif response.status_code == 403:
                raise PermissionError("Cannot modify blocks during lock period")
        except requests.RequestException:
            pass
        return None

    def update_block(self, block_id: int, **updates) -> Optional[Block]:
        """Update a block.

        Args:
            block_id: Block ID to update
            **updates: Fields to update

        Returns:
            Updated Block or None if failed
        """
        try:
            print(f"\n[API Client] update_block called:")
            print(f"  URL: {self.base_url}/api/blocks/{block_id}")
            print(f"  Method: PUT")
            print(f"  Data: {updates}")

            response = self._request('PUT', f'/api/blocks/{block_id}', json=updates)

            print(f"[API Client] Response status: {response.status_code}")
            print(f"[API Client] Response body: {response.text[:500]}")  # First 500 chars

            if response.status_code == 200:
                return Block(**response.json())
            elif response.status_code == 403:
                raise PermissionError("Cannot modify blocks during lock period")
            else:
                print(f"[API Client] Unexpected status code: {response.status_code}")
        except requests.RequestException as e:
            print(f"[API Client] RequestException: {e}")
            import traceback
            traceback.print_exc()
        return None

    def delete_block(self, block_id: int) -> bool:
        """Delete a block.

        Args:
            block_id: Block ID to delete

        Returns:
            True if deleted successfully
        """
        try:
            response = self._request('DELETE', f'/api/blocks/{block_id}')
            if response.status_code == 200:
                return True
            elif response.status_code == 403:
                raise PermissionError("Cannot modify blocks during lock period")
        except requests.RequestException:
            pass
        return False

    def get_block_lock_status(self, block_id: int) -> dict:
        """Get lock status for a specific block.

        Args:
            block_id: Block ID to check

        Returns:
            Dict with 'locked' key indicating lock status
        """
        try:
            response = self._request('GET', f'/api/blocks/{block_id}/lock-status')
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Failed to get block lock status: {response.text}")
        except requests.RequestException as e:
            raise Exception(f"Request failed: {str(e)}")

    def get_stats(self) -> Optional[Stats]:
        """Get blocking statistics.

        Returns:
            Stats object or None if unreachable
        """
        try:
            response = self._request('GET', '/api/stats')
            if response.status_code == 200:
                return Stats(**response.json())
        except requests.RequestException:
            pass
        return None

    def get_browsers(self) -> List[BrowserStatus]:
        """Get detected browsers and their status.

        Returns:
            List of BrowserStatus objects
        """
        try:
            response = self._request('GET', '/api/browsers')
            if response.status_code == 200:
                return [BrowserStatus(**b) for b in response.json()]
        except requests.RequestException:
            pass
        return []

    def start_grace_period(self) -> Optional[GracePeriodStatus]:
        """Start a grace period for adding browser extensions.

        Returns:
            GracePeriodStatus or None if failed
        """
        try:
            response = self._request('POST', '/api/grace-period')
            if response.status_code == 200:
                return GracePeriodStatus(**response.json())
        except requests.RequestException:
            pass
        return None

    def get_grace_period_status(self) -> Optional[GracePeriodStatus]:
        """Get the current grace period status.

        Returns:
            GracePeriodStatus or None if failed
        """
        try:
            response = self._request('GET', '/api/grace-period')
            if response.status_code == 200:
                return GracePeriodStatus(**response.json())
        except requests.RequestException:
            pass
        return None

    def get_browser_enforcement_status(self) -> Optional[BrowserEnforcementStatus]:
        """Get browser enforcement status.

        Returns:
            BrowserEnforcementStatus or None if failed
        """
        try:
            response = self._request('GET', '/api/settings/browser-enforcement')
            if response.status_code == 200:
                return BrowserEnforcementStatus(**response.json())
        except requests.RequestException:
            pass
        return None

    def update_browser_enforcement(self, enabled: bool) -> dict:
        """Update browser enforcement setting.

        Args:
            enabled: Whether to enable browser enforcement

        Returns:
            Dict with success status

        Raises:
            PermissionError: If settings are locked
        """
        try:
            response = self._request('PUT', '/api/settings/browser-enforcement', json={'enabled': enabled})
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 403:
                raise PermissionError("Settings are locked and cannot be changed")
            else:
                raise Exception(f"Failed to update browser enforcement: {response.text}")
        except requests.RequestException as e:
            raise Exception(f"Request failed: {str(e)}")

    def get_watchdog_status(self) -> Optional[WatchdogStatus]:
        """Get watchdog status.

        Returns:
            WatchdogStatus or None if failed
        """
        try:
            response = self._request('GET', '/api/settings/watchdog')
            if response.status_code == 200:
                return WatchdogStatus(**response.json())
        except requests.RequestException:
            pass
        return None

    def update_watchdog(self, enabled: Optional[bool] = None, count: Optional[int] = None) -> dict:
        """Update watchdog settings.

        Args:
            enabled: Whether to enable watchdog
            count: Number of watchdog processes

        Returns:
            Dict with success status

        Raises:
            PermissionError: If settings are locked
        """
        try:
            data = {}
            if enabled is not None:
                data['enabled'] = enabled
            if count is not None:
                data['count'] = count

            response = self._request('PUT', '/api/settings/watchdog', json=data)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 403:
                raise PermissionError("Settings are locked and cannot be changed")
            else:
                raise Exception(f"Failed to update watchdog: {response.text}")
        except requests.RequestException as e:
            raise Exception(f"Request failed: {str(e)}")

    def get_settings_lock(self) -> Optional[SettingsLockStatus]:
        """Get settings lock status.

        Returns:
            SettingsLockStatus or None if failed
        """
        try:
            response = self._request('GET', '/api/settings/lock')
            if response.status_code == 200:
                return SettingsLockStatus(**response.json())
        except requests.RequestException:
            pass
        return None

    def lock_settings(self, lock_until: str) -> dict:
        """Lock settings until a specific datetime.

        Args:
            lock_until: ISO datetime string

        Returns:
            Dict with success status
        """
        try:
            response = self._request('POST', '/api/settings/lock', json={'lock_until': lock_until})
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 403:
                raise PermissionError("System time appears to be manipulated")
            else:
                raise Exception(f"Failed to lock settings: {response.text}")
        except requests.RequestException as e:
            raise Exception(f"Request failed: {str(e)}")

    def unlock_settings(self) -> dict:
        """Unlock settings.

        Returns:
            Dict with success status

        Raises:
            PermissionError: If lock has not expired
        """
        try:
            response = self._request('DELETE', '/api/settings/lock')
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 403:
                raise PermissionError("Settings are still locked")
            else:
                raise Exception(f"Failed to unlock settings: {response.text}")
        except requests.RequestException as e:
            raise Exception(f"Request failed: {str(e)}")
