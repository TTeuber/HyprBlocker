import { useState, useEffect } from 'react';
import { Modal, ModalFooter } from '../ui/Modal';
import { Button } from '../ui/Button';
import {
  FormGroup,
  FormRow,
  Input,
  Select,
} from '../ui/FormElements';
import { useToast } from '../../context/ToastContext';
import { useStatus } from '../../context/StatusContext';
import { api } from '../../lib/api';
import type { Block } from '../../types';

interface LockModalProps {
  isOpen: boolean;
  onClose: () => void;
  block: Block | null;
}

type LockOption = 'none' | 'until' | 'duration';
type DurationUnit = 'minute' | 'hour' | 'day' | 'month';

const DURATION_UNITS: { value: DurationUnit; label: string }[] = [
  { value: 'minute', label: 'Minutes' },
  { value: 'hour', label: 'Hours' },
  { value: 'day', label: 'Days' },
  { value: 'month', label: 'Months' },
];

export function LockModal({ isOpen, onClose, block }: LockModalProps) {
  const { showToast } = useToast();
  const { refreshBlocks } = useStatus();
  const [lockOption, setLockOption] = useState<LockOption>('none');
  const [lockUntilDate, setLockUntilDate] = useState<string>('');
  const [lockUntilTime, setLockUntilTime] = useState<string>('');
  const [durationValue, setDurationValue] = useState<number>(1);
  const [durationUnit, setDurationUnit] = useState<DurationUnit>('hour');
  const [submitting, setSubmitting] = useState(false);
  const [isCurrentlyLocked, setIsCurrentlyLocked] = useState(false);
  const [checkingLock, setCheckingLock] = useState(false);

  // Check lock status and populate form when opening
  useEffect(() => {
    if (block && isOpen) {
      setCheckingLock(true);
      api.getBlockLockStatus(block.id).then((status) => {
        setIsCurrentlyLocked(status.locked);
        setCheckingLock(false);

        if (status.locked) {
          // Block is locked - default to duration mode for extension
          setLockOption('duration');
          setDurationValue(1);
          setDurationUnit('hour');
          // Clear date/time fields
          setLockUntilDate('');
          setLockUntilTime('');
        } else if (block.lock_mode === 'locked_until' && block.lock_until) {
          // Block has expired lock settings
          setLockOption('until');
          const [datePart, timePart] = block.lock_until.split('T');
          setLockUntilDate(datePart);
          setLockUntilTime(timePart ? timePart.substring(0, 5) : '');
        } else {
          setLockOption('none');
          setLockUntilDate('');
          setLockUntilTime('');
        }
        setDurationValue(1);
        setDurationUnit('hour');
      }).catch(() => {
        setCheckingLock(false);
        setIsCurrentlyLocked(false);
      });
    }
  }, [block, isOpen]);

  const calculateLockUntil = (): string | null => {
    if (lockOption === 'none') {
      return null;
    }

    if (lockOption === 'until') {
      if (!lockUntilDate.trim() || !lockUntilTime.trim()) {
        showToast('Please fill in both date and time', 'error');
        return 'error';
      }
      return `${lockUntilDate.trim()}T${lockUntilTime.trim()}`;
    }

    if (lockOption === 'duration') {
      const now = new Date();
      let milliseconds = 0;

      switch (durationUnit) {
        case 'minute':
          milliseconds = durationValue * 60 * 1000;
          break;
        case 'hour':
          milliseconds = durationValue * 60 * 60 * 1000;
          break;
        case 'day':
          milliseconds = durationValue * 24 * 60 * 60 * 1000;
          break;
        case 'month':
          milliseconds = durationValue * 30 * 24 * 60 * 60 * 1000;
          break;
      }

      const lockUntil = new Date(now.getTime() + milliseconds);
      // Format as local ISO string (no timezone) to match "Until Date/Time" format
      const pad = (n: number) => String(n).padStart(2, '0');
      const y = lockUntil.getFullYear();
      const m = pad(lockUntil.getMonth() + 1);
      const d = pad(lockUntil.getDate());
      const h = pad(lockUntil.getHours());
      const min = pad(lockUntil.getMinutes());
      return `${y}-${m}-${d}T${h}:${min}`;
    }

    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!block) return;

    setSubmitting(true);

    try {
      const lockUntil = calculateLockUntil();
      if (lockUntil === 'error') {
        setSubmitting(false);
        return;
      }

      if (isCurrentlyLocked) {
        // Use extend endpoint
        if (!lockUntil) {
          showToast('Cannot remove lock while locked', 'error');
          setSubmitting(false);
          return;
        }

        const result = await api.extendBlockLock(block.id, lockUntil);

        if (result.success) {
          showToast('Lock extended successfully', 'success');
          await refreshBlocks();
          onClose();
        } else {
          showToast(result.error || 'Failed to extend lock', 'error');
        }
      } else {
        // Use regular update endpoint
        const updates = {
          lock_mode: (lockOption === 'none' ? 'none' : 'locked_until') as 'none' | 'locked_until',
          lock_until: lockUntil ?? undefined,
        };

        const result = await api.updateBlock(block.id, updates);

        if (result.success) {
          showToast(
            lockOption === 'none' ? 'Block unlocked' : 'Block locked successfully',
            'success'
          );
          await refreshBlocks();
          onClose();
        } else {
          showToast(result.error || 'Failed to update lock', 'error');
        }
      }
    } catch (error) {
      console.error('Failed to update lock:', error);
      showToast('Failed to update lock', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  if (!block) return null;

  const formatCurrentLockTime = () => {
    if (!block.lock_until) return '';
    try {
      return new Date(block.lock_until).toLocaleString();
    } catch {
      return block.lock_until;
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={`Lock: ${block.name}`}>
      {checkingLock ? (
        <p className="text-text-secondary">Checking lock status...</p>
      ) : (
        <form onSubmit={handleSubmit}>
          {isCurrentlyLocked ? (
            <>
              <div className="mb-4 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
                <div className="flex items-center gap-2 text-yellow-500 mb-2">
                  <span className="text-lg">🔒</span>
                  <span className="font-medium">Block is currently locked</span>
                </div>
                <p className="text-sm text-text-secondary">
                  Locked until: {formatCurrentLockTime()}
                </p>
                <p className="text-sm text-text-secondary mt-2">
                  You can extend the lock duration, but cannot shorten or remove it until it expires.
                </p>
              </div>

              <FormGroup label="Extend Lock">
                <Select
                  value={lockOption}
                  onChange={(e) => setLockOption(e.target.value as LockOption)}
                >
                  <option value="until">Extend Until Date/Time</option>
                  <option value="duration">Extend By Duration</option>
                </Select>
              </FormGroup>

              {lockOption === 'until' && (
                <FormRow>
                  <FormGroup label="Date">
                    <Input
                      type="date"
                      value={lockUntilDate}
                      onChange={(e) => setLockUntilDate(e.target.value)}
                      required
                    />
                  </FormGroup>
                  <FormGroup label="Time">
                    <Input
                      type="time"
                      value={lockUntilTime}
                      onChange={(e) => setLockUntilTime(e.target.value)}
                      required
                    />
                  </FormGroup>
                </FormRow>
              )}

              {lockOption === 'duration' && (
                <FormRow>
                  <FormGroup label="Duration">
                    <Input
                      type="number"
                      min={1}
                      value={durationValue}
                      onChange={(e) => setDurationValue(parseInt(e.target.value) || 1)}
                      required
                    />
                  </FormGroup>
                  <FormGroup label="Unit">
                    <Select
                      value={durationUnit}
                      onChange={(e) => setDurationUnit(e.target.value as DurationUnit)}
                    >
                      {DURATION_UNITS.map((unit) => (
                        <option key={unit.value} value={unit.value}>
                          {unit.label}
                        </option>
                      ))}
                    </Select>
                  </FormGroup>
                </FormRow>
              )}
            </>
          ) : (
            <>
              <FormGroup label="Lock Mode">
                <Select
                  value={lockOption}
                  onChange={(e) => setLockOption(e.target.value as LockOption)}
                >
                  <option value="none">No Lock</option>
                  <option value="until">Lock Until Date/Time</option>
                  <option value="duration">Lock For Duration</option>
                </Select>
              </FormGroup>

              {lockOption === 'until' && (
                <FormRow>
                  <FormGroup label="Date">
                    <Input
                      type="date"
                      value={lockUntilDate}
                      onChange={(e) => setLockUntilDate(e.target.value)}
                      required
                    />
                  </FormGroup>
                  <FormGroup label="Time">
                    <Input
                      type="time"
                      value={lockUntilTime}
                      onChange={(e) => setLockUntilTime(e.target.value)}
                      required
                    />
                  </FormGroup>
                </FormRow>
              )}

              {lockOption === 'duration' && (
                <FormRow>
                  <FormGroup label="Duration">
                    <Input
                      type="number"
                      min={1}
                      value={durationValue}
                      onChange={(e) => setDurationValue(parseInt(e.target.value) || 1)}
                      required
                    />
                  </FormGroup>
                  <FormGroup label="Unit">
                    <Select
                      value={durationUnit}
                      onChange={(e) => setDurationUnit(e.target.value as DurationUnit)}
                    >
                      {DURATION_UNITS.map((unit) => (
                        <option key={unit.value} value={unit.value}>
                          {unit.label}
                        </option>
                      ))}
                    </Select>
                  </FormGroup>
                </FormRow>
              )}

              {lockOption !== 'none' && (
                <p className="text-sm text-text-secondary mt-4">
                  Locking prevents modifications to this block until the lock expires.
                  You can still add stricter rules while locked.
                </p>
              )}
            </>
          )}

          <ModalFooter>
            <Button type="button" variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              {isCurrentlyLocked ? 'Extend Lock' : lockOption === 'none' ? 'Remove Lock' : 'Apply Lock'}
            </Button>
          </ModalFooter>
        </form>
      )}
    </Modal>
  );
}
