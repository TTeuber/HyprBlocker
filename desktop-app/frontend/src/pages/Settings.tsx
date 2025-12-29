import { useState, useEffect } from "react";
import { useStatus } from "../context/StatusContext";
import { useToast } from "../context/ToastContext";
import { Card } from "../components/ui/Card";
import { Checkbox, Select } from "../components/ui/FormElements";
import { Button } from "../components/ui/Button";
import { api } from "../lib/api";
import type {
  DevModeStatus,
  WatchdogStatus,
  SettingsLockStatus,
} from "../types";

export function Settings() {
  const { status } = useStatus();
  const { showToast } = useToast();
  const [devModeStatus, setDevModeStatus] = useState<DevModeStatus | null>(
    null,
  );
  const [watchdogStatus, setWatchdogStatus] = useState<WatchdogStatus | null>(
    null,
  );
  const [settingsLock, setSettingsLock] = useState<SettingsLockStatus | null>(
    null,
  );
  const [updating, setUpdating] = useState(false);
  const [lockDuration, setLockDuration] = useState("1h");

  // Load all settings on mount
  useEffect(() => {
    loadDevModeStatus();
    loadWatchdogStatus();
    loadSettingsLock();
  }, []);

  const loadDevModeStatus = async () => {
    try {
      const status = await api.getDevModeStatus();
      setDevModeStatus(status);
    } catch (error) {
      console.error("Failed to load dev mode status:", error);
      showToast("Failed to load settings", "error");
    }
  };

  const handleDevModeToggle = async (enabled: boolean) => {
    setUpdating(true);
    try {
      const result = await api.updateDevMode(enabled);

      if (result.success) {
        showToast(
          enabled
            ? "Browser enforcement disabled"
            : "Browser enforcement enabled",
          "success",
        );
        await loadDevModeStatus();
      } else if (result.env_override) {
        showToast(
          "Dev mode is controlled by environment variable and cannot be changed",
          "warning",
        );
        await loadDevModeStatus();
      } else {
        showToast(result.error || "Failed to update setting", "error");
        await loadDevModeStatus();
      }
    } catch (error) {
      console.error("Failed to update dev mode:", error);
      showToast("Failed to update setting", "error");
      await loadDevModeStatus();
    } finally {
      setUpdating(false);
    }
  };

  const loadWatchdogStatus = async () => {
    try {
      const status = await api.getWatchdogStatus();
      setWatchdogStatus(status);
    } catch (error) {
      console.error("Failed to load watchdog status:", error);
    }
  };

  const loadSettingsLock = async () => {
    try {
      const lock = await api.getSettingsLock();
      setSettingsLock(lock);
    } catch (error) {
      console.error("Failed to load settings lock:", error);
    }
  };

  const handleWatchdogToggle = async (enabled: boolean) => {
    setUpdating(true);
    try {
      const result = await api.updateWatchdog(enabled);

      if (result.success) {
        showToast(
          enabled
            ? "Watchdog protection enabled"
            : "Watchdog protection disabled",
          "success",
        );
        await loadWatchdogStatus();
      } else if (result.settingsLocked) {
        showToast("Settings are locked and cannot be changed", "warning");
      } else {
        showToast(result.error || "Failed to update watchdog", "error");
      }
    } catch (error) {
      console.error("Failed to update watchdog:", error);
      showToast("Failed to update watchdog", "error");
    } finally {
      setUpdating(false);
    }
  };

  const handleWatchdogCountChange = async (count: number) => {
    setUpdating(true);
    try {
      const result = await api.updateWatchdog(undefined, count);

      if (result.success) {
        showToast(`Watchdog count set to ${count}`, "success");
        await loadWatchdogStatus();
      } else if (result.settingsLocked) {
        showToast("Settings are locked and cannot be changed", "warning");
      } else {
        showToast(result.error || "Failed to update watchdog count", "error");
      }
    } catch (error) {
      console.error("Failed to update watchdog count:", error);
      showToast("Failed to update watchdog count", "error");
    } finally {
      setUpdating(false);
    }
  };

  const handleLockSettings = async () => {
    setUpdating(true);
    try {
      // Calculate lock_until based on selected duration
      const now = new Date();
      let lockUntil: Date;

      switch (lockDuration) {
        case "15m":
          lockUntil = new Date(now.getTime() + 15 * 60 * 1000);
          break;
        case "30m":
          lockUntil = new Date(now.getTime() + 30 * 60 * 1000);
          break;
        case "1h":
          lockUntil = new Date(now.getTime() + 60 * 60 * 1000);
          break;
        case "4h":
          lockUntil = new Date(now.getTime() + 4 * 60 * 60 * 1000);
          break;
        case "8h":
          lockUntil = new Date(now.getTime() + 8 * 60 * 60 * 1000);
          break;
        case "1d":
          lockUntil = new Date(now.getTime() + 24 * 60 * 60 * 1000);
          break;
        case "2d":
          lockUntil = new Date(now.getTime() + 24 * 60 * 60 * 1000 * 2);
          break;
        case "1w":
          lockUntil = new Date(now.getTime() + 24 * 60 * 60 * 1000 * 7);
          break;
        case "2w":
          lockUntil = new Date(now.getTime() + 24 * 60 * 60 * 1000 * 14);
          break;
        case "1m":
          lockUntil = new Date(now.getTime() + 24 * 60 * 60 * 1000 * 30);
          break;
        default:
          lockUntil = new Date(now.getTime() + 60 * 60 * 1000);
      }

      const result = await api.lockSettings(lockUntil.toISOString());

      if (result.success) {
        showToast("Settings locked", "success");
        await loadSettingsLock();
      } else {
        showToast(result.error || "Failed to lock settings", "error");
      }
    } catch (error) {
      console.error("Failed to lock settings:", error);
      showToast("Failed to lock settings", "error");
    } finally {
      setUpdating(false);
    }
  };

  const formatRemainingTime = (seconds: number | null): string => {
    if (seconds === null || seconds <= 0) return "";
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (hours > 0) {
      return `${hours}h ${minutes}m remaining`;
    }
    return `${minutes}m remaining`;
  };

  const isSettingsLocked = settingsLock?.locked ?? false;

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
              {status?.running ? "Running" : "Not Running"}
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
              disabled={updating || devModeStatus?.source === "environment"}
            />
            <p className="text-xs text-text-secondary mt-2">
              When enabled, browsers will not be killed for missing extensions.
              Useful for testing or if you don't want browser enforcement.
            </p>
            {devModeStatus?.source === "environment" && (
              <p className="text-xs text-yellow-500 mt-2">
                ⚠️ This setting is controlled by the BLOCKER_DEV_MODE
                environment variable and cannot be changed through the UI.
                Remove the systemd override file to use the UI toggle.
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
            <span className="font-medium text-text">
              ~/.config/website-blocker/
            </span>
          </div>
        </Card>

        <Card title="Watchdog Protection">
          <div className="py-3">
            <Checkbox
              label="Enable watchdog processes"
              checked={watchdogStatus?.enabled ?? false}
              onChange={(e) => handleWatchdogToggle(e.target.checked)}
              disabled={updating || isSettingsLocked}
            />
            <p className="text-xs text-text-secondary mt-2">
              Watchdog processes monitor the daemon and restart it if stopped.
              Uses obfuscated process names for resilience.
            </p>

            {watchdogStatus?.enabled && (
              <div className="mt-4">
                <label className="block text-sm text-text-secondary mb-2">
                  Number of watchdogs
                </label>
                <Select
                  value={String(watchdogStatus?.count ?? 3)}
                  onChange={(e) =>
                    handleWatchdogCountChange(Number(e.target.value))
                  }
                  disabled={updating || isSettingsLocked}
                >
                  <option value="2">2</option>
                  <option value="3">3</option>
                  <option value="4">4</option>
                  <option value="5">5</option>
                </Select>

                {watchdogStatus?.activeWatchdogs &&
                  watchdogStatus.activeWatchdogs.length > 0 && (
                    <div className="mt-3 text-xs text-text-secondary">
                      <p className="font-medium">Active watchdogs:</p>
                      <ul className="mt-1 space-y-1">
                        {watchdogStatus.activeWatchdogs.map((wd) => (
                          <li key={wd.pid}>
                            PID {wd.pid} ({wd.name}) -{" "}
                            {Math.floor(wd.uptime_seconds / 60)}m uptime
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
              </div>
            )}

            {isSettingsLocked && (
              <p className="text-xs text-yellow-500 mt-2">
                Settings are locked and cannot be changed.
              </p>
            )}
          </div>
        </Card>

        <Card title="Settings Lock">
          <div className="py-3">
            {isSettingsLocked ? (
              <div>
                <div className="flex items-center gap-2 text-yellow-500 mb-2">
                  <span className="text-lg">🔒</span>
                  <span className="font-medium">Settings are locked</span>
                </div>
                <p className="text-sm text-text-secondary">
                  {formatRemainingTime(settingsLock?.remainingSeconds ?? null)}
                </p>
                {settingsLock?.lockUntil && (
                  <p className="text-xs text-text-secondary mt-1">
                    Until: {new Date(settingsLock.lockUntil).toLocaleString()}
                  </p>
                )}
              </div>
            ) : (
              <div>
                <p className="text-sm text-text-secondary mb-3">
                  Lock settings to prevent changes for a specified duration.
                  Uses NTP time verification to prevent clock manipulation.
                </p>
                <div className="flex gap-3 items-center">
                  <Select
                    value={lockDuration}
                    onChange={(e) => setLockDuration(e.target.value)}
                    disabled={updating}
                  >
                    <option value="15m">15 minutes</option>
                    <option value="30m">30 minutes</option>
                    <option value="1h">1 hour</option>
                    <option value="4h">4 hours</option>
                    <option value="8h">8 hours</option>
                    <option value="1d">24 hours</option>
                    <option value="2d">2 days</option>
                    <option value="1w">1 week</option>
                    <option value="2w">2 weeks</option>
                    <option value="1m">1 month</option>
                  </Select>
                  <Button
                    onClick={handleLockSettings}
                    disabled={updating}
                    variant="primary"
                  >
                    Lock Settings
                  </Button>
                </div>
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
