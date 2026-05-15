import { describe, expect, it } from 'vitest';
import { canDelete, canStart, canStop, type DeviceState } from '@/lib/state-machine';

describe('state machine guards', () => {
  it.each<[DeviceState, boolean]>([
    ['stopped', true],
    ['error', true],
    ['running', false],
    ['creating', false],
    ['stopping', false],
    ['deleted', false],
  ])('canStart(%s) === %s', (state, expected) => {
    expect(canStart(state)).toBe(expected);
  });

  it.each<[DeviceState, boolean]>([
    ['running', true],
    ['creating', true],
    ['stopped', false],
    ['error', false],
    ['stopping', false],
    ['deleted', false],
  ])('canStop(%s) === %s', (state, expected) => {
    expect(canStop(state)).toBe(expected);
  });

  it.each<[DeviceState, boolean]>([
    ['running', true],
    ['creating', true],
    ['stopped', true],
    ['error', true],
    ['stopping', true],
    ['deleted', false],
  ])('canDelete(%s) === %s', (state, expected) => {
    expect(canDelete(state)).toBe(expected);
  });
});
