'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  useCallback,
  useRef,
  type ComponentProps,
  type FocusEvent,
  type MouseEvent,
  type TouchEvent,
} from 'react';
import { prefetchProductPdp } from '@/lib/prefetch-product-pdp';

type ProductPdpLinkProps = Omit<ComponentProps<typeof Link>, 'prefetch'> & {
  href: string;
};

/**
 * Link tới PDP — prefetch sớm (touch/hover/focus) để mở gần như tức thì khi bấm.
 */
export default function ProductPdpLink({
  href,
  onTouchStart,
  onMouseEnter,
  onFocus,
  onPointerDown,
  ...rest
}: ProductPdpLinkProps) {
  const router = useRouter();
  const prefetchedRef = useRef(false);

  const warmRoute = useCallback(() => {
    if (prefetchedRef.current) return;
    prefetchedRef.current = true;
    prefetchProductPdp(router, href);
  }, [href, router]);

  return (
    <Link
      href={href}
      prefetch
      onTouchStart={(e: TouchEvent<HTMLAnchorElement>) => {
        warmRoute();
        onTouchStart?.(e);
      }}
      onPointerDown={(e) => {
        if (e.pointerType === 'touch') warmRoute();
        onPointerDown?.(e);
      }}
      onMouseEnter={(e: MouseEvent<HTMLAnchorElement>) => {
        warmRoute();
        onMouseEnter?.(e);
      }}
      onFocus={(e: FocusEvent<HTMLAnchorElement>) => {
        warmRoute();
        onFocus?.(e);
      }}
      {...rest}
    />
  );
}
