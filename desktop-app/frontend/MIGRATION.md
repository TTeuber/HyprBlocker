# Frontend Migration: Vanilla → React + TypeScript + Tailwind v4

## Overview

This document details the migration of the Website Blocker desktop application frontend from vanilla HTML/CSS/JavaScript to a modern React-based stack.

## Migration Summary

**From:**
- Vanilla HTML files
- Plain CSS stylesheets
- Vanilla JavaScript
- No build process

**To:**
- Vite build tool
- React 18 (UI framework)
- TypeScript (type safety)
- Tailwind CSS v4 (styling)
- Lucide React (icons)
- Bun (package manager/runtime)

## Motivation

The UI was becoming more complex, requiring:
- Better state management
- Component reusability
- Type safety to prevent runtime errors
- Modern styling system with dark theme
- Improved developer experience with HMR (Hot Module Reloading)

## Tech Stack Details

### Build Tool: Vite
- Fast HMR during development
- Optimized production builds with code splitting
- Built-in TypeScript support
- Development server on port 5173

### UI Framework: React 18
- Component-based architecture
- React Context API for state management
- Hooks for lifecycle and state

### Type Safety: TypeScript
- Full type definitions for Python API bridge
- Type-safe component props
- Catch errors at compile time

### Styling: Tailwind CSS v4
- **Important:** Uses v4, not v3 (different setup)
- CSS-first configuration with `@theme` directive
- No `tailwind.config.js` file needed
- Custom JetBrains Darcula dark theme
- Utility-first CSS classes

### Icons: Lucide React
- Modern, consistent icon library
- Tree-shakable (only imports used icons)
- Replaces custom SVG/icon fonts

### Package Manager: Bun
- Faster than npm/yarn
- Drop-in replacement for Node.js
- Native TypeScript support

## Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── layout/        # Layout components (Sidebar, Layout, LockBanner)
│   │   ├── ui/            # Reusable UI components (Button, Card, Modal, etc.)
│   │   └── blocks/        # Block-specific components
│   ├── pages/             # Page components (Dashboard, Blocks, etc.)
│   ├── context/           # React Context providers
│   ├── lib/               # API wrapper and utilities
│   ├── types/             # TypeScript type definitions
│   ├── App.tsx            # Main app component
│   ├── main.tsx           # Entry point
│   └── index.css          # Global styles + Tailwind v4 theme
├── vite.config.ts         # Vite configuration
├── tsconfig.json          # TypeScript configuration
└── package.json           # Dependencies
```

### Build Output
- Builds to `../web/` directory
- Python's pywebview loads from this directory in production

## Development Workflow

### Development Mode (with HMR)

**Terminal 1 - Start Vite dev server:**
```bash
cd frontend
bun run dev
```

**Terminal 2 - Start pywebview in dev mode:**
```bash
cd ..  # back to desktop-app root
python main.py --dev
```

The `--dev` flag was added to `main.py` to connect to the Vite dev server at `http://localhost:5173` instead of loading built files.

### Production Build

```bash
cd frontend
bun run build
```

Then run normally:
```bash
cd ..
python main.py
```

## Key Architecture Changes

### State Management

**Before:** Global variables and DOM manipulation

**After:** React Context API with three providers:
1. **AppContext** - Current page navigation
2. **ToastContext** - Toast notifications with auto-dismiss
3. **StatusContext** - Daemon status, blocks, stats (refreshes every 5s)

### API Integration

**Before:** Direct `window.pywebview.api` calls scattered throughout code

**After:** Centralized typed API wrapper in `src/lib/api.ts`:
- Type-safe method signatures
- Helper functions for data parsing/formatting
- Async/await with proper error handling
- `waitForPywebview()` utility to ensure API is ready

### Component Architecture

All UI elements converted to reusable React components:

**Layout Components:**
- `Layout` - Main layout wrapper with sidebar
- `Sidebar` - Fixed navigation sidebar
- `LockBanner` - Shows when app is locked

**UI Components:**
- `Button` - Reusable button with variants
- `Card` - Container component with consistent styling
- `Badge` - Status indicators
- `Modal` - Overlay modals with backdrop
- `Toast` - Notification system
- `FormElements` - Input, Select, Label, Checkbox, FormGroup, FormSection

**Page Components:**
- `Dashboard` - Overview with stats cards
- `Blocks` - Block management with table + modal
- `Statistics` - Detailed stats display
- `Browsers` - Browser status with grace period
- `Settings` - App settings

**Block Components:**
- `BlockModal` - Complex modal with conditional fields based on mode
- `BlocksTable` - Data table with edit/delete actions

### Styling Approach

**Before:**
- Custom CSS files
- Manual class names
- Difficult to maintain consistency

**After:**
- Tailwind utility classes
- Custom JetBrains Darcula theme in `@theme` directive
- Consistent spacing/colors via CSS variables
- No component-specific CSS files needed

## Custom Theme: JetBrains Darcula

Defined in `src/index.css` using Tailwind v4's `@theme` directive:

```css
@theme {
  /* Backgrounds */
  --color-bg: #2b2b2b;
  --color-bg-elevated: #3c3f41;
  --color-bg-sidebar: #1e1e1e;
  --color-bg-card: #3c3f41;
  /* ... */

  /* Accent colors from Darcula syntax highlighting */
  --color-accent-orange: #cc7832;
  --color-accent-green: #6a8759;
  --color-accent-purple: #9876aa;
  --color-accent-blue: #6897bb;
  /* ... */
}
```

Usage in components:
```tsx
<div className="bg-bg-card text-text p-6 rounded-lg">
  <h2 className="text-accent-blue text-xl">Title</h2>
</div>
```

## TypeScript Types

All Python API types defined in `src/types/index.ts`:

```typescript
export interface Block {
  id: number;
  name: string;
  block_mode: 'always' | 'schedule' | 'none';
  lock_mode: 'always' | 'schedule' | 'temporary' | 'none';
  enabled: boolean;
  websites_blocked: string[];
  websites_allowed: string[];
  apps_blocked: string[];
  apps_allowed: string[];
  // ... time-related fields
}

export interface DaemonStatus {
  running: boolean;
  locked: boolean;
  lock_end_time: number | null;
  active_rules: number;
  active_blocks: number;
  browsers_detected: number;
  browsers_compliant: number;
}

// Global pywebview type declaration
declare global {
  interface Window {
    pywebview: {
      api: {
        get_status(): Promise<DaemonStatus>;
        get_blocks(): Promise<Block[]>;
        add_block(data: Partial<Block>): Promise<{ success: boolean; error?: string; locked?: boolean }>;
        // ... all other API methods
      };
    };
  }
}
```

## Issues Encountered & Solutions

### Issue 1: Tailwind v4 Setup Differences

**Problem:** Tailwind v4 has a different setup than v3
- No `tailwind.config.js` file
- Uses CSS-first configuration
- `@theme` directive in CSS instead of JS config

**Solution:**
- Used `@import "tailwindcss";` in index.css
- Configured theme with `@theme { }` directive
- Used `@tailwindcss/vite` plugin (not `tailwindcss/vite`)

### Issue 2: Dev Server Support in pywebview

**Problem:** No hot module reloading during development

**Solution:**
- Added `--dev` flag to `main.py` with argparse
- Dev mode connects to `http://localhost:5173`
- Production mode loads from `web/index.html`
- Configured Vite server with CORS support

### Issue 3: CSS Reset Overriding Tailwind Utilities

**Problem:** ALL padding and margin utilities weren't working
- Sidebar covered content despite using Tailwind classes
- No visible padding anywhere in the app

**Root Cause:**
```css
/* This was AFTER Tailwind's utility layer in compiled CSS */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}
```

The universal selector reset came after `@layer utilities` in the cascade, overriding every Tailwind padding/margin class.

**Solution:**
Deleted the redundant CSS reset (lines 57-62 in original index.css). Tailwind's `@layer base` already includes this reset in the correct position.

**Result:**
- ✅ All Tailwind utilities now work correctly
- ✅ Proper cascade: base layer → utilities → custom styles
- ✅ Padding and margins display correctly throughout app

### Issue 4: Fixed Sidebar Layout

**Problem:** Fixed-position sidebar doesn't participate in flex layout

**Original Attempt:**
```tsx
<div className="flex">
  <Sidebar />  {/* position: fixed */}
  <main className="flex-1 ml-60">  {/* margin-left doesn't work */}
```

**Solution:**
Use padding instead of margin for the content wrapper:
```tsx
<div className="min-h-screen">
  <Sidebar />  {/* position: fixed, w-60 (240px) */}
  <div style={{ paddingLeft: '240px' }}>
    <main className="min-h-screen">
      {/* content */}
    </main>
  </div>
</div>
```

**Note:** After fixing the CSS reset issue, this could be changed to `className="pl-60"` for full Tailwind consistency.

## File Mapping: Before vs After

| Old (Vanilla) | New (React) | Notes |
|---------------|-------------|-------|
| Multiple HTML files | `src/pages/*.tsx` | Single-page app with client-side routing via state |
| Inline `<style>` or separate CSS | `className` with Tailwind | Utility classes, no CSS files per component |
| Global JS variables | React Context (`src/context/*.tsx`) | Proper state management |
| Direct DOM manipulation | React component state | Declarative UI updates |
| Inline event handlers | React event handlers with TypeScript | Type-safe event handling |
| No types | `src/types/index.ts` | Full type safety |

## Benefits of Migration

1. **Type Safety** - Catch errors at compile time, not runtime
2. **Better DX** - HMR for instant feedback during development
3. **Component Reusability** - DRY principle with React components
4. **Maintainability** - Clear project structure and separation of concerns
5. **Modern Tooling** - Vite's fast builds and dev server
6. **Consistent Styling** - Tailwind utilities with custom theme
7. **State Management** - React Context instead of global variables
8. **Better Performance** - Code splitting and optimized production builds

## Development Commands

```bash
# Install dependencies
bun install

# Start dev server (port 5173)
bun run dev

# Build for production
bun run build

# Preview production build
bun run preview

# Lint code
bun run lint

# Type check
tsc -b
```

## Vite Configuration

Key settings in `vite.config.ts`:

```typescript
export default defineConfig({
  plugins: [
    react(),           // React support with JSX
    tailwindcss()      // Tailwind CSS v4 plugin
  ],
  server: {
    port: 5173,        // Dev server port
    strictPort: true,  // Fail if port is taken
    cors: true,        // Enable CORS for pywebview
    host: 'localhost',
  },
  build: {
    outDir: '../web',      // Build to parent directory
    emptyOutDir: true,     // Clean before build
  },
  base: './',              // Relative paths for desktop app
})
```

## Python Integration

The pywebview bridge remains unchanged - the Python `API` class in `main.py` still exposes the same methods. The frontend now:

1. Waits for pywebview to be ready: `await waitForPywebview()`
2. Calls methods through typed wrapper: `await api.getBlocks()`
3. Handles responses with proper TypeScript types

Example:
```typescript
// src/lib/api.ts
export const api = {
  async getBlocks(): Promise<Block[]> {
    await waitForPywebview();
    return window.pywebview.api.get_blocks();
  },
  // ...
};

// Usage in components
import { api } from '../lib/api';

const blocks = await api.getBlocks();  // Type: Block[]
```

## Migration Checklist

- [x] Set up Vite + React + TypeScript project
- [x] Configure Tailwind CSS v4 with custom theme
- [x] Create type definitions for Python API
- [x] Build API wrapper with helper functions
- [x] Create React Context providers for state
- [x] Build reusable UI components
- [x] Convert all pages to React components
- [x] Implement navigation system
- [x] Add dev server support to main.py
- [x] Configure Vite for pywebview integration
- [x] Fix Tailwind CSS reset issue
- [x] Test all functionality in dev and production modes
- [x] Create documentation (this file)

## Future Enhancements

Potential improvements for the future:

1. **React Router** - Replace state-based navigation with proper routing
2. **TanStack Query** - Better data fetching with caching
3. **Form Validation** - Add Zod or similar for form validation
4. **Testing** - Add Jest/Vitest + React Testing Library
5. **Storybook** - Component documentation and visual testing
6. **ESLint Config** - Stricter linting rules
7. **Accessibility** - Add ARIA labels and keyboard navigation
8. **Error Boundaries** - Better error handling in React
9. **Code Splitting** - Lazy load pages for faster initial load
10. **Bundle Analysis** - Optimize bundle size

## Conclusion

The migration to React + TypeScript + Tailwind v4 provides a solid foundation for future development with:
- Modern tooling and developer experience
- Type safety to prevent bugs
- Reusable component architecture
- Consistent styling with custom theme
- Hot module reloading for fast iteration

The codebase is now more maintainable, scalable, and easier to work with.
