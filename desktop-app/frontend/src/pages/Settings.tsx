import { useStatus } from '../context/StatusContext';
import { Card } from '../components/ui/Card';

export function Settings() {
  const { status } = useStatus();

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
