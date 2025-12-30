import { useStatus } from '../context/StatusContext';
import { Card } from '../components/ui/Card';
import { capitalizeFirst } from '../lib/api';

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

export function Dashboard() {
  const { status, stats, browsers } = useStatus();

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-semibold text-text">Dashboard</h2>
      </div>

      <div className="grid grid-cols-2 gap-5">
        {/* Status Card */}
        <Card title="Status">
          <div className="text-3xl font-bold text-accent-blue mb-2">
            {status?.running ? 'Active' : 'Daemon Not Running'}
          </div>
          <div className="text-sm text-text-secondary">
            {status?.active_blocks ?? 0} blocks | {status?.browsers_compliant ?? 0}/
            {status?.browsers_detected ?? 0} browsers
          </div>
        </Card>

        {/* Today's Activity Card */}
        <Card title="Today's Activity">
          <div className="grid grid-cols-3 gap-4">
            <div className="text-center p-4 bg-bg-secondary rounded-lg">
              <span className="block text-3xl font-bold text-accent-blue">
                {stats?.websites_blocked_today ?? 0}
              </span>
              <span className="text-xs text-text-secondary uppercase tracking-wide">
                Sites Blocked
              </span>
            </div>
            <div className="text-center p-4 bg-bg-secondary rounded-lg">
              <span className="block text-3xl font-bold text-accent-blue">
                {stats?.apps_closed_today ?? 0}
              </span>
              <span className="text-xs text-text-secondary uppercase tracking-wide">
                Apps Closed
              </span>
            </div>
            <div className="text-center p-4 bg-bg-secondary rounded-lg">
              <span className="block text-3xl font-bold text-accent-blue">
                {stats?.browsers_killed_today ?? 0}
              </span>
              <span className="text-xs text-text-secondary uppercase tracking-wide">
                Browsers Killed
              </span>
            </div>
          </div>
        </Card>

        {/* Browser Status Card */}
        <Card title="Browser Status" className="col-span-2">
          {browsers.length === 0 ? (
            <p className="text-center text-text-secondary py-4">No browsers detected</p>
          ) : (
            <div className="flex flex-col gap-2">
              {browsers.map((browser) => (
                <div
                  key={browser.pid}
                  className="flex items-center gap-3 p-3 bg-bg-secondary rounded-lg"
                >
                  <span className="text-xl">{getBrowserIcon(browser.browser)}</span>
                  <span className="flex-1 font-medium">{capitalizeFirst(browser.browser)}</span>
                  <span
                    className={`text-xs px-2 py-1 rounded-full text-text-bright ${
                      browser.compliant ? 'bg-success' : 'bg-danger'
                    }`}
                  >
                    {browser.compliant ? 'Active' : 'No Extension'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
