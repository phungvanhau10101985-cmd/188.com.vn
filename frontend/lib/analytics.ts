'use client';

import { apiClient } from '@/lib/api-client';
import { getGuestSessionId } from '@/lib/guest-session';

/** @deprecated alias — dùng getGuestSessionId */
export const getAnalyticsSessionId = getGuestSessionId;

export function trackEvent(eventName: string, properties: Record<string, any> = {}) {
  if (typeof window === 'undefined') return;
  const sessionId = getGuestSessionId();
  const payload = {
    event_name: eventName,
    session_id: sessionId,
    page_url: window.location.href,
    referrer: document.referrer,
    properties,
  };
  apiClient.trackEvent(payload).catch(() => {});
}
