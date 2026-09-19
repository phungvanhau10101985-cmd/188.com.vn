'use client';

import { useEffect } from 'react';

import { APP_WEB_ICON_URL } from '@/lib/app-web-icon';
import { useAppWebIconPolling } from '@/lib/use-app-web-icon';

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
  const { icon_url: iconUrl } = useAppWebIconPolling();

  useEffect(() => {
    applyIcon(iconUrl || APP_WEB_ICON_URL);
  }, [iconUrl]);

  return null;
}
