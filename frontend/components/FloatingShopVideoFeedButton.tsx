'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useDraggableFloatingOffset } from '@/hooks/useDraggableFloatingOffset';
import { SHOP_VIDEO_FEED_PATH, shopVideoFeedHrefFromPathname } from '@/lib/shop-video-feed';

function pathNorm(p: string | null | undefined): string {
  if (p == null) return '/';
  const t = p.replace(/\/$/, '').trim();
  return t === '' ? '/' : t;
}

/**
 * Icon nổi cố định viewport → vào feed lướt video (desktop + mobile).
 * Ẩn trên trang feed và trang đăng nhập; tránh chồng bottom nav mobile.
 */
export default function FloatingShopVideoFeedButton() {
  const pathname = usePathname();
  const { dragStyle, onPointerDown, onClickCapture, cursorClass } = useDraggableFloatingOffset(
    '188-fab-video-offset',
    true,
    { syncParallelEmbedFloaters: true }
  );
  const norm = pathNorm(pathname);
  const feedHref = shopVideoFeedHrefFromPathname(pathname);

  if (norm === SHOP_VIDEO_FEED_PATH || pathname?.startsWith('/auth/') || pathname?.startsWith('/admin')) {
    return null;
  }

  const isProductDetail = Boolean(pathname?.match(/^\/products\/[^/]+$/));
  /** Giống AppShell `showMobileBottomNav` — chỉ mobile có thanh dưới (Desktop nav ẩn md:hidden) */
  const reserveMobileBottom =
    !pathname?.startsWith('/auth/') && !isProductDetail && norm !== SHOP_VIDEO_FEED_PATH;

  /** Không dùng arbitrary `max(...)` có dấu phẩy — Tailwind có thể bỏ qua → mất `bottom`, nút “biến mất” */
  /** Cạnh trái để không chồng BackToTopButton (phải). */
  const positionClass = reserveMobileBottom
    ? 'bottom-28 left-4 md:bottom-10 md:left-8'
    : 'bottom-8 left-4 md:bottom-10 md:left-8';

  return (
    <Link
      data-188-video-fab
      href={feedHref}
      prefetch={false}
      draggable={false}
      onDragStart={(e) => e.preventDefault()}
      style={dragStyle}
      onPointerDown={onPointerDown}
      onClickCapture={onClickCapture}
      className={`fixed z-[70] flex h-[52px] w-[52px] pointer-events-auto items-center justify-center rounded-full bg-gradient-to-br from-[#ea580c] to-[#c2410c] text-white shadow-[0_3px_12px_rgba(234,88,12,0.4)] ring-2 ring-white transition hover:scale-[1.06] hover:shadow-lg active:scale-[0.97] ${positionClass} ${cursorClass}`}
      aria-label="Lướt xem video shop"
      title="Lướt xem video shop"
    >
      <svg className="h-[26px] w-[26px] shrink-0 drop-shadow-sm" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
        <path d="M17 10.5V7a1 1 0 00-1-1H4a1 1 0 00-1 1v10a1 1 0 001 1h12a1 1 0 001-1v-3.5l4 4v-11l-4 4z" />
      </svg>
    </Link>
  );
}
