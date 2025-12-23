# Website Blocker - Frontend

React + TypeScript + Vite + Tailwind v4 frontend for the Website Blocker desktop application.

## Tech Stack

- **Vite** - Build tool
- **React 18** - UI framework
- **TypeScript** - Type safety
- **Tailwind CSS v4** - Styling with JetBrains Darcula theme
- **Lucide React** - Icons
- **Bun** - Package manager and runtime

## Development

### Prerequisites

- Bun installed
- Python with pywebview for the desktop app

### Running in Development Mode

Development mode enables hot module reloading (HMR) for fast development.

**Terminal 1 - Start Vite dev server:**
```bash
cd frontend
bun run dev
```

**Terminal 2 - Start pywebview app in dev mode:**
```bash
# From desktop-app root directory
python main.py --dev
```

The app will connect to the Vite dev server at `http://localhost:5173` and changes will hot-reload automatically.

### Production Build

```bash
cd frontend
bun run build
```

This builds the frontend to `../web/` directory.

Then run the app normally:
```bash
python main.py
```

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

## Theme

The app uses a custom JetBrains Darcula dark theme defined in `src/index.css` using Tailwind v4's `@theme` directive.

## API Integration

The frontend communicates with Python through pywebview's JavaScript API bridge. See `src/lib/api.ts` for the typed wrapper around `window.pywebview.api`.
