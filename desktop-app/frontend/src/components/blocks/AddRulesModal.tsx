import { useState } from 'react';
import { Modal, ModalFooter } from '../ui/Modal';
import { Button } from '../ui/Button';
import { FormGroup, FormSection, Textarea } from '../ui/FormElements';
import { useToast } from '../../context/ToastContext';
import { useStatus } from '../../context/StatusContext';
import { api } from '../../lib/api';
import type { Block } from '../../types';

interface AddRulesModalProps {
  isOpen: boolean;
  onClose: () => void;
  block: Block | null;
}

export function AddRulesModal({ isOpen, onClose, block }: AddRulesModalProps) {
  const { showToast } = useToast();
  const { refreshBlocks } = useStatus();
  const [websitesBlockedAdd, setWebsitesBlockedAdd] = useState('');
  const [appsBlockedAdd, setAppsBlockedAdd] = useState('');
  const [websitesAllowedRemove, setWebsitesAllowedRemove] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!block) return;

    // Check if any fields have content
    const hasContent =
      websitesBlockedAdd.trim() ||
      appsBlockedAdd.trim() ||
      websitesAllowedRemove.trim();

    if (!hasContent) {
      showToast('Please enter at least one rule to add or remove', 'warning');
      return;
    }

    setSubmitting(true);

    try {
      const updates: Record<string, string> = {};

      if (websitesBlockedAdd.trim()) {
        updates.websites_blocked_add = websitesBlockedAdd.trim();
      }
      if (appsBlockedAdd.trim()) {
        updates.apps_blocked_add = appsBlockedAdd.trim();
      }
      if (websitesAllowedRemove.trim()) {
        updates.websites_allowed_remove = websitesAllowedRemove.trim();
      }

      const result = await api.updateBlockStrict(block.id, updates);

      if (result.success) {
        showToast('Rules updated successfully', 'success');
        await refreshBlocks();
        // Clear fields
        setWebsitesBlockedAdd('');
        setAppsBlockedAdd('');
        setWebsitesAllowedRemove('');
        onClose();
      } else {
        showToast(result.error || 'Failed to update rules', 'error');
      }
    } catch (error) {
      console.error('Failed to update rules:', error);
      showToast('Failed to update rules', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  if (!block) return null;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`Add Rules: ${block.name}`}
      size="large"
    >
      <form onSubmit={handleSubmit}>
        <p className="text-sm text-text-secondary mb-4">
          This block is locked, but you can still add stricter rules.
          Adding blocked items and removing allowed items makes the block more restrictive.
        </p>

        <FormSection title="Add to Blocked Lists" hint="Enter one item per line">
          <FormGroup label="Websites to Block" hint="These will be added to the blocked websites list">
            <Textarea
              rows={4}
              placeholder="reddit.com&#10;youtube.com/shorts&#10;twitter.com"
              value={websitesBlockedAdd}
              onChange={(e) => setWebsitesBlockedAdd(e.target.value)}
            />
          </FormGroup>

          <FormGroup label="Apps to Block" hint="These will be added to the blocked apps list">
            <Textarea
              rows={3}
              placeholder="steam&#10;discord"
              value={appsBlockedAdd}
              onChange={(e) => setAppsBlockedAdd(e.target.value)}
            />
          </FormGroup>
        </FormSection>

        <FormSection title="Remove from Allow Lists" hint="Enter one item per line">
          <FormGroup label="Websites to Remove from Allow List" hint="These will be removed from the allowed websites">
            <Textarea
              rows={3}
              placeholder="youtube.com/educational"
              value={websitesAllowedRemove}
              onChange={(e) => setWebsitesAllowedRemove(e.target.value)}
            />
          </FormGroup>
        </FormSection>

        <ModalFooter>
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={submitting}>
            Add Rules
          </Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}
