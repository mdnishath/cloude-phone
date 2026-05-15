import { NavLink } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { Settings as SettingsIcon, Smartphone, Server } from 'lucide-react';

const items = [
  { to: '/devices', icon: Smartphone, label: 'Devices' },
  { to: '/proxies', icon: Server, label: 'Proxies' },
  { to: '/settings', icon: SettingsIcon, label: 'Settings' },
];

export const Sidebar = (): JSX.Element => (
  <nav className="w-56 border-r bg-card p-3 flex flex-col gap-1">
    <div className="px-3 py-2 text-lg font-semibold">Cloude Phone</div>
    {items.map(({ to, icon: Icon, label }) => (
      <NavLink
        key={to}
        to={to}
        className={({ isActive }) =>
          cn(
            'flex items-center gap-2 rounded-md px-3 py-2 text-sm',
            isActive ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/50'
          )
        }
      >
        <Icon className="h-4 w-4" />
        {label}
      </NavLink>
    ))}
  </nav>
);
