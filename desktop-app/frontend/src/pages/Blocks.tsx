import { useState } from 'react';
import { Plus } from 'lucide-react';
import { useStatus } from '../context/StatusContext';
import { useToast } from '../context/ToastContext';
import { Button } from '../components/ui/Button';
import { BlocksTable } from '../components/blocks/BlocksTable';
import { BlockModal } from '../components/blocks/BlockModal';
import { api } from '../lib/api';
import type { Block } from '../types';

export function Blocks() {
  const { blocks, refreshBlocks } = useStatus();
  const { showToast } = useToast();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingBlock, setEditingBlock] = useState<Block | null>(null);

  const handleAddBlock = () => {
    setEditingBlock(null);
    setIsModalOpen(true);
  };

  const handleEditBlock = async (block: Block) => {
    try {
      const lockStatus = await api.getBlockLockStatus(block.id);
      if (lockStatus.locked) {
        showToast('This block is currently locked', 'warning');
        return;
      }
      setEditingBlock(block);
      setIsModalOpen(true);
    } catch (error) {
      console.error('Failed to check lock status:', error);
      setEditingBlock(block);
      setIsModalOpen(true);
    }
  };

  const handleToggleBlock = async (block: Block) => {
    try {
      const lockStatus = await api.getBlockLockStatus(block.id);
      if (lockStatus.locked) {
        showToast('This block is currently locked', 'warning');
        return;
      }

      const result = await api.updateBlock(block.id, { enabled: !block.enabled });
      if (result.success) {
        await refreshBlocks();
      } else {
        showToast(result.error || 'Failed to update block', 'error');
      }
    } catch (error) {
      console.error('Failed to toggle block:', error);
      showToast('Failed to update block', 'error');
    }
  };

  const handleDeleteBlock = async (block: Block) => {
    try {
      const lockStatus = await api.getBlockLockStatus(block.id);
      if (lockStatus.locked) {
        showToast('This block is currently locked', 'warning');
        return;
      }

      if (!confirm('Are you sure you want to delete this block?')) {
        return;
      }

      const result = await api.deleteBlock(block.id);
      if (result.success) {
        showToast('Block deleted', 'success');
        await refreshBlocks();
      } else {
        showToast(result.error || 'Failed to delete block', 'error');
      }
    } catch (error) {
      console.error('Failed to delete block:', error);
      showToast('Failed to delete block', 'error');
    }
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setEditingBlock(null);
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-semibold text-text">Blocks</h2>
        <Button onClick={handleAddBlock}>
          <Plus size={18} />
          Add Block
        </Button>
      </div>

      <p className="text-text-secondary mb-5">
        Blocks group rules together and define when they're active and when configuration is locked.
      </p>

      <BlocksTable
        blocks={blocks}
        onEdit={handleEditBlock}
        onToggle={handleToggleBlock}
        onDelete={handleDeleteBlock}
      />

      <BlockModal
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        editBlock={editingBlock}
      />
    </div>
  );
}
