'use client';

import { useEffect } from 'react';

import { APP_WEB_ICON_URL, type CurrentAppWebIcon } from '@/lib/app-web-icon';
import { apiClient } from '@/lib/api-client';

function applyRel(rel: string, href: string, attrs?: Record<string, string>) {
  const links = Array.from(document.head.querySelectorAll<HTMLLinkElement>(`link[rel="${rel}"]`));
  if (links.length === 0) {
    const link = document.createElement('link');
    link.rel = rel;
    document.head.appendChild(link);
    links.push(link);
  }
  links.forEach((link) => {
    link.href = href;
    link.type = 'image/png';
    if (attrs) {
      Object.entries(attrs).forEach(([key, value]) => {
        link.setAttribute(key, value);
      });
    }
  });
}

function applyIcon(url: string) {
  applyRel('icon', url);
  applyRel('shortcut icon', url);
  applyRel('apple-touch-icon', url, { sizes: '180x180' });
}

export default function AppWebIconSync() {
  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const current = (await apiClient.getCurrentAppWebIcon()) as CurrentAppWebIcon;
        if (cancelled) return;
        applyIcon(current.icon_url || APP_WEB_ICON_URL);
      } catch {
        if (!cancelled) applyIcon(APP_WEB_ICON_URL);
      }
    };

    void load();
    const timer = window.setInterval(() => void load(), 5 * 60 * 1000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return null;
}
