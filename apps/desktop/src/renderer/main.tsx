import './styles/index.css';
import { App } from './App';
import { createRoot } from 'react-dom/client';

const el = document.getElementById('root');
if (!el) throw new Error('root element missing');
createRoot(el).render(<App />);
