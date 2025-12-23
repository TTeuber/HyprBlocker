import { LayoutDashboard, Blocks, BarChart3, Globe, Settings } from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { useStatus } from '../../context/StatusContext';
import type { Page } from '../../types';

interface NavItem {
  id: Page;
  label: string;
  icon: typeof LayoutDashboard;
}

const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'blocks', label: 'Blocks', icon: Blocks },
  { id: 'stats', label: 'Statistics', icon: BarChart3 },
  { id: 'browsers', label: 'Browsers', icon: Globe },
  { id: 'settings', label: 'Settings', icon: Settings },
];

export function Sidebar() {
  const { currentPage, setCurrentPage } = useApp();
  const { status } = useStatus();

  const isConnected = status?.running ?? false;

  return (
    <nav className="w-60 bg-bg-sidebar text-text-bright flex flex-col fixed h-screen left-0 top-0">
      {/* Header */}
      <div className="p-6 border-b border-white/10">
        <h1 className="text-lg font-semibold">Website Blocker</h1>
      </div>

      {/* Navigation */}
      <ul className="flex-1 py-4">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = currentPage === item.id;

          return (
            <li key={item.id}>
              <button
                onClick={() => setCurrentPage(item.id)}
                className={`w-full flex items-center gap-3 px-6 py-3 text-left transition-colors ${
                  isActive
                    ? 'bg-accent-blue text-text-bright'
                    : 'text-white/70 hover:bg-white/10 hover:text-text-bright'
                }`}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            </li>
          );
        })}
      </ul>

      {/* Footer - Daemon Status */}
      <div className="p-4 border-t border-white/10">
        <div className="flex items-center gap-2 text-sm">
          <span
            className={`w-2.5 h-2.5 rounded-full ${
              isConnected ? 'bg-success' : 'bg-danger'
            }`}
          />
          <span className="text-white/70">
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
      </div>
    </nav>
  );
}
