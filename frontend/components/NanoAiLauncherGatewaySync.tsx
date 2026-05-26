'use client';

import { useEffect } from 'react';
import {
  syncNanoAiWidgetLauncherGatewayButtons,
  type NanoAiGatewayPayload,
} from '@/lib/nanoai-hosted-chat';

type Props = {
  payload: NanoAiGatewayPayload;
};

/**
 * PDP / lướt video: đồng bộ FAB widget NanoAI (Tư vấn nhắn tin + Thử đồ camera)
 * với sku/ảnh SP — bổ sung cho data-ctx-* trên script, không thay thế nút 188.
 */
export default function NanoAiLauncherGatewaySync({ payload }: Props) {
  useEffect(() => {
    if (typeof window === 'undefined') return;
    let cancelled = false;

    const apply = () => {
      if (cancelled) return;
      syncNanoAiWidgetLauncherGatewayButtons(payload);
    };

    apply();

    const tid = window.setInterval(apply, 400);
    const stop = window.setTimeout(() => window.clearInterval(tid), 15_000);

    const mo = new MutationObserver(() => apply());
    mo.observe(document.body, { childList: true, subtree: true });

    window.addEventListener('188-site-embeds-ready', apply);

    return () => {
      cancelled = true;
      window.clearInterval(tid);
      window.clearTimeout(stop);
      mo.disconnect();
      window.removeEventListener('188-site-embeds-ready', apply);
    };
  }, [payload.sku, payload.imageUrl, payload.productUrl, payload.inventoryId]);

  return null;
}
