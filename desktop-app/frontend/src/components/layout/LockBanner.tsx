import { Lock } from 'lucide-react';
import { useStatus } from '../../context/StatusContext';

export function LockBanner() {
  const { status } = useStatus();

  if (!status?.locked) return null;

  // Calculate remaining time
  let timerText = '';
  if (status.lock_end_time) {
    const endTime = new Date(status.lock_end_time);
    const now = new Date();
    const diffMs = endTime.getTime() - now.getTime();

    if (diffMs > 0) {
      const hours = Math.floor(diffMs / (1000 * 60 * 60));
      const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
      timerText = `Unlocks in ${hours}h ${minutes}m`;
    }
  }

  return (
    <div className="bg-gradient-to-r from-warning to-orange-700 text-text-bright px-6 py-4 rounded-lg mb-6 flex items-center gap-3 shadow-md">
      <Lock size={24} />
      <span className="flex-1 font-medium">
        Configuration locked during blocking period
      </span>
      {timerText && (
        <span className="text-sm opacity-90">{timerText}</span>
      )}
    </div>
  );
}
