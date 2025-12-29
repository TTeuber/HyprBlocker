// Block configuration
export interface Block {
  id: number;
  name: string;
  block_mode: 'always' | 'time_range' | 'disabled';
  block_days_of_week: string | null; // JSON string of number array
  block_start_time: string | null;
  block_end_time: string | null;
  lock_mode: 'none' | 'time_range' | 'locked_until';
  lock_days_of_week: string | null; // JSON string of number array
  lock_start_time: string | null;
  lock_end_time: string | null;
  lock_until: string | null;
  enabled: boolean;
  created_at: string;
  websites_blocked: string | null;
  websites_allowed: string | null;
  apps_blocked: string | null;
  apps_allowed: string | null;
}

// Block input for creating/updating
export interface BlockInput {
  name: string;
  block_mode: 'always' | 'time_range' | 'disabled';
  lock_mode: 'none' | 'time_range' | 'locked_until';
  enabled: boolean;
  block_days_of_week?: string;
  block_start_time?: string;
  block_end_time?: string;
  lock_days_of_week?: string;
  lock_start_time?: string;
  lock_end_time?: string;
  lock_until?: string;
  websites_blocked?: string | null;
  websites_allowed?: string | null;
  apps_blocked?: string | null;
  apps_allowed?: string | null;
}

// Daemon status
export interface DaemonStatus {
  running: boolean;
  locked: boolean;
  lock_end_time: string | null;
  active_rules: number;
  active_blocks: number;
  browsers_detected: number;
  browsers_compliant: number;
  error?: string;
}

// Statistics
export interface Stats {
  total_blocks_today: number;
  total_blocks_week: number;
  total_blocks_month: number;
  websites_blocked_today: number;
  apps_closed_today: number;
  browsers_killed_today: number;
}

// Browser status
export interface BrowserStatus {
  pid: number;
  browser: string;
  compliant: boolean;
  last_heartbeat: string;
  incognito_active: boolean;
  incognito_enabled: boolean;
}

// Grace period status
export interface GracePeriodStatus {
  active: boolean;
  expires_at: string | null;
  remaining_seconds: number;
}

// API response types
export interface ApiResponse {
  success: boolean;
  error?: string;
  locked?: boolean;
}

export interface AddBlockResponse extends ApiResponse {
  block?: {
    id: number;
    name: string;
  };
}

export interface GracePeriodResponse extends ApiResponse {
  active?: boolean;
  expires_at?: string;
  remaining_seconds?: number;
}

export interface LockStatusResponse {
  locked: boolean;
}

// Dev mode settings
export interface DevModeStatus {
  enabled: boolean;
  source: 'environment' | 'config' | 'default' | 'unknown';
  error?: string;
}

export interface DevModeUpdateResponse {
  success: boolean;
  enabled?: boolean;
  error?: string;
  env_override?: boolean;
}

// Watchdog status
export interface WatchdogStatus {
  enabled: boolean;
  count: number;
  activeWatchdogs: Array<{
    pid: number;
    name: string;
    uptime_seconds: number;
  }>;
  error?: string;
}

export interface WatchdogUpdateResponse {
  success: boolean;
  enabled?: boolean;
  count?: number;
  error?: string;
  settingsLocked?: boolean;
}

// Settings lock
export interface SettingsLockStatus {
  locked: boolean;
  lockUntil: string | null;
  remainingSeconds: number | null;
}

export interface SettingsLockResponse {
  success: boolean;
  lockUntil?: string;
  error?: string;
  stillLocked?: boolean;
}

// Navigation pages
export type Page = 'dashboard' | 'blocks' | 'stats' | 'browsers' | 'settings';

// Toast types
export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface Toast {
  id: string;
  message: string;
  type: ToastType;
}

// Declare global pywebview API
declare global {
  interface Window {
    pywebview: {
      api: {
        get_status(): Promise<DaemonStatus>;
        get_blocks(): Promise<Block[]>;
        add_block(data: BlockInput): Promise<AddBlockResponse>;
        update_block(block_id: number, updates: Partial<BlockInput>): Promise<ApiResponse>;
        delete_block(block_id: number): Promise<ApiResponse>;
        get_block_lock_status(block_id: number): Promise<LockStatusResponse>;
        get_stats(): Promise<Stats>;
        get_browsers(): Promise<BrowserStatus[]>;
        is_daemon_running(): Promise<boolean>;
        start_extension_grace_period(): Promise<GracePeriodResponse>;
        get_grace_period_status(): Promise<GracePeriodStatus>;
        get_dev_mode_status(): Promise<DevModeStatus>;
        update_dev_mode(enabled: boolean): Promise<DevModeUpdateResponse>;
        get_watchdog_status(): Promise<WatchdogStatus>;
        update_watchdog(enabled?: boolean, count?: number): Promise<WatchdogUpdateResponse>;
        get_settings_lock(): Promise<SettingsLockStatus>;
        lock_settings(lock_until: string): Promise<SettingsLockResponse>;
        unlock_settings(): Promise<SettingsLockResponse>;
      };
    };
  }
}
