'use client';

import { useEffect } from 'react';
import { reportSiteError } from '@/lib/report-site-error';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    reportSiteError({
      message: error?.message || 'Lỗi toàn trang',
      stack: error?.stack,
      digest: error?.digest,
    });
  }, [error]);

  return (
    <html lang="vi">
      <body style={{ margin: 0, fontFamily: 'system-ui, sans-serif', background: '#f9fafb' }}>
        <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
          <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 16, padding: 32, maxWidth: 480, textAlign: 'center' }}>
            <h2 style={{ fontSize: 20, margin: '0 0 8px' }}>Có lỗi xảy ra</h2>
            <p style={{ color: '#4b5563', fontSize: 14, margin: '0 0 20px' }}>
              Vui lòng thử tải lại trang. Nếu lỗi vẫn tiếp tục, hãy thử lại sau.
            </p>
            <button
              type="button"
              onClick={() => reset()}
              style={{ background: '#ea580c', color: '#fff', border: 0, borderRadius: 8, padding: '10px 20px', fontWeight: 600, cursor: 'pointer' }}
            >
              Thử lại
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
