import './styles/index.css';
import { App } from './App';
import { createRoot } from 'react-dom/client';
import { bootstrapAuth } from './stores/auth';
import { bootstrapSettings } from './stores/settings';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 0, refetchOnWindowFocus: false } },
});

const el = document.getElementById('root');
if (!el) throw new Error('root element missing');

Promise.all([bootstrapSettings(), bootstrapAuth()]).finally(() => {
  createRoot(el).render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  );
});
