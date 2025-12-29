import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react';
import type { DaemonStatus, Block, Stats, BrowserStatus } from '../types';
import { api } from '../lib/api';

interface StatusContextType {
  status: DaemonStatus | null;
  blocks: Block[];
  stats: Stats | null;
  browsers: BrowserStatus[];
  loading: boolean;
  refreshStatus: () => Promise<void>;
  refreshBlocks: () => Promise<void>;
  refreshStats: () => Promise<void>;
  refreshBrowsers: () => Promise<void>;
  refreshAll: () => Promise<void>;
}

const StatusContext = createContext<StatusContextType | null>(null);

export function StatusProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<DaemonStatus | null>(null);
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [browsers, setBrowsers] = useState<BrowserStatus[]>([]);
  const [loading, setLoading] = useState(true);

  const refreshStatus = useCallback(async () => {
    try {
      const data = await api.getStatus();
      setStatus(data);
    } catch (error) {
      console.error('Failed to refresh status:', error);
      setStatus({ running: false, active_rules: 0, active_blocks: 0, browsers_detected: 0, browsers_compliant: 0 });
    }
  }, []);

  const refreshBlocks = useCallback(async () => {
    try {
      const data = await api.getBlocks();
      setBlocks(data);
    } catch (error) {
      console.error('Failed to refresh blocks:', error);
    }
  }, []);

  const refreshStats = useCallback(async () => {
    try {
      const data = await api.getStats();
      setStats(data);
    } catch (error) {
      console.error('Failed to refresh stats:', error);
    }
  }, []);

  const refreshBrowsers = useCallback(async () => {
    try {
      const data = await api.getBrowsers();
      setBrowsers(data);
    } catch (error) {
      console.error('Failed to refresh browsers:', error);
    }
  }, []);

  const refreshAll = useCallback(async () => {
    await Promise.all([refreshStatus(), refreshStats(), refreshBlocks(), refreshBrowsers()]);
  }, [refreshStatus, refreshStats, refreshBlocks, refreshBrowsers]);

  // Initial load
  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await refreshAll();
      setLoading(false);
    };
    init();
  }, [refreshAll]);

  // Periodic refresh every 5 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      refreshStatus();
      refreshStats();
    }, 5000);

    return () => clearInterval(interval);
  }, [refreshStatus, refreshStats]);

  return (
    <StatusContext.Provider
      value={{
        status,
        blocks,
        stats,
        browsers,
        loading,
        refreshStatus,
        refreshBlocks,
        refreshStats,
        refreshBrowsers,
        refreshAll,
      }}
    >
      {children}
    </StatusContext.Provider>
  );
}

export function useStatus() {
  const context = useContext(StatusContext);
  if (!context) {
    throw new Error('useStatus must be used within a StatusProvider');
  }
  return context;
}
