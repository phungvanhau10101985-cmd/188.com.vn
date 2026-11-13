'use client';

import { useEffect } from 'react';
import { reportSiteError } from '@/lib/report-site-error';

/** Bắt lỗi JS và promise chưa xử lý trên mọi trang. */
export default function SiteErrorReporter() {
  useEffect(() => {
    const onError = (event: ErrorEvent) => {
      const err = event.error;
      reportSiteError({
        message: event.message || (err instanceof Error ? err.message : 'window.onerror'),
        stack: err instanceof Error ? err.stack : `${event.filename || ''}:${event.lineno || 0}`,
      });
    };
    const onRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason;
      if (reason instanceof Error) {
        if (!reason.message.trim()) return;
        reportSiteError({ message: reason.message, stack: reason.stack });
        return;
      }
      if (typeof reason === 'string') {
        if (!reason.trim()) return;
        reportSiteError({ message: reason });
        return;
      }
      if (reason && typeof reason === 'object') {
        const rec = reason as { message?: unknown; stack?: unknown };
        const message = typeof rec.message === 'string' ? rec.message.trim() : '';
        if (!message) return;
        reportSiteError({
          message,
          stack: typeof rec.stack === 'string' ? rec.stack : undefined,
        });
      }
    };
    window.addEventListener('error', onError);
    window.addEventListener('unhandledrejection', onRejection);
    return () => {
      window.removeEventListener('error', onError);
      window.removeEventListener('unhandledrejection', onRejection);
    };
  }, []);
  return null;
}
