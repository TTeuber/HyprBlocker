import { type ReactNode } from 'react';
import { Sidebar } from './Sidebar';
import { ToastContainer } from '../ui/Toast';

interface LayoutProps {
  children: ReactNode;
}

export function Layout({ children }: LayoutProps) {
  return (
    <div className="min-h-screen">
      <Sidebar />
      <div style={{ paddingLeft: '240px' }}>
        <main className="min-h-screen">
          <div className="max-w-[1400px] mx-auto px-8 py-6">
            {children}
          </div>
        </main>
      </div>
      <ToastContainer />
    </div>
  );
}
