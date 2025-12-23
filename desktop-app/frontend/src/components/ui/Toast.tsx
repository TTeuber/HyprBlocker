import { useToast } from '../../context/ToastContext';
import { X } from 'lucide-react';

export function ToastContainer() {
  const { toasts, removeToast } = useToast();

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-6 right-6 z-[1001] flex flex-col gap-3">
      {toasts.map((toast) => {
        const typeStyles = {
          success: 'bg-success',
          error: 'bg-danger',
          warning: 'bg-warning',
          info: 'bg-bg-sidebar',
        };

        return (
          <div
            key={toast.id}
            className={`${typeStyles[toast.type]} text-text-bright px-6 py-4 rounded-lg shadow-lg flex items-center gap-3 animate-slide-in`}
          >
            <span className="flex-1">{toast.message}</span>
            <button
              onClick={() => removeToast(toast.id)}
              className="hover:opacity-80 transition-opacity"
            >
              <X size={18} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
