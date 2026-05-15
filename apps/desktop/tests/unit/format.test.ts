import { describe, expect, it } from 'vitest';
import { humanizeState, formatRelativeTime } from '@/lib/format';

describe('humanizeState', () => {
  it.each([
    ['creating', 'Creating'],
    ['running', 'Running'],
    ['stopping', 'Stopping'],
    ['stopped', 'Stopped'],
    ['error', 'Error'],
    ['deleted', 'Deleted'],
  ])('"%s" -> "%s"', (input, expected) => {
    expect(humanizeState(input)).toBe(expected);
  });
});

describe('formatRelativeTime', () => {
  it('returns "just now" for recent times', () => {
    const ts = new Date(Date.now() - 5_000).toISOString();
    expect(formatRelativeTime(ts)).toBe('just now');
  });
  it('returns "5m ago" for ~5-minute-old times', () => {
    const ts = new Date(Date.now() - 5 * 60_000).toISOString();
    expect(formatRelativeTime(ts)).toBe('5m ago');
  });
  it('returns "2h ago" for ~2-hour-old times', () => {
    const ts = new Date(Date.now() - 2 * 3600_000).toISOString();
    expect(formatRelativeTime(ts)).toBe('2h ago');
  });
});
