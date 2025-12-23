#!/usr/bin/env python3
"""Main entry point for the Website Blocker desktop application."""

import json
import os
import subprocess
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
                'active_blocks': status.active_blocks,
                'browsers_detected': status.browsers_detected,
                'browsers_compliant': status.browsers_compliant
            }
        return {'running': False, 'error': 'Daemon not reachable'}

    def get_blocks(self) -> list:
        """Get all blocks."""
        blocks = self.client.get_blocks()
        return [{
            'id': b.id,
            'name': b.name,
            'block_mode': b.block_mode,
            'block_days_of_week': b.block_days_of_week,
            'block_start_time': b.block_start_time,
            'block_end_time': b.block_end_time,
            'lock_mode': b.lock_mode,
            'lock_days_of_week': b.lock_days_of_week,
            'lock_start_time': b.lock_start_time,
            'lock_end_time': b.lock_end_time,
            'lock_until': b.lock_until,
            'enabled': b.enabled,
            'created_at': b.created_at,
            'websites_blocked': b.websites_blocked,
            'websites_allowed': b.websites_allowed,
            'apps_blocked': b.apps_blocked,
            'apps_allowed': b.apps_allowed
        } for b in blocks]

    def add_block(self, data: dict) -> dict:
        """Add a new block."""
        try:
            name = data.pop('name')
            block_mode = data.pop('block_mode', 'always')
            lock_mode = data.pop('lock_mode', 'none')
            block = self.client.add_block(name, block_mode, lock_mode, **data)
            if block:
                return {'success': True, 'block': {'id': block.id, 'name': block.name}}
            return {'success': False, 'error': 'Failed to add block'}
        except PermissionError as e:
            return {'success': False, 'error': str(e), 'locked': True}

    def update_block(self, block_id: int, updates: dict) -> dict:
        """Update a block."""
        try:
            block = self.client.update_block(block_id, **updates)
            if block:
                return {'success': True}
            return {'success': False, 'error': 'Failed to update block'}
        except PermissionError as e:
            return {'success': False, 'error': str(e), 'locked': True}

    def delete_block(self, block_id: int) -> dict:
        """Delete a block."""
        try:
            if self.client.delete_block(block_id):
                return {'success': True}
            return {'success': False, 'error': 'Failed to delete block'}
        except PermissionError as e:
            return {'success': False, 'error': str(e), 'locked': True}

    def get_block_lock_status(self, block_id: int) -> dict:
        """Check if a specific block is currently locked."""
        try:
            response = self.client.get_block_lock_status(block_id)
            return {'locked': response.get('locked', False)}
        except PermissionError:
            return {'locked': True}
        except Exception as e:
            print(f"Error checking block lock status: {e}")
            return {'locked': False}

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

    def start_extension_grace_period(self) -> dict:
        """Start grace period and open browser extensions page.

        Returns:
            dict with status and grace period info
        """
        # Start grace period in daemon
        grace_status = self.client.start_grace_period()

        if grace_status and grace_status.active:
            # Open Chrome extensions page
            try:
                subprocess.Popen(['xdg-open', 'chrome://extensions/'])
            except Exception:
                # Fallback: try direct Chrome command
                try:
                    subprocess.Popen(['google-chrome', 'chrome://extensions/'])
                except Exception:
                    try:
                        subprocess.Popen(['chromium', 'chrome://extensions/'])
                    except Exception:
                        pass

            return {
                'success': True,
                'active': True,
                'expires_at': grace_status.expires_at,
                'remaining_seconds': grace_status.remaining_seconds
            }

        return {
            'success': False,
            'error': 'Failed to start grace period'
        }

    def get_grace_period_status(self) -> dict:
        """Get current grace period status.

        Returns:
            dict with grace period info
        """
        status = self.client.get_grace_period_status()
        if status:
            return {
                'active': status.active,
                'expires_at': status.expires_at,
                'remaining_seconds': status.remaining_seconds
            }
        return {'active': False}


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
