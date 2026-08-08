'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  useCallback,
  useRef,
  useState,
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
  onClick,
  className,
  ...rest
}: ProductPdpLinkProps) {
  const router = useRouter();
  const prefetchedRef = useRef(false);
  const [isNavigating, setIsNavigating] = useState(false);

  const warmRoute = useCallback(() => {
    if (prefetchedRef.current) return;
    prefetchedRef.current = true;
    prefetchProductPdp(router, href);
  }, [href, router]);

  const handleClick = (e: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(e);
    // Không hiển thị pending khi mở tab mới hay click đã bị caller chặn.
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    setIsNavigating(true);
  };

  return (
    <Link
      href={href}
      // Lưới trang chủ có đến 48 thẻ; prefetch tự động toàn bộ dễ chiếm
      // băng thông và làm chậm request của sản phẩm người dùng vừa bấm.
      prefetch={false}
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
      onClick={handleClick}
      aria-busy={isNavigating || undefined}
      className={`${className ?? ''}${isNavigating ? ' opacity-70' : ''}`}
      {...rest}
    />
  );
}
