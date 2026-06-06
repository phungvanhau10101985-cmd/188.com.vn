'use client';

import { useSyncExternalStore } from 'react';

const subscribeNoop = () => () => {};

/** true chỉ sau hydrate trên client; server và lần hydrate đầu luôn false (tránh lệch DOM). */
export function useClientMounted(): boolean {
  return useSyncExternalStore(subscribeNoop, () => true, () => false);
}
