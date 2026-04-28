'use client';

const SESSION_KEY = 'analytics_session';
const SESSION_TTL_MS = 30 * 60 * 1000;

function generateId() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/** Phiên trình duyệt (analytics + X-Guest-Session-Id). Không import api-client. */
export function getGuestSessionId(): string | null {
  if (typeof window === 'undefined') return null;
  const now = Date.now();
  try {
    const stored = localStorage.getItem(SESSION_KEY);
    if (stored) {
      const parsed = JSON.parse(stored) as { id: string; expiresAt: number };
      if (parsed?.id && parsed.expiresAt > now) {
        const refreshed = { ...parsed, expiresAt: now + SESSION_TTL_MS };
        localStorage.setItem(SESSION_KEY, JSON.stringify(refreshed));
        return parsed.id;
      }
    }
  } catch {
    // ignore
  }
  const newSession = { id: generateId(), expiresAt: now + SESSION_TTL_MS };
  try {
    localStorage.setItem(SESSION_KEY, JSON.stringify(newSession));
  } catch {
    // ignore
  }
  return newSession.id;
}
