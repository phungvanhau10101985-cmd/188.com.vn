'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import type { ComponentProps, MouseEvent, ReactNode } from 'react';
import { useCallback, useEffect, useState, useTransition } from 'react';
import ButtonSpinner from './ButtonSpinner';

type LoadingLinkProps = Omit<ComponentProps<typeof Link>, 'onClick'> & {
  onClick?: (event: MouseEvent<HTMLAnchorElement>) => void;
  loadingLabel?: ReactNode;
  showSpinner?: boolean;
};

function hrefToString(href: ComponentProps<typeof Link>['href']): string {
  if (typeof href === 'string') return href;
  const pathname = href.pathname ?? '';
  const query = href.query;
  if (!query) return pathname;
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value == null) return;
    if (Array.isArray(value)) {
      value.forEach((item) => params.append(key, String(item)));
      return;
    }
    params.set(key, String(value));
  });
  const qs = params.toString();
  return qs ? `${pathname}?${qs}` : pathname;
}

export default function LoadingLink({
  href,
  onClick,
  children,
  className = '',
  loadingLabel,
  showSpinner = true,
  ...rest
}: LoadingLinkProps) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [clicked, setClicked] = useState(false);
  const destination = hrefToString(href);
  const loading = clicked && isPending;

  useEffect(() => {
    if (!isPending) {
      setClicked(false);
    }
  }, [isPending]);

  const handleClick = useCallback(
    (event: MouseEvent<HTMLAnchorElement>) => {
      onClick?.(event);
      if (event.defaultPrevented) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) {
        return;
      }
      event.preventDefault();
      setClicked(true);
      startTransition(() => {
        router.push(destination);
      });
    },
    [destination, onClick, router, startTransition]
  );

  return (
    <Link
      href={href}
      onClick={handleClick}
      className={`btn-interactive ${className}`.trim()}
      data-loading={loading ? 'true' : undefined}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? (
        <span className="inline-flex items-center justify-center gap-2">
          {showSpinner ? <ButtonSpinner size="sm" /> : null}
          {loadingLabel ?? children}
        </span>
      ) : (
        children
      )}
    </Link>
  );
}
