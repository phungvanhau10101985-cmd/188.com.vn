'use client';

import { useEffect, useState } from 'react';

/** Gợi ý origin cho Google Cloud Console khi lỗi origin_mismatch. */
export default function GoogleOAuthOriginHint() {
  const [origin, setOrigin] = useState<string | null>(null);

  useEffect(() => {
    setOrigin(window.location.origin);
  }, []);

  if (!origin) return null;

  return (
    <p className="text-xs text-gray-500 text-center leading-relaxed">
      Nếu Google báo <strong className="text-gray-700">origin_mismatch</strong>: thêm origin{' '}
      <code className="bg-gray-100 px-1 rounded text-gray-800">{origin}</code> vào Google Cloud →
      Credentials → OAuth Web client → <strong>Authorized JavaScript origins</strong>. Xem{' '}
      <code className="text-gray-600">docs/GOOGLE_OAUTH_DANG_NHAP.md</code>.
    </p>
  );
}
