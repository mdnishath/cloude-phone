export type DeviceState = 'creating' | 'running' | 'stopping' | 'stopped' | 'error' | 'deleted';

export const canStart = (state: DeviceState): boolean =>
  state === 'stopped' || state === 'error';

export const canStop = (state: DeviceState): boolean =>
  state === 'running' || state === 'creating';

export const canDelete = (state: DeviceState): boolean =>
  state !== 'deleted';
