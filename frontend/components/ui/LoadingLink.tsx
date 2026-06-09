'use client';

import Link from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';
import type { ComponentProps, MouseEvent, ReactNode } from 'react';
import { Suspense, useCallback, useEffect, useState } from 'react';
import ButtonSpinner from './ButtonSpinner';

type LoadingLinkProps = Omit<ComponentProps<typeof Link>, 'onClick'> & {
  onClick?: (event: MouseEvent<HTMLAnchorElement>) => void;
  loadingLabel?: ReactNode;
  showSpinner?: boolean;
};

function LoadingLinkInner({
  href,
  onClick,
  children,
  className = '',
  loadingLabel,
  showSpinner = true,
  ...rest
}: LoadingLinkProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [clicked, setClicked] = useState(false);
  const searchKey = searchParams.toString();
  const loading = clicked;

  useEffect(() => {
    setClicked(false);
  }, [pathname, searchKey]);

  useEffect(() => {
    if (!clicked) return;
    const timer = window.setTimeout(() => setClicked(false), 12000);
    return () => window.clearTimeout(timer);
  }, [clicked]);

  const handleClick = useCallback(
    (event: MouseEvent<HTMLAnchorElement>) => {
      onClick?.(event);
      if (event.defaultPrevented) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) {
        return;
      }
      setClicked(true);
    },
    [onClick],
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

export default function LoadingLink(props: LoadingLinkProps) {
  const { className = '', children, href, ...rest } = props;
  return (
    <Suspense
      fallback={
        <Link href={href} className={`btn-interactive ${className}`.trim()} {...rest}>
          {children}
        </Link>
      }
    >
      <LoadingLinkInner {...props} />
    </Suspense>
  );
}
