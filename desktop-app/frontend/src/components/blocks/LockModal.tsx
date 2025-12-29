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

  // Populate form when opening
  useEffect(() => {
    if (block && isOpen) {
      if (block.lock_mode === 'locked_until' && block.lock_until) {
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
      return lockUntil.toISOString();
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

      const updates = {
        lock_mode: lockOption === 'none' ? 'none' : 'locked_until',
        lock_until: lockUntil,
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
    } catch (error) {
      console.error('Failed to update lock:', error);
      showToast('Failed to update lock', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  if (!block) return null;

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={`Lock: ${block.name}`}>
      <form onSubmit={handleSubmit}>
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

        <ModalFooter>
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={submitting}>
            {lockOption === 'none' ? 'Remove Lock' : 'Apply Lock'}
          </Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}
