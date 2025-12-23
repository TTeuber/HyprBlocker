import { type ReactNode } from 'react';

interface BadgeProps {
  variant?: 'default' | 'success' | 'danger' | 'warning' | 'info';
  children: ReactNode;
  className?: string;
}

export function Badge({ variant = 'default', children, className = '' }: BadgeProps) {
  const variantStyles = {
    default: 'bg-bg-elevated text-text-secondary',
    success: 'bg-success/20 text-success',
    danger: 'bg-danger/20 text-danger',
    warning: 'bg-warning/20 text-warning',
    info: 'bg-info/20 text-info',
  };

  return (
    <span
      className={`inline-block px-2.5 py-1 rounded-full text-xs font-medium ${variantStyles[variant]} ${className}`}
    >
      {children}
    </span>
  );
}
