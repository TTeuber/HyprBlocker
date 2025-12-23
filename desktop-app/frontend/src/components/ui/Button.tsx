import { type ButtonHTMLAttributes, type ReactNode } from 'react';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger';
  size?: 'small' | 'medium';
  children: ReactNode;
}

export function Button({
  variant = 'primary',
  size = 'medium',
  className = '',
  children,
  ...props
}: ButtonProps) {
  const baseStyles =
    'inline-flex items-center justify-center gap-2 font-medium rounded-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed';

  const sizeStyles = {
    small: 'px-3 py-1.5 text-xs',
    medium: 'px-5 py-2.5 text-sm',
  };

  const variantStyles = {
    primary:
      'bg-gradient-to-br from-accent-blue to-accent-purple text-text-bright hover:shadow-md hover:-translate-y-0.5',
    secondary:
      'bg-bg-elevated text-text border border-border hover:bg-bg-hover',
    danger:
      'bg-danger text-text-bright hover:brightness-110',
  };

  return (
    <button
      className={`${baseStyles} ${sizeStyles[size]} ${variantStyles[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
