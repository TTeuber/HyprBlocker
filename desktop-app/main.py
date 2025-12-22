#!/usr/bin/env python3
"""Main entry point for the Website Blocker desktop application."""

import json
import os
import sys

import webview

from api_client import DaemonClient


class API:
    """JavaScript API exposed to the webview."""

    def __init__(self):
        self.client = DaemonClient()

    def get_status(self) -> dict:
        """Get daemon status."""
        status = self.client.get_status()
        if status:
            return {
                'running': status.running,
                'locked': status.locked,
                'lock_end_time': status.lock_end_time,
                'active_rules': status.active_rules,
                'active_schedules': status.active_schedules,
                'browsers_detected': status.browsers_detected,
                'browsers_compliant': status.browsers_compliant
            }
        return {'running': False, 'error': 'Daemon not reachable'}

    def get_rules(self) -> list:
        """Get all blocking rules."""
        rules = self.client.get_rules()
        return [{
            'id': r.id,
            'rule_type': r.rule_type,
            'target': r.target,
            'enabled': r.enabled,
            'created_at': r.created_at
        } for r in rules]

    def add_rule(self, rule_type: str, target: str, enabled: bool = True) -> dict:
        """Add a new blocking rule."""
        try:
            rule = self.client.add_rule(rule_type, target, enabled)
            if rule:
                return {
                    'success': True,
                    'rule': {
                        'id': rule.id,
                        'rule_type': rule.rule_type,
                        'target': rule.target,
                        'enabled': rule.enabled
                    }
                }
            return {'success': False, 'error': 'Failed to add rule'}
        except PermissionError as e:
            return {'success': False, 'error': str(e), 'locked': True}

    def update_rule(self, rule_id: int, updates: dict) -> dict:
        """Update a blocking rule."""
        try:
            rule = self.client.update_rule(rule_id, **updates)
            if rule:
                return {'success': True}
            return {'success': False, 'error': 'Failed to update rule'}
        except PermissionError as e:
            return {'success': False, 'error': str(e), 'locked': True}

    def delete_rule(self, rule_id: int) -> dict:
        """Delete a blocking rule."""
        try:
            if self.client.delete_rule(rule_id):
                return {'success': True}
            return {'success': False, 'error': 'Failed to delete rule'}
        except PermissionError as e:
            return {'success': False, 'error': str(e), 'locked': True}

    def get_schedules(self) -> list:
        """Get all schedules."""
        schedules = self.client.get_schedules()
        return [{
            'id': s.id,
            'name': s.name,
            'schedule_type': s.schedule_type,
            'days_of_week': s.days_of_week,
            'start_time': s.start_time,
            'end_time': s.end_time,
            'locked_until': s.locked_until,
            'enabled': s.enabled,
            'created_at': s.created_at,
            'rule_ids': s.rule_ids
        } for s in schedules]

    def add_schedule(self, data: dict) -> dict:
        """Add a new schedule."""
        try:
            name = data.pop('name')
            schedule_type = data.pop('schedule_type')
            schedule = self.client.add_schedule(name, schedule_type, **data)
            if schedule:
                return {'success': True, 'schedule': {'id': schedule.id, 'name': schedule.name}}
            return {'success': False, 'error': 'Failed to add schedule'}
        except PermissionError as e:
            return {'success': False, 'error': str(e), 'locked': True}

    def update_schedule(self, schedule_id: int, updates: dict) -> dict:
        """Update a schedule."""
        try:
            schedule = self.client.update_schedule(schedule_id, **updates)
            if schedule:
                return {'success': True}
            return {'success': False, 'error': 'Failed to update schedule'}
        except PermissionError as e:
            return {'success': False, 'error': str(e), 'locked': True}

    def delete_schedule(self, schedule_id: int) -> dict:
        """Delete a schedule."""
        try:
            if self.client.delete_schedule(schedule_id):
                return {'success': True}
            return {'success': False, 'error': 'Failed to delete schedule'}
        except PermissionError as e:
            return {'success': False, 'error': str(e), 'locked': True}

    def get_stats(self) -> dict:
        """Get blocking statistics."""
        stats = self.client.get_stats()
        if stats:
            return {
                'total_blocks_today': stats.total_blocks_today,
                'total_blocks_week': stats.total_blocks_week,
                'total_blocks_month': stats.total_blocks_month,
                'websites_blocked_today': stats.websites_blocked_today,
                'apps_closed_today': stats.apps_closed_today,
                'browsers_killed_today': stats.browsers_killed_today
            }
        return {}

    def get_browsers(self) -> list:
        """Get detected browsers and their status."""
        browsers = self.client.get_browsers()
        return [{
            'pid': b.pid,
            'browser': b.browser,
            'compliant': b.compliant,
            'last_heartbeat': b.last_heartbeat,
            'incognito_active': b.incognito_active
        } for b in browsers]

    def is_daemon_running(self) -> bool:
        """Check if daemon is running."""
        return self.client.is_daemon_running()


def get_web_dir() -> str:
    """Get the path to the web directory."""
    # Check if running from source
    script_dir = os.path.dirname(os.path.abspath(__file__))
    web_dir = os.path.join(script_dir, 'web')
    if os.path.exists(web_dir):
        return web_dir

    # Check installed location
    installed_dir = os.path.expanduser('~/.local/share/website-blocker/desktop-app/web')
    if os.path.exists(installed_dir):
        return installed_dir

    raise FileNotFoundError("Web directory not found")


def main():
    """Main entry point."""
    try:
        web_dir = get_web_dir()
        index_path = os.path.join(web_dir, 'index.html')

        if not os.path.exists(index_path):
            print(f"Error: index.html not found at {index_path}")
            sys.exit(1)

        api = API()

        # Create the window
        window = webview.create_window(
            title='Website Blocker',
            url=index_path,
            js_api=api,
            width=1000,
            height=700,
            min_size=(800, 600),
            resizable=True
        )

        # Start the application
        webview.start(gui='gtk')

    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
