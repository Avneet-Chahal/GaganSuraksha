import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TopBar } from './components/layout/TopBar';
import { SimulatorPage } from './pages/SimulatorPage';
import { ConjunctionsPage } from './pages/ConjunctionsPage';
import { EventDetailPage } from './pages/EventDetailPage';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { WatchlistPage } from './pages/WatchlistPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 30, // 30 seconds
      retry: 1,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="min-h-screen bg-[#070B12] text-slate-200 flex flex-col font-sans selection:bg-cyan-500/20 selection:text-cyan-200">
          <TopBar />
          <div className="flex-1 flex flex-col">
            <Routes>
              {/* Landing route opens directly into the 3D Simulator */}
              <Route path="/" element={<Navigate to="/simulator" replace />} />
              <Route path="/simulator" element={<SimulatorPage />} />
              <Route path="/conjunctions" element={<ConjunctionsPage />} />
              <Route path="/conjunctions/:id" element={<EventDetailPage />} />
              <Route path="/analytics" element={<AnalyticsPage />} />
              <Route path="/watchlist" element={<WatchlistPage />} />
              {/* Fallback */}
              <Route path="*" element={<Navigate to="/simulator" replace />} />
            </Routes>
          </div>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
