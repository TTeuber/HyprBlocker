import { AppProvider, useApp } from './context/AppContext';
import { ToastProvider } from './context/ToastContext';
import { StatusProvider } from './context/StatusContext';
import { Layout } from './components/layout/Layout';
import { Dashboard } from './pages/Dashboard';
import { Blocks } from './pages/Blocks';
import { Statistics } from './pages/Statistics';
import { Browsers } from './pages/Browsers';
import { Settings } from './pages/Settings';

function PageRouter() {
  const { currentPage } = useApp();

  switch (currentPage) {
    case 'dashboard':
      return <Dashboard />;
    case 'blocks':
      return <Blocks />;
    case 'stats':
      return <Statistics />;
    case 'browsers':
      return <Browsers />;
    case 'settings':
      return <Settings />;
    default:
      return <Dashboard />;
  }
}

function App() {
  return (
    <ToastProvider>
      <AppProvider>
        <StatusProvider>
          <Layout>
            <PageRouter />
          </Layout>
        </StatusProvider>
      </AppProvider>
    </ToastProvider>
  );
}

export default App;
