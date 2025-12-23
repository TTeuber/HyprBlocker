import { useState, useEffect } from 'react';
import { Modal, ModalFooter } from '../ui/Modal';
import { Button } from '../ui/Button';
import {
  FormGroup,
  FormSection,
  FormRow,
  Input,
  Select,
  Textarea,
  Checkbox,
  DayCheckboxes,
} from '../ui/FormElements';
import { useToast } from '../../context/ToastContext';
import { useStatus } from '../../context/StatusContext';
import { api, parseDaysOfWeek } from '../../lib/api';
import type { Block, BlockInput } from '../../types';

interface BlockModalProps {
  isOpen: boolean;
  onClose: () => void;
  editBlock?: Block | null;
}

const INITIAL_FORM_STATE: BlockInput = {
  name: '',
  block_mode: 'always',
  lock_mode: 'none',
  enabled: true,
  block_days_of_week: '[]',
  block_start_time: '09:00',
  block_end_time: '17:00',
  lock_days_of_week: '[]',
  lock_start_time: '09:00',
  lock_end_time: '17:00',
  lock_until: '',
  websites_blocked: '',
  websites_allowed: '',
  apps_blocked: '',
  apps_allowed: '',
};

export function BlockModal({ isOpen, onClose, editBlock }: BlockModalProps) {
  const { showToast } = useToast();
  const { refreshBlocks } = useStatus();
  const [formData, setFormData] = useState<BlockInput>(INITIAL_FORM_STATE);
  const [blockDays, setBlockDays] = useState<number[]>([]);
  const [lockDays, setLockDays] = useState<number[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const isEditMode = !!editBlock;

  // Populate form when editing
  useEffect(() => {
    if (editBlock) {
      setFormData({
        name: editBlock.name,
        block_mode: editBlock.block_mode,
        lock_mode: editBlock.lock_mode,
        enabled: editBlock.enabled,
        block_start_time: editBlock.block_start_time || '09:00',
        block_end_time: editBlock.block_end_time || '17:00',
        lock_start_time: editBlock.lock_start_time || '09:00',
        lock_end_time: editBlock.lock_end_time || '17:00',
        lock_until: editBlock.lock_until || '',
        websites_blocked: editBlock.websites_blocked || '',
        websites_allowed: editBlock.websites_allowed || '',
        apps_blocked: editBlock.apps_blocked || '',
        apps_allowed: editBlock.apps_allowed || '',
      });
      setBlockDays(parseDaysOfWeek(editBlock.block_days_of_week));
      setLockDays(parseDaysOfWeek(editBlock.lock_days_of_week));
    } else {
      setFormData(INITIAL_FORM_STATE);
      setBlockDays([]);
      setLockDays([]);
    }
  }, [editBlock, isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);

    try {
      const data: BlockInput = {
        ...formData,
        block_days_of_week: JSON.stringify(blockDays),
        lock_days_of_week: JSON.stringify(lockDays),
      };

      // Handle lock_until datetime
      if (formData.lock_mode === 'locked_until' && formData.lock_until) {
        // Ensure proper format
        data.lock_until = formData.lock_until;
      }

      let result;
      if (isEditMode && editBlock) {
        result = await api.updateBlock(editBlock.id, data);
      } else {
        result = await api.addBlock(data);
      }

      if (result.success) {
        showToast(isEditMode ? 'Block updated successfully' : 'Block added successfully', 'success');
        await refreshBlocks();
        onClose();
      } else {
        showToast(result.error || 'Failed to save block', 'error');
      }
    } catch (error) {
      console.error('Failed to save block:', error);
      showToast('Failed to save block', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const updateField = <K extends keyof BlockInput>(field: K, value: BlockInput[K]) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEditMode ? 'Edit Block' : 'Add Block'}
      size="large"
    >
      <form onSubmit={handleSubmit}>
        <FormGroup label="Name">
          <Input
            type="text"
            placeholder="e.g., Work Focus"
            value={formData.name}
            onChange={(e) => updateField('name', e.target.value)}
            required
          />
        </FormGroup>

        {/* Block Schedule Section */}
        <FormSection title="Block Schedule" hint="When should content be blocked?">
          <FormGroup label="Block Mode">
            <Select
              value={formData.block_mode}
              onChange={(e) => updateField('block_mode', e.target.value as BlockInput['block_mode'])}
            >
              <option value="always">Always Block</option>
              <option value="time_range">Block During Time Range</option>
              <option value="disabled">Disabled (Don't Block)</option>
            </Select>
          </FormGroup>

          {formData.block_mode === 'time_range' && (
            <>
              <FormGroup label="Block Days">
                <DayCheckboxes
                  name="block-days"
                  selectedDays={blockDays}
                  onChange={setBlockDays}
                />
              </FormGroup>
              <FormRow>
                <FormGroup label="Start Time">
                  <Input
                    type="time"
                    value={formData.block_start_time}
                    onChange={(e) => updateField('block_start_time', e.target.value)}
                  />
                </FormGroup>
                <FormGroup label="End Time">
                  <Input
                    type="time"
                    value={formData.block_end_time}
                    onChange={(e) => updateField('block_end_time', e.target.value)}
                  />
                </FormGroup>
              </FormRow>
            </>
          )}
        </FormSection>

        {/* Lock Schedule Section */}
        <FormSection title="Lock Schedule" hint="When should configuration be locked (read-only)?">
          <FormGroup label="Lock Mode">
            <Select
              value={formData.lock_mode}
              onChange={(e) => updateField('lock_mode', e.target.value as BlockInput['lock_mode'])}
            >
              <option value="none">No Lock</option>
              <option value="time_range">Lock During Time Range</option>
              <option value="locked_until">Lock Until Date/Time</option>
            </Select>
          </FormGroup>

          {formData.lock_mode === 'time_range' && (
            <>
              <FormGroup label="Lock Days">
                <DayCheckboxes
                  name="lock-days"
                  selectedDays={lockDays}
                  onChange={setLockDays}
                />
              </FormGroup>
              <FormRow>
                <FormGroup label="Start Time">
                  <Input
                    type="time"
                    value={formData.lock_start_time}
                    onChange={(e) => updateField('lock_start_time', e.target.value)}
                  />
                </FormGroup>
                <FormGroup label="End Time">
                  <Input
                    type="time"
                    value={formData.lock_end_time}
                    onChange={(e) => updateField('lock_end_time', e.target.value)}
                  />
                </FormGroup>
              </FormRow>
            </>
          )}

          {formData.lock_mode === 'locked_until' && (
            <FormGroup label="Lock Until">
              <Input
                type="datetime-local"
                value={formData.lock_until}
                onChange={(e) => updateField('lock_until', e.target.value)}
              />
            </FormGroup>
          )}
        </FormSection>

        {/* Blocked Content Section */}
        <FormSection title="Blocked Content" hint="Enter one item per line">
          <FormGroup label="Blocked Websites" hint="Supports paths: youtube.com/shorts blocks only YouTube Shorts">
            <Textarea
              rows={4}
              placeholder="reddit.com&#10;youtube.com/shorts&#10;twitter.com"
              value={formData.websites_blocked || ''}
              onChange={(e) => updateField('websites_blocked', e.target.value || null)}
            />
          </FormGroup>

          <FormGroup label="Allowed Websites (exceptions)" hint="Allow list overrides block list">
            <Textarea
              rows={3}
              placeholder="youtube.com/educational&#10;reddit.com/r/programming"
              value={formData.websites_allowed || ''}
              onChange={(e) => updateField('websites_allowed', e.target.value || null)}
            />
          </FormGroup>

          <FormGroup label="Blocked Applications">
            <Textarea
              rows={4}
              placeholder="steam&#10;discord"
              value={formData.apps_blocked || ''}
              onChange={(e) => updateField('apps_blocked', e.target.value || null)}
            />
          </FormGroup>

          <FormGroup label="Allowed Applications (exceptions)">
            <Textarea
              rows={3}
              value={formData.apps_allowed || ''}
              onChange={(e) => updateField('apps_allowed', e.target.value || null)}
            />
          </FormGroup>
        </FormSection>

        <Checkbox
          label="Enabled"
          checked={formData.enabled}
          onChange={(e) => updateField('enabled', e.target.checked)}
        />

        <ModalFooter>
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={submitting}>
            {isEditMode ? 'Save Changes' : 'Add Block'}
          </Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}
