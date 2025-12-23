import { useStatus } from '../context/StatusContext';
import { Card } from '../components/ui/Card';

export function Statistics() {
  const { stats } = useStatus();

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-semibold text-text">Statistics</h2>
      </div>

      {/* Overview Cards */}
      <div className="grid grid-cols-3 gap-5 mb-6">
        <div className="bg-gradient-to-br from-accent-blue to-accent-purple text-text-bright p-6 rounded-lg text-center shadow-md">
          <span className="block text-5xl font-bold mb-2">
            {stats?.total_blocks_today ?? 0}
          </span>
          <span className="text-sm opacity-90">Blocks Today</span>
        </div>
        <div className="bg-gradient-to-br from-accent-blue to-accent-purple text-text-bright p-6 rounded-lg text-center shadow-md">
          <span className="block text-5xl font-bold mb-2">
            {stats?.total_blocks_week ?? 0}
          </span>
          <span className="text-sm opacity-90">Blocks This Week</span>
        </div>
        <div className="bg-gradient-to-br from-accent-blue to-accent-purple text-text-bright p-6 rounded-lg text-center shadow-md">
          <span className="block text-5xl font-bold mb-2">
            {stats?.total_blocks_month ?? 0}
          </span>
          <span className="text-sm opacity-90">Blocks This Month</span>
        </div>
      </div>

      {/* Breakdown */}
      <Card title="Breakdown by Type (Today)">
        <div className="flex flex-col gap-3">
          <div className="flex justify-between items-center p-3 bg-bg-secondary rounded-lg">
            <span className="text-text">Websites Blocked</span>
            <strong className="text-text">{stats?.websites_blocked_today ?? 0}</strong>
          </div>
          <div className="flex justify-between items-center p-3 bg-bg-secondary rounded-lg">
            <span className="text-text">Apps Closed</span>
            <strong className="text-text">{stats?.apps_closed_today ?? 0}</strong>
          </div>
          <div className="flex justify-between items-center p-3 bg-bg-secondary rounded-lg">
            <span className="text-text">Browsers Killed</span>
            <strong className="text-text">{stats?.browsers_killed_today ?? 0}</strong>
          </div>
        </div>
      </Card>
    </div>
  );
}
