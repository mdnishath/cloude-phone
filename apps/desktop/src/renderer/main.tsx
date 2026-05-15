import './styles/index.css';
import { App } from './App';
import { createRoot } from 'react-dom/client';
import { bootstrapAuth } from './stores/auth';
import { bootstrapSettings } from './stores/settings';

const el = document.getElementById('root');
if (!el) throw new Error('root element missing');

Promise.all([bootstrapSettings(), bootstrapAuth()]).finally(() => {
  createRoot(el).render(<App />);
});
