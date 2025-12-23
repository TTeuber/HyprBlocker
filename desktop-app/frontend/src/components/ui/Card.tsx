import { type ReactNode } from 'react';

interface CardProps {
  title?: string;
  children: ReactNode;
  className?: string;
}

export function Card({ title, children, className = '' }: CardProps) {
  return (
    <div
      className={`bg-bg-card rounded-lg p-6 shadow-md border border-border ${className}`}
    >
      {title && (
        <h3 className="text-base font-semibold mb-5 text-text">{title}</h3>
      )}
      {children}
    </div>
  );
}
