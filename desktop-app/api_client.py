"""API client for communicating with the Website Blocker daemon."""

import requests
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class BlockRule:
    """Represents a blocking rule."""
    id: int
    rule_type: str
    target: str
    enabled: bool
    created_at: str


@dataclass
class Schedule:
    """Represents a schedule."""
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


@dataclass
class DaemonStatus:
    """Represents the daemon status."""
    running: bool
    locked: bool
    lock_end_time: Optional[str]
    active_rules: int
    active_schedules: int
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

    def get_rules(self) -> List[BlockRule]:
        """Get all blocking rules.

        Returns:
            List of BlockRule objects
        """
        try:
            response = self._request('GET', '/api/rules')
            if response.status_code == 200:
                return [BlockRule(**r) for r in response.json()]
        except requests.RequestException:
            pass
        return []

    def add_rule(self, rule_type: str, target: str, enabled: bool = True) -> Optional[BlockRule]:
        """Add a new blocking rule.

        Args:
            rule_type: 'website' or 'application'
            target: URL pattern or app class name
            enabled: Whether the rule is enabled

        Returns:
            Created BlockRule or None if failed
        """
        try:
            response = self._request('POST', '/api/rules', json={
                'rule_type': rule_type,
                'target': target,
                'enabled': enabled
            })
            if response.status_code == 200:
                return BlockRule(**response.json())
            elif response.status_code == 403:
                raise PermissionError("Cannot modify rules during lock period")
        except requests.RequestException:
            pass
        return None

    def update_rule(self, rule_id: int, **updates) -> Optional[BlockRule]:
        """Update a blocking rule.

        Args:
            rule_id: Rule ID to update
            **updates: Fields to update

        Returns:
            Updated BlockRule or None if failed
        """
        try:
            response = self._request('PUT', f'/api/rules/{rule_id}', json=updates)
            if response.status_code == 200:
                return BlockRule(**response.json())
            elif response.status_code == 403:
                raise PermissionError("Cannot modify rules during lock period")
        except requests.RequestException:
            pass
        return None

    def delete_rule(self, rule_id: int) -> bool:
        """Delete a blocking rule.

        Args:
            rule_id: Rule ID to delete

        Returns:
            True if deleted successfully
        """
        try:
            response = self._request('DELETE', f'/api/rules/{rule_id}')
            if response.status_code == 200:
                return True
            elif response.status_code == 403:
                raise PermissionError("Cannot modify rules during lock period")
        except requests.RequestException:
            pass
        return False

    def get_schedules(self) -> List[Schedule]:
        """Get all schedules.

        Returns:
            List of Schedule objects
        """
        try:
            response = self._request('GET', '/api/schedules')
            if response.status_code == 200:
                return [Schedule(**s) for s in response.json()]
        except requests.RequestException:
            pass
        return []

    def add_schedule(self, name: str, schedule_type: str, **kwargs) -> Optional[Schedule]:
        """Add a new schedule.

        Args:
            name: Schedule name
            schedule_type: 'time_range' or 'locked_until'
            **kwargs: Additional schedule fields

        Returns:
            Created Schedule or None if failed
        """
        try:
            data = {
                'name': name,
                'schedule_type': schedule_type,
                **kwargs
            }
            response = self._request('POST', '/api/schedules', json=data)
            if response.status_code == 200:
                return Schedule(**response.json())
            elif response.status_code == 403:
                raise PermissionError("Cannot modify schedules during lock period")
        except requests.RequestException:
            pass
        return None

    def update_schedule(self, schedule_id: int, **updates) -> Optional[Schedule]:
        """Update a schedule.

        Args:
            schedule_id: Schedule ID to update
            **updates: Fields to update

        Returns:
            Updated Schedule or None if failed
        """
        try:
            response = self._request('PUT', f'/api/schedules/{schedule_id}', json=updates)
            if response.status_code == 200:
                return Schedule(**response.json())
            elif response.status_code == 403:
                raise PermissionError("Cannot modify schedules during lock period")
        except requests.RequestException:
            pass
        return None

    def delete_schedule(self, schedule_id: int) -> bool:
        """Delete a schedule.

        Args:
            schedule_id: Schedule ID to delete

        Returns:
            True if deleted successfully
        """
        try:
            response = self._request('DELETE', f'/api/schedules/{schedule_id}')
            if response.status_code == 200:
                return True
            elif response.status_code == 403:
                raise PermissionError("Cannot modify schedules during lock period")
        except requests.RequestException:
            pass
        return False

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
