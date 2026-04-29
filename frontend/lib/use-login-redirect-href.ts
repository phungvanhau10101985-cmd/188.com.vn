'use client';

import { usePathname, useSearchParams } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { buildAuthLoginHrefFromParts } from '@/lib/auth-redirect';

/**
 * href cho nút/link Đăng nhập: pathname + query hiện tại + hash (đồng bộ sau mount và khi hash đổi).
 * `hashOverride` — ép hash (vd `#qa`); nếu không truyền dùng hash trên window.
 */
export function useLoginRedirectHref(hashOverride?: string | null): string {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [hash, setHash] = useState('');

  useEffect(() => {
    const sync = () => {
      if (typeof window === 'undefined') return;
      setHash(window.location.hash || '');
    };
    sync();
    window.addEventListener('hashchange', sync);
    return () => window.removeEventListener('hashchange', sync);
  }, [pathname]);

  return useMemo(() => {
    const effectiveHash = hashOverride !== undefined && hashOverride !== null ? hashOverride : hash;
    return buildAuthLoginHrefFromParts(pathname, searchParams, effectiveHash);
  }, [pathname, searchParams, hash, hashOverride]);
}
