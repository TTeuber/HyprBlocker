import { Lock, Unlock } from 'lucide-react';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { parseDaysOfWeek, formatDays, formatDate } from '../../lib/api';
import type { Block } from '../../types';

interface BlocksTableProps {
  blocks: Block[];
  onEdit: (block: Block) => void;
  onToggle: (block: Block) => void;
  onDelete: (block: Block) => void;
  onLock: (block: Block) => void;
}

function formatBlockMode(block: Block): React.ReactNode {
  if (block.block_mode === 'always') {
    return <Badge variant="info">Always</Badge>;
  } else if (block.block_mode === 'time_range') {
    const days = parseDaysOfWeek(block.block_days_of_week);
    const daysText = days.length > 0 ? formatDays(days) : 'All days';
    return (
      <div>
        <Badge variant="info">Time Range</Badge>
        <div className="text-xs text-text-secondary mt-1">
          {daysText} {block.block_start_time || ''} - {block.block_end_time || ''}
        </div>
      </div>
    );
  } else {
    return <Badge variant="default">Disabled</Badge>;
  }
}

function isBlockLocked(block: Block): boolean {
  if (block.lock_mode !== 'locked_until' || !block.lock_until) {
    return false;
  }
  return new Date(block.lock_until) > new Date();
}

function formatLockStatus(block: Block): React.ReactNode {
  const locked = isBlockLocked(block);

  if (locked) {
    return (
      <div className="flex flex-col items-start">
        <div className="flex items-center gap-1.5 text-yellow-500">
          <Lock size={16} />
          <span className="text-sm font-medium">Locked</span>
        </div>
        <div className="text-xs text-text-secondary mt-0.5">
          Until {formatDate(block.lock_until)}
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1.5 text-text-secondary">
      <Unlock size={16} />
      <span className="text-sm">Unlocked</span>
    </div>
  );
}

function countRules(block: Block): number {
  const websitesCount = block.websites_blocked
    ? block.websites_blocked.split('\n').filter((s) => s.trim()).length
    : 0;
  const appsCount = block.apps_blocked
    ? block.apps_blocked.split('\n').filter((s) => s.trim()).length
    : 0;
  return websitesCount + appsCount;
}

export function BlocksTable({ blocks, onEdit, onToggle, onDelete, onLock }: BlocksTableProps) {
  if (blocks.length === 0) {
    return (
      <p className="text-center text-text-secondary py-10">
        No blocks configured. Add a block to organize your rules.
      </p>
    );
  }

  return (
    <div className="bg-bg-card rounded-lg shadow-md border border-border overflow-hidden">
      <table className="w-full border-collapse">
        <thead>
          <tr className="bg-bg-secondary">
            <th className="px-4 py-3 text-left text-xs font-semibold text-text-secondary uppercase tracking-wide">
              Name
            </th>
            <th className="px-4 py-3 text-left text-xs font-semibold text-text-secondary uppercase tracking-wide">
              Block Mode
            </th>
            <th className="px-4 py-3 text-left text-xs font-semibold text-text-secondary uppercase tracking-wide">
              Lock
            </th>
            <th className="px-4 py-3 text-left text-xs font-semibold text-text-secondary uppercase tracking-wide">
              Rules
            </th>
            <th className="px-4 py-3 text-left text-xs font-semibold text-text-secondary uppercase tracking-wide">
              Status
            </th>
            <th className="px-4 py-3 text-left text-xs font-semibold text-text-secondary uppercase tracking-wide">
              Actions
            </th>
          </tr>
        </thead>
        <tbody>
          {blocks.map((block) => (
            <tr key={block.id} className="border-t border-border hover:bg-bg-hover/50">
              <td className="px-4 py-3 text-text">{block.name}</td>
              <td className="px-4 py-3">{formatBlockMode(block)}</td>
              <td className="px-4 py-3">
                <button
                  onClick={() => onLock(block)}
                  className="hover:bg-bg-hover rounded p-1 transition-colors cursor-pointer"
                  title="Configure lock"
                >
                  {formatLockStatus(block)}
                </button>
              </td>
              <td className="px-4 py-3 text-text">{countRules(block)} rules</td>
              <td className="px-4 py-3">
                <Badge variant={block.enabled ? 'success' : 'danger'}>
                  {block.enabled ? 'Enabled' : 'Disabled'}
                </Badge>
              </td>
              <td className="px-4 py-3">
                <div className="flex gap-2">
                  <Button size="small" variant="secondary" onClick={() => onEdit(block)}>
                    Edit
                  </Button>
                  <Button size="small" variant="secondary" onClick={() => onToggle(block)}>
                    {block.enabled ? 'Disable' : 'Enable'}
                  </Button>
                  <Button size="small" variant="danger" onClick={() => onDelete(block)}>
                    Delete
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
