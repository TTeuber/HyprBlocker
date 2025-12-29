#!/usr/bin/env python3
"""Main entry point for the Website Blocker desktop application."""

import argparse
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
            print(f"\n[PyWebView Bridge] update_block called:")
            print(f"  block_id: {block_id} (type: {type(block_id)})")
            print(f"  updates: {updates}")
            print(f"  updates keys: {list(updates.keys())}")

            # Log each field's value and type
            for key, value in updates.items():
                print(f"    {key}: {value!r} (type: {type(value).__name__})")

            block = self.client.update_block(block_id, **updates)

            print(f"[PyWebView Bridge] api_client returned: {block}")

            if block:
                return {'success': True}
            return {'success': False, 'error': 'Failed to update block'}
        except PermissionError as e:
            print(f"[PyWebView Bridge] PermissionError: {e}")
            return {'success': False, 'error': str(e), 'locked': True}
        except Exception as e:
            print(f"[PyWebView Bridge] Unexpected exception: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': f'Exception: {str(e)}'}

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
            'incognito_active': b.incognito_active,
            'incognito_enabled': b.incognito_enabled
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

    def get_browser_enforcement_status(self) -> dict:
        """Get browser enforcement status.

        Returns:
            dict with browser enforcement status
        """
        status = self.client.get_browser_enforcement_status()
        if status:
            return {
                'enabled': status.enabled,
                'source': status.source
            }
        return {'enabled': True, 'source': 'unknown', 'error': 'Failed to get status'}

    def update_browser_enforcement(self, enabled: bool) -> dict:
        """Update browser enforcement setting.

        Args:
            enabled: Whether to enable browser enforcement

        Returns:
            dict with success status
        """
        try:
            result = self.client.update_browser_enforcement(enabled)
            return {'success': True, 'enabled': result.get('enabled', enabled)}
        except PermissionError as e:
            return {
                'success': False,
                'error': str(e),
                'settingsLocked': True
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def get_safe_search_status(self) -> dict:
        """Get safe search enforcement status.

        Returns:
            dict with safe search enforcement status
        """
        status = self.client.get_safe_search_status()
        if status:
            return {
                'enabled': status.enabled,
                'source': status.source
            }
        return {'enabled': False, 'source': 'unknown', 'error': 'Failed to get status'}

    def update_safe_search(self, enabled: bool) -> dict:
        """Update safe search enforcement setting.

        Args:
            enabled: Whether to enable safe search enforcement

        Returns:
            dict with success status
        """
        try:
            result = self.client.update_safe_search(enabled)
            return {'success': True, 'enabled': result.get('enabled', enabled)}
        except PermissionError as e:
            return {
                'success': False,
                'error': str(e),
                'settingsLocked': True
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def get_shutdown_prevention_status(self) -> dict:
        """Get shutdown prevention status.

        Returns:
            dict with shutdown prevention status
        """
        status = self.client.get_shutdown_prevention_status()
        if status:
            return {
                'enabled': status.enabled,
                'source': status.source
            }
        return {'enabled': False, 'source': 'unknown', 'error': 'Failed to get status'}

    def update_shutdown_prevention(self, enabled: bool) -> dict:
        """Update shutdown prevention setting.

        Args:
            enabled: Whether to enable shutdown prevention

        Returns:
            dict with success status
        """
        try:
            result = self.client.update_shutdown_prevention(enabled)
            return {'success': True, 'enabled': result.get('enabled', enabled)}
        except PermissionError as e:
            return {
                'success': False,
                'error': str(e),
                'settingsLocked': True
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def get_watchdog_status(self) -> dict:
        """Get watchdog status.

        Returns:
            dict with watchdog status
        """
        status = self.client.get_watchdog_status()
        if status:
            return {
                'enabled': status.enabled,
                'count': status.count,
                'activeWatchdogs': status.active_watchdogs
            }
        return {'enabled': False, 'count': 0, 'activeWatchdogs': [], 'error': 'Failed to get watchdog status'}

    def update_watchdog(self, enabled: bool = None, count: int = None) -> dict:
        """Update watchdog settings.

        Args:
            enabled: Whether to enable watchdog
            count: Number of watchdog processes

        Returns:
            dict with success status
        """
        try:
            result = self.client.update_watchdog(enabled=enabled, count=count)
            return {
                'success': True,
                'enabled': result.get('enabled'),
                'count': result.get('count')
            }
        except PermissionError as e:
            return {
                'success': False,
                'error': str(e),
                'settingsLocked': True
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def get_settings_lock(self) -> dict:
        """Get settings lock status.

        Returns:
            dict with settings lock status
        """
        status = self.client.get_settings_lock()
        if status:
            return {
                'locked': status.locked,
                'lockUntil': status.lock_until,
                'remainingSeconds': status.remaining_seconds
            }
        return {'locked': False, 'lockUntil': None, 'remainingSeconds': None}

    def lock_settings(self, lock_until: str) -> dict:
        """Lock settings until a specific datetime.

        Args:
            lock_until: ISO datetime string

        Returns:
            dict with success status
        """
        try:
            result = self.client.lock_settings(lock_until)
            return {
                'success': True,
                'lockUntil': result.get('lock_until')
            }
        except PermissionError as e:
            return {
                'success': False,
                'error': str(e)
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def unlock_settings(self) -> dict:
        """Unlock settings.

        Returns:
            dict with success status
        """
        try:
            self.client.unlock_settings()
            return {'success': True}
        except PermissionError as e:
            return {
                'success': False,
                'error': str(e),
                'stillLocked': True
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }


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
    parser = argparse.ArgumentParser(description='Website Blocker Desktop App')
    parser.add_argument('--dev', action='store_true', help='Run in development mode (connects to Vite dev server)')
    args = parser.parse_args()

    api = API()

    if args.dev:
        # Development mode - connect to Vite dev server
        url = 'http://localhost:5173'
        print("=" * 60)
        print("Running in DEVELOPMENT mode")
        print(f"Connecting to Vite dev server at {url}")
        print("Make sure to run 'bun run dev' in the frontend directory!")
        print("=" * 60)
    else:
        # Production mode - use built files
        try:
            web_dir = get_web_dir()
            url = os.path.join(web_dir, 'index.html')

            if not os.path.exists(url):
                print(f"Error: index.html not found at {url}")
                sys.exit(1)
        except FileNotFoundError as e:
            print(f"Error: {e}")
            sys.exit(1)

    # Create the window
    window = webview.create_window(
        title='Website Blocker',
        url=url,
        js_api=api,
        width=1000,
        height=700,
        min_size=(800, 600),
        resizable=True
    )

    # Start the application
    webview.start(gui='gtk')


if __name__ == '__main__':
    main()
