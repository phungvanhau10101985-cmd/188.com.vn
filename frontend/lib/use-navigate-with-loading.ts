'use client';

import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState, useTransition } from 'react';

type NavigateOptions = {
  scroll?: boolean;
};

export function useNavigateWithLoading() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [pendingHref, setPendingHref] = useState<string | null>(null);

  useEffect(() => {
    if (!isPending) {
      setPendingHref(null);
    }
  }, [isPending]);

  const markPending = useCallback((href: string) => {
    setPendingHref(href);
  }, []);

  const push = useCallback(
    (href: string, options?: NavigateOptions) => {
      startTransition(() => {
        router.push(href, options);
      });
    },
    [router, startTransition],
  );

  const navigate = useCallback(
    (href: string, options?: NavigateOptions) => {
      markPending(href);
      push(href, options);
    },
    [markPending, push],
  );

  const isNavigating = useCallback((href: string) => pendingHref === href, [pendingHref]);

  return { navigate, markPending, push, isNavigating, isPending, pendingHref };
}
