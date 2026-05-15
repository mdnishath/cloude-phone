import { cn } from '@/lib/utils';
import { humanizeState } from '@/lib/format';
import type { DeviceState } from '@/lib/state-machine';

const styles: Record<DeviceState, string> = {
  creating: 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
  running: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300',
  stopping: 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
  stopped: 'bg-slate-500/15 text-slate-700 dark:text-slate-300',
  error: 'bg-red-500/15 text-red-700 dark:text-red-300',
  deleted: 'bg-zinc-700/15 text-zinc-700 dark:text-zinc-400',
};

export const StateBadge = ({ state }: { state: DeviceState }): JSX.Element => (
  <span
    className={cn(
      'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
      styles[state]
    )}
  >
    {humanizeState(state)}
  </span>
);
