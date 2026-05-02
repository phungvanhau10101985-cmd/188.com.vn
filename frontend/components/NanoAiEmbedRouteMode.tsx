'use client';

import { useEffect, useRef } from 'react';
import { findNanoAiChatLoaderScripts } from '@/lib/nanoai-hosted-chat';

type Props = {
  primary: 'try_on';
  tryOnLabel?: string;
};

/**
 * Trang PDP / lướt video: ưu tiên thử đồ khi mở widget (khớp NanoAI `data-primary="try_on"`).
 * Khôi phục thuộc tính script khi rời route.
 */
export default function NanoAiEmbedRouteMode({ primary, tryOnLabel = 'Thử đồ' }: Props) {
  const snapshot = useRef(
    new Map<HTMLScriptElement, { primary: string | null; label: string | null }>()
  );

  useEffect(() => {
    const apply = () => {
      const scripts = findNanoAiChatLoaderScripts();
      for (const script of scripts) {
        if (!snapshot.current.has(script)) {
          snapshot.current.set(script, {
            primary: script.getAttribute('data-primary'),
            label: script.getAttribute('data-try-on-label'),
          });
        }
        script.setAttribute('data-primary', primary);
        script.setAttribute('data-try-on-label', tryOnLabel);
      }
    };

    apply();

    const tid = window.setInterval(apply, 400);
    const stop = window.setTimeout(() => window.clearInterval(tid), 14_000);

    return () => {
      window.clearInterval(tid);
      window.clearTimeout(stop);
      for (const [el, snap] of snapshot.current.entries()) {
        if (snap.primary == null || snap.primary === '') el.removeAttribute('data-primary');
        else el.setAttribute('data-primary', snap.primary);
        if (snap.label == null || snap.label === '') el.removeAttribute('data-try-on-label');
        else el.setAttribute('data-try-on-label', snap.label);
      }
      snapshot.current.clear();
    };
  }, [primary, tryOnLabel]);

  return null;
}
