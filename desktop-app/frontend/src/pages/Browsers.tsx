import { useState, useEffect } from 'react';
import { RefreshCw, Plus, Clock, AlertTriangle } from 'lucide-react';
import { useStatus } from '../context/StatusContext';
import { useToast } from '../context/ToastContext';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { api, capitalizeFirst, formatTime } from '../lib/api';

// Browser icon mapping
function getBrowserIcon(browser: string): string {
  const icons: Record<string, string> = {
    firefox: '\uD83D\uDD25',
    chrome: '\uD83D\uDD34',
    chromium: '\uD83D\uDD35',
    brave: '\uD83E\uDD81',
    edge: '\uD83D\uDD36',
    opera: '\uD83C\uDFB5',
    vivaldi: '\uD83C\uDFB6',
  };
  return icons[browser.toLowerCase()] || '\uD83C\uDF10';
}

export function Browsers() {
  const { browsers, refreshBrowsers } = useStatus();
  const { showToast } = useToast();
  const [gracePeriodActive, setGracePeriodActive] = useState(false);
  const [gracePeriodSeconds, setGracePeriodSeconds] = useState(0);

  const handleRefresh = async () => {
    await refreshBrowsers();
  };

  const startGracePeriod = async () => {
    try {
      const result = await api.startExtensionGracePeriod();
      if (result.success && result.remaining_seconds) {
        setGracePeriodActive(true);
        setGracePeriodSeconds(result.remaining_seconds);
        showToast('Grace period started - you have 30 seconds to add the extension', 'success');
      } else {
        showToast(result.error || 'Failed to start grace period', 'error');
      }
    } catch (error) {
      console.error('Failed to start grace period:', error);
      showToast('Failed to start grace period', 'error');
    }
  };

  // Grace period countdown
  useEffect(() => {
    if (!gracePeriodActive || gracePeriodSeconds <= 0) return;

    const interval = setInterval(() => {
      setGracePeriodSeconds((prev) => {
        if (prev <= 1) {
          setGracePeriodActive(false);
          showToast('Grace period ended', 'info');
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [gracePeriodActive, gracePeriodSeconds, showToast]);

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-semibold text-text">Browser Status</h2>
        <div className="flex gap-3">
          <Button onClick={startGracePeriod}>
            <Plus size={18} />
            Add Extension
          </Button>
          <Button variant="secondary" onClick={handleRefresh}>
            <RefreshCw size={18} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Grace Period Banner */}
      {gracePeriodActive && (
        <div className="bg-warning/20 border border-warning rounded-lg px-4 py-3 mb-4 flex items-center gap-2">
          <Clock size={18} className="text-warning" />
          <span className="flex-1 text-text">Grace period active - browser enforcement paused</span>
          <span className="font-bold text-warning">{gracePeriodSeconds}s</span>
        </div>
      )}

      {/* Incognito Permission Warning */}
      {browsers.filter(b => !b.incognito_enabled).length > 0 && (
        <div className="bg-danger/20 border border-danger rounded-lg px-4 py-3 mb-4">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle size={18} className="text-danger" />
            <span className="font-bold text-danger">Incognito Permission Required</span>
          </div>
          <p className="text-text-secondary mb-2">
            {browsers.filter(b => !b.incognito_enabled).length} browser(s) are NON-COMPLIANT
            because they don't have incognito permission
          </p>
          <p className="text-text-secondary text-sm">
            To fix: Open chrome://extensions/, find "Website Blocker",
            and enable "Allow in Incognito"
          </p>
        </div>
      )}

      {/* Browser Grid */}
      <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-5 mb-6">
        {browsers.length === 0 ? (
          <p className="text-center text-text-secondary py-8 col-span-full">
            No browsers detected. Start a browser with the extension installed.
          </p>
        ) : (
          browsers.map((browser) => (
            <Card key={browser.pid}>
              <div className="flex items-center gap-3 mb-4">
                <span className="text-2xl">{getBrowserIcon(browser.browser)}</span>
                <h4 className="flex-1 font-medium text-text">
                  {capitalizeFirst(browser.browser)}
                </h4>
                <Badge variant={browser.compliant ? 'success' : 'danger'}>
                  {browser.compliant ? 'Compliant' : 'Non-compliant'}
                </Badge>
              </div>
              <div className="text-sm text-text-secondary space-y-2">
                <p>
                  <strong className="text-text">PID:</strong> {browser.pid}
                </p>
                <p>
                  <strong className="text-text">Last Heartbeat:</strong>{' '}
                  {formatTime(browser.last_heartbeat)}
                </p>
                <p>
                  <strong className="text-text">Incognito Active:</strong>{' '}
                  {browser.incognito_active ? 'Yes' : 'No'}
                </p>
                <p>
                  <strong className="text-text">Incognito Permission:</strong>{' '}
                  <span className={browser.incognito_enabled ? 'text-accent-green' : 'text-danger'}>
                    {browser.incognito_enabled ? 'Enabled' : 'Disabled'}
                  </span>
                </p>
              </div>
            </Card>
          ))
        )}
      </div>

      {/* Extension Info */}
      <Card title="Extension Setup">
        <p className="text-text-secondary mb-4">
          The browser extension is required for website blocking to work. Install it in each
          browser you use.
        </p>
        <ol className="list-decimal list-inside space-y-3 text-text">
          <li>Click "Add Extension" to start a grace period</li>
          <li>Open your browser's extension settings</li>
          <li>Enable "Developer mode"</li>
          <li>
            Load the extension from:{' '}
            <code className="bg-bg-secondary px-2 py-1 rounded text-accent-green text-sm">
              ~/.local/share/website-blocker/extension
            </code>
          </li>
          <li>Enable the extension in incognito/private mode</li>
        </ol>
      </Card>
    </div>
  );
}
