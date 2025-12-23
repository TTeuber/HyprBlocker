import { useState, useEffect } from 'react';
import { useStatus } from '../context/StatusContext';
import { useToast } from '../context/ToastContext';
import { Card } from '../components/ui/Card';
import { Checkbox } from '../components/ui/FormElements';
import { api } from '../lib/api';
import type { DevModeStatus } from '../types';

export function Settings() {
  const { status } = useStatus();
  const { showToast } = useToast();
  const [devModeStatus, setDevModeStatus] = useState<DevModeStatus | null>(null);
  const [updating, setUpdating] = useState(false);

  // Load dev mode status on mount
  useEffect(() => {
    loadDevModeStatus();
  }, []);

  const loadDevModeStatus = async () => {
    try {
      const status = await api.getDevModeStatus();
      setDevModeStatus(status);
    } catch (error) {
      console.error('Failed to load dev mode status:', error);
      showToast('Failed to load settings', 'error');
    }
  };

  const handleDevModeToggle = async (enabled: boolean) => {
    setUpdating(true);
    try {
      const result = await api.updateDevMode(enabled);

      if (result.success) {
        showToast(
          enabled
            ? 'Browser enforcement disabled'
            : 'Browser enforcement enabled',
          'success'
        );
        await loadDevModeStatus();
      } else if (result.env_override) {
        showToast(
          'Dev mode is controlled by environment variable and cannot be changed',
          'warning'
        );
        await loadDevModeStatus();
      } else {
        showToast(result.error || 'Failed to update setting', 'error');
        await loadDevModeStatus();
      }
    } catch (error) {
      console.error('Failed to update dev mode:', error);
      showToast('Failed to update setting', 'error');
      await loadDevModeStatus();
    } finally {
      setUpdating(false);
    }
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-semibold text-text">Settings</h2>
      </div>

      <div className="grid grid-cols-2 gap-5">
        <Card title="Daemon">
          <div className="flex justify-between py-3 border-b border-border">
            <span className="text-text-secondary">Status:</span>
            <span className="font-medium text-text">
              {status?.running ? 'Running' : 'Not Running'}
            </span>
          </div>
          <div className="flex justify-between py-3">
            <span className="text-text-secondary">Port:</span>
            <span className="font-medium text-text">8765</span>
          </div>
        </Card>

        <Card title="Browser Enforcement">
          <div className="py-3">
            <Checkbox
              label="Disable browser enforcement"
              checked={devModeStatus?.enabled ?? false}
              onChange={(e) => handleDevModeToggle(e.target.checked)}
              disabled={updating || devModeStatus?.source === 'environment'}
            />
            <p className="text-xs text-text-secondary mt-2">
              When enabled, browsers will not be killed for missing extensions.
              Useful for testing or if you don't want browser enforcement.
            </p>
            {devModeStatus?.source === 'environment' && (
              <p className="text-xs text-yellow-500 mt-2">
                ⚠️ This setting is controlled by the BLOCKER_DEV_MODE environment variable
                and cannot be changed through the UI. Remove the systemd override file to
                use the UI toggle.
              </p>
            )}
          </div>
        </Card>

        <Card title="About">
          <div className="flex justify-between py-3 border-b border-border">
            <span className="text-text-secondary">Version:</span>
            <span className="font-medium text-text">1.0.0</span>
          </div>
          <div className="flex justify-between py-3">
            <span className="text-text-secondary">Config:</span>
            <span className="font-medium text-text">~/.config/website-blocker/</span>
          </div>
        </Card>
      </div>
    </div>
  );
}
