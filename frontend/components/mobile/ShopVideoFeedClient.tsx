'use client';

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { useRouter, useSearchParams } from 'next/navigation';
import type { Product } from '@/types/api';
import { apiClient } from '@/lib/api-client';
import { parseVideoLink, buildYoutubeEmbedSrc } from '@/lib/video-utils';
import { formatPrice } from '@/lib/utils';
import { useCart } from '@/features/cart/hooks/useCart';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { useFavorites } from '@/features/favorites/hooks/useFavorites';
import { useToast } from '@/components/ToastProvider';
import { cartLineMainImage } from '@/lib/product-color-variant';
import { buildAuthLoginHrefFromFullPath, getBrowserReturnLocation } from '@/lib/auth-redirect';
import { trackEvent } from '@/lib/analytics';
import ProductVariantModal from '@/app/products/[slug]/components/ProductVariantModal/ProductVariantModal';
import NanoAiProductPageContext from '@/components/NanoAiProductPageContext';
import { SHOP_VIDEO_START_SLUG_PARAM } from '@/lib/shop-video-feed';

const FEED_SOUND_SESSION_KEY = '188-shop-video-feed-sound-on';

function readPersistedFeedSound(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return sessionStorage.getItem(FEED_SOUND_SESSION_KEY) === '1';
  } catch {
    return false;
  }
}

function persistFeedSound(on: boolean) {
  try {
    sessionStorage.setItem(FEED_SOUND_SESSION_KEY, on ? '1' : '0');
  } catch {
    /* private mode / quota */
  }
}

function productHref(p: Product): string {
  const s = (p.slug || '').trim();
  if (s) return `/products/${encodeURIComponent(s)}`;
  return `/products/${encodeURIComponent(p.product_id)}`;
}

function hasPlayableVideoLink(link: string | undefined | null): boolean {
  return parseVideoLink(link) != null;
}

/** Nút 🔊/🔇 — đặt trong section, z cao hơn overlay sản phẩm để touch không bị chặn */
function FeedSoundToggle({ soundOn, onToggle }: { soundOn: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onToggle();
      }}
      onPointerDown={(e) => e.stopPropagation()}
      className="pointer-events-auto absolute right-3 bottom-[calc(7.5rem+env(safe-area-inset-bottom,0px))] z-[35] flex h-11 w-11 touch-manipulation items-center justify-center rounded-full bg-black/60 text-white ring-1 ring-white/40 backdrop-blur-sm shadow-lg active:scale-95"
      aria-label={soundOn ? 'Tắt tiếng' : 'Bật tiếng'}
      title={soundOn ? 'Tắt tiếng' : 'Bật tiếng'}
    >
      {soundOn ? (
        <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24" aria-hidden>
          <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z" />
        </svg>
      ) : (
        <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24" aria-hidden>
          <path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z" />
        </svg>
      )}
    </button>
  );
}

function formatSoldCount(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return '';
  return n.toLocaleString('vi-VN');
}

function VideoFeedProductBar({
  product,
  href,
  isFavorited,
  favoriteBusy,
  cartBusy,
  canAddToCart,
  onOpenCartModal,
  onToggleFavorite,
}: {
  product: Product;
  href: string;
  isFavorited: boolean;
  favoriteBusy: boolean;
  cartBusy: boolean;
  /** false khi hết hàng — nút giỏ vô hiệu */
  canAddToCart: boolean;
  onOpenCartModal: () => void;
  onToggleFavorite: () => void;
}) {
  const sold = product.purchases != null && product.purchases > 0 ? formatSoldCount(product.purchases) : '';
  const reviewTotal = product.rating_total ?? 0;
  const ratingPoint = product.rating_point ?? 0;
  const showReviews = reviewTotal > 0 || ratingPoint > 0;
  const likesCount = product.likes ?? 0;

  return (
    <>
      <p className="text-white text-sm font-medium line-clamp-2 mb-1">{product.name}</p>
      {product.shop_name ? (
        <p className="text-[11px] text-white/65 mb-1.5 truncate">{product.shop_name}</p>
      ) : null}

      {(sold || showReviews) && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] mb-2">
          {sold ? (
            <span className="font-medium text-white tabular-nums drop-shadow-[0_1px_3px_rgba(0,0,0,0.95)]">
              Đã bán {sold}
            </span>
          ) : null}
          {showReviews ? (
            <span className="inline-flex items-center gap-1 text-white drop-shadow-[0_1px_3px_rgba(0,0,0,0.9)]">
              <span className="text-amber-300" aria-hidden>
                ★
              </span>
              <span className="font-semibold text-white">{ratingPoint > 0 ? ratingPoint.toFixed(1) : '—'}</span>
              {reviewTotal > 0 ? (
                <span className="text-white/85">({reviewTotal.toLocaleString('vi-VN')} đánh giá)</span>
              ) : null}
            </span>
          ) : null}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[#ea580c] font-bold shrink-0">{formatPrice(product.price)}</span>

        <div className="ml-auto flex items-center gap-1.5 shrink-0">
          <button
            type="button"
            onClick={onOpenCartModal}
            disabled={cartBusy || !canAddToCart}
            className="min-h-[44px] min-w-[44px] rounded-full bg-white/18 border border-white/25 flex items-center justify-center text-white hover:bg-white/28 active:scale-[0.96] disabled:opacity-45 disabled:pointer-events-none"
            aria-label={canAddToCart ? 'Chọn biến thể và thêm vào giỏ' : 'Hết hàng'}
            title={canAddToCart ? 'Thêm vào giỏ' : 'Hết hàng'}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" aria-hidden>
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z"
              />
            </svg>
          </button>

          <div className="flex flex-col items-center gap-0.5">
            <button
              type="button"
              onClick={onToggleFavorite}
              disabled={favoriteBusy}
              className={`min-h-[44px] min-w-[44px] rounded-full border flex items-center justify-center active:scale-[0.96] disabled:opacity-45 ${
                isFavorited
                  ? 'bg-red-500/35 border-red-400/50 text-red-200'
                  : 'bg-white/18 border-white/25 text-white hover:bg-white/28'
              }`}
              aria-label={isFavorited ? 'Bỏ yêu thích' : 'Thêm yêu thích'}
              title={isFavorited ? 'Bỏ yêu thích' : 'Thích'}
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24" aria-hidden>
                {isFavorited ? (
                  <path
                    fill="currentColor"
                    d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"
                  />
                ) : (
                  <path
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={2}
                    d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"
                  />
                )}
              </svg>
            </button>
            {likesCount > 0 ? (
              <span className="text-[10px] leading-none text-white/65 tabular-nums">{likesCount.toLocaleString('vi-VN')}</span>
            ) : null}
          </div>

          <Link
            href={href}
            className="rounded-full bg-white text-gray-900 px-4 py-2.5 text-xs font-semibold shadow-md active:scale-[0.98] min-h-[44px] inline-flex items-center"
          >
            Xem sản phẩm
          </Link>
        </div>
      </div>
    </>
  );
}

function VideoPane({
  product,
  isActive,
  soundOn,
}: {
  product: Product;
  isActive: boolean;
  /** Âm thanh chỉ áp dụng slide đang active — state giữ ở parent để nút loa nằm trên overlay */
  soundOn: boolean;
}) {
  const parsed = parseVideoLink(product.video_link);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const el = videoRef.current;
    if (!el || parsed?.kind !== 'cdn_mp4') return;
    el.muted = !isActive || !soundOn;
    if (isActive) {
      void el.play().catch(() => {});
    } else {
      el.pause();
    }
  }, [isActive, parsed?.kind, soundOn]);

  if (!parsed) return null;

  if (parsed.kind === 'youtube') {
    const src = buildYoutubeEmbedSrc(parsed.urlOrId, { autoplay: isActive, muted: !soundOn });
    if (!isActive && parsed.thumbUrl) {
      return (
        <div className="relative h-full w-full min-h-0 bg-black">
          <Image src={parsed.thumbUrl} alt="" fill className="object-cover" sizes="100vw" unoptimized />
          <div className="absolute inset-0 flex items-center justify-center bg-black/35">
            <span className="rounded-full bg-white/90 text-gray-900 px-4 py-2 text-sm font-medium shadow-lg">
              Vuốt để xem
            </span>
          </div>
        </div>
      );
    }
    return (
      <div className="relative h-full w-full min-h-0">
        <iframe
          key={`yt-${product.id}-${soundOn ? '1' : '0'}`}
          title={product.name}
          src={src}
          className="absolute inset-0 h-full w-full border-0 bg-black"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share; fullscreen"
          allowFullScreen
          referrerPolicy="strict-origin-when-cross-origin"
        />
      </div>
    );
  }

  return (
    <div className="relative h-full w-full min-h-0">
      <video
        ref={videoRef}
        src={parsed.urlOrId}
        className="absolute inset-0 h-full w-full object-cover bg-black"
        playsInline
        loop
        muted={!isActive || !soundOn}
        controls={isActive}
      />
    </div>
  );
}

export default function ShopVideoFeedClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const seedFromUrl = searchParams.get('seed');
  const parsedSeed =
    seedFromUrl != null && seedFromUrl !== '' && Number.isFinite(Number(seedFromUrl))
      ? Number(seedFromUrl)
      : undefined;

  const startSlugForFeed = useMemo(() => {
    const raw = searchParams.get(SHOP_VIDEO_START_SLUG_PARAM)?.trim();
    return raw && raw !== '' ? raw : undefined;
  }, [searchParams]);

  const [products, setProducts] = useState<Product[]>([]);
  const [total, setTotal] = useState(0);
  const [seed, setSeed] = useState<number | null>(parsedSeed ?? null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  /** Offset tiếp theo gửi API (theo thứ tự seed), không phải độ dài danh sách đã lọc client */
  const [apiOffset, setApiOffset] = useState(0);

  const { addToCart, isLoading: cartBusy } = useCart();
  const { isAuthenticated } = useAuth();
  const { refreshFavorites } = useFavorites();
  const { pushToast } = useToast();
  const [favoriteIds, setFavoriteIds] = useState<Set<number>>(() => new Set());
  const [favoriteBusyId, setFavoriteBusyId] = useState<number | null>(null);
  const [variantModalProduct, setVariantModalProduct] = useState<Product | null>(null);
  const [displayStockByVariant, setDisplayStockByVariant] = useState<Record<string, number>>({});
  /** Tiếng: giữ khi vuốt sang clip khác; đọc/ghi session để không phải bật lại mỗi video */
  const [feedSoundOn, setFeedSoundOn] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const loadMoreSentinelRef = useRef<HTMLDivElement>(null);
  const emptyPageFetchAttempts = useRef(0);
  /** Cuộn về slide 0 khi mở feed kèm start_slug (chỉ một lần sau mỗi lần đổi query). */
  const didApplyStartSlugScroll = useRef(false);

  useEffect(() => {
    if (readPersistedFeedSound()) setFeedSoundOn(true);
  }, []);

  const toggleFeedSound = useCallback(() => {
    setFeedSoundOn((v) => {
      const next = !v;
      persistFeedSound(next);
      return next;
    });
  }, []);

  const fetchPage = useCallback(
    async (
      offset: number,
      nextSeed: number | undefined,
      append: boolean,
      opts?: { startSlug?: string }
    ) => {
      const res = await apiClient.getProductsSameShopAsRecentViews(15, offset, nextSeed ?? null, true);
      const rawBatch = res.products || [];
      let playable = rawBatch.filter((p) => hasPlayableVideoLink(p.video_link));

      if (!append && opts?.startSlug) {
        try {
          const sp = await apiClient.getProductBySlug(opts.startSlug);
          if (sp && hasPlayableVideoLink(sp.video_link)) {
            playable = [sp, ...playable.filter((p) => p.id !== sp.id)];
          }
        } catch {
          /* slug không hợp lệ / lỗi mạng — dùng feed mặc định */
        }
      }

      if (append) {
        setProducts((prev) => {
          const seen = new Set(prev.map((p) => p.id));
          return [...prev, ...playable.filter((p) => !seen.has(p.id))];
        });
      } else {
        setProducts(playable);
      }
      setTotal(res.total ?? 0);
      if (res.seed != null) setSeed(res.seed);
      setApiOffset(offset + rawBatch.length);
      return rawBatch.length;
    },
    []
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setApiOffset(0);
    emptyPageFetchAttempts.current = 0;
    fetchPage(0, parsedSeed, false, startSlugForFeed ? { startSlug: startSlugForFeed } : undefined)
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Không tải được danh sách video');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [parsedSeed, startSlugForFeed, fetchPage]);

  useEffect(() => {
    didApplyStartSlugScroll.current = false;
  }, [startSlugForFeed, parsedSeed]);

  useLayoutEffect(() => {
    if (loading || !startSlugForFeed || products.length === 0) return;
    if (didApplyStartSlugScroll.current) return;
    didApplyStartSlugScroll.current = true;
    const root = scrollRef.current;
    if (root) root.scrollTop = 0;
    setActiveIndex(0);
  }, [loading, startSlugForFeed, products.length]);

  useEffect(() => {
    if (!isAuthenticated) {
      setFavoriteIds(new Set());
      return;
    }
    let cancelled = false;
    apiClient
      .getFavorites()
      .then((list) => {
        if (cancelled) return;
        const raw = Array.isArray(list) ? list : [];
        const ids = new Set<number>();
        for (const item of raw as { product_id?: number }[]) {
          const pid = typeof item?.product_id === 'number' ? item.product_id : null;
          if (pid != null) ids.add(pid);
        }
        setFavoriteIds(ids);
      })
      .catch(() => {
        if (!cancelled) setFavoriteIds(new Set());
      });
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated]);

  const hasMore = apiOffset < total && total > 0;

  const handleVariantModalAddToCart = useCallback(
    async (p: Product, qty: number, selectedSize?: string, selectedColor?: string) => {
      try {
        const lineImg = cartLineMainImage(p, selectedColor);
        await addToCart({
          product_id: p.id,
          quantity: qty,
          selected_size: selectedSize,
          selected_color: selectedColor,
          line_image_url: lineImg,
          product_data: {
            id: p.id,
            product_id: p.product_id,
            name: p.name,
            price: p.price,
            main_image: lineImg,
            brand_name: p.brand_name,
            available: p.available,
            original_price: p.original_price,
            slug: p.slug,
          },
        });
        pushToast({ title: 'Đã thêm vào giỏ hàng', variant: 'success', durationMs: 2000 });
        trackEvent('add_to_cart_click', { product_id: p.id, quantity: qty, source: 'shop_video_feed' });
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : String(err);
        if (message.includes('Authentication required') || message.includes('401')) {
          pushToast({
            title: 'Vui lòng đăng nhập lại',
            description: 'Phiên đăng nhập đã hết hạn.',
            variant: 'info',
            durationMs: 2500,
          });
          router.push(buildAuthLoginHrefFromFullPath(getBrowserReturnLocation()));
        } else {
          pushToast({ title: 'Không thể thêm vào giỏ hàng', description: message, variant: 'error', durationMs: 3000 });
        }
      }
    },
    [addToCart, pushToast, router]
  );

  const handleVariantModalBuyNow = useCallback((_p: Product, _qty: number, _size?: string, _color?: string) => {}, []);

  const openCartVariantModal = useCallback((p: Product) => {
    setVariantModalProduct(p);
  }, []);

  async function handleToggleFavorite(p: Product) {
    if (!isAuthenticated) {
      pushToast({ title: 'Đăng nhập để lưu yêu thích', variant: 'info', durationMs: 2200 });
      router.push(buildAuthLoginHrefFromFullPath(getBrowserReturnLocation()));
      return;
    }
    if (favoriteBusyId !== null) return;
    const fav = favoriteIds.has(p.id);
    setFavoriteBusyId(p.id);
    try {
      if (fav) {
        await apiClient.removeFromFavorites(p.id);
        setFavoriteIds((prev) => {
          const next = new Set(prev);
          next.delete(p.id);
          return next;
        });
        setProducts((prev) =>
          prev.map((x) => (x.id === p.id ? { ...x, likes: Math.max(0, (x.likes ?? 0) - 1) } : x))
        );
        trackEvent('favorite_remove', { product_id: p.id });
        pushToast({ title: 'Đã bỏ yêu thích', variant: 'success', durationMs: 2000 });
      } else {
        await apiClient.addToFavorites(p.id, {
          id: p.id,
          product_id: p.product_id,
          name: p.name,
          price: p.price,
          main_image: p.main_image,
          brand_name: p.brand_name,
          slug: p.slug,
        });
        setFavoriteIds((prev) => new Set(prev).add(p.id));
        setProducts((prev) =>
          prev.map((x) => (x.id === p.id ? { ...x, likes: (x.likes ?? 0) + 1 } : x))
        );
        trackEvent('favorite_add', { product_id: p.id });
        pushToast({ title: 'Đã thêm vào yêu thích', variant: 'success', durationMs: 2000 });
      }
      await refreshFavorites();
    } catch (err: unknown) {
      if (err instanceof Error && (err.message.includes('Authentication') || err.message.includes('401'))) {
        pushToast({ title: 'Vui lòng đăng nhập lại', variant: 'info', durationMs: 2500 });
        router.push(buildAuthLoginHrefFromFullPath(getBrowserReturnLocation()));
      } else {
        pushToast({
          title: 'Không thể cập nhật yêu thích',
          description: err instanceof Error ? err.message : 'Vui lòng thử lại',
          variant: 'error',
          durationMs: 3000,
        });
      }
    } finally {
      setFavoriteBusyId(null);
    }
  }

  const loadMore = useCallback(async () => {
    if (!hasMore || loadingMore || seed == null) return;
    setLoadingMore(true);
    try {
      await fetchPage(apiOffset, seed, true);
    } finally {
      setLoadingMore(false);
    }
  }, [hasMore, loadingMore, seed, apiOffset, fetchPage]);

  /** Trang đầu toàn SP không phát được trên client → gọi thêm chunk API (giới hạn lần để tránh vòng lặp) */
  useEffect(() => {
    if (loading || loadingMore || error) return;
    if (products.length > 0) {
      emptyPageFetchAttempts.current = 0;
      return;
    }
    if (!hasMore || seed == null) return;
    if (emptyPageFetchAttempts.current >= 10) return;
    emptyPageFetchAttempts.current += 1;
    void loadMore();
  }, [loading, loadingMore, error, products.length, hasMore, seed, loadMore]);

  useEffect(() => {
    if (!hasMore || loadingMore) return;
    const root = scrollRef.current;
    const target = loadMoreSentinelRef.current;
    if (!root || !target) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) void loadMore();
      },
      { root, rootMargin: '80px', threshold: 0 }
    );
    io.observe(target);
    return () => io.disconnect();
  }, [hasMore, loadingMore, loadMore]);

  const onScrollPane = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const h = el.clientHeight || 1;
    const idx = Math.round(el.scrollTop / h);
    setActiveIndex(Math.max(0, Math.min(idx, Math.max(0, products.length - 1))));
  }, [products.length]);

  /** Sản phẩm đang “đứng” trên slide — dùng cho widget nhắn tin (NanoAI) giống trang chi tiết */
  const nanoCtxProduct = products[activeIndex] ?? null;

  const nanoImageList = useMemo(() => {
    const p = nanoCtxProduct;
    if (!p) return [];
    const ordered = [p.main_image, ...(p.images || [])].filter(Boolean) as string[];
    return [...new Set(ordered)];
  }, [nanoCtxProduct]);

  const nanoSku = nanoCtxProduct
    ? (nanoCtxProduct.code?.trim() || nanoCtxProduct.product_id || String(nanoCtxProduct.id)).trim()
    : '';
  const nanoPrimaryImage = nanoImageList[0] || '';
  const nanoSecondaryImage = nanoImageList.find((u) => u !== nanoPrimaryImage) || null;
  /** Khớp PDP: đường dẫn site không encode — widget/chat dùng cùng format */
  const nanoProductPath = nanoCtxProduct
    ? `/products/${(nanoCtxProduct.slug || '').trim() || nanoCtxProduct.product_id}`
    : '';

  return (
    <div className="relative flex h-[100dvh] max-h-[100dvh] flex-col overflow-hidden bg-black w-full md:max-w-lg md:mx-auto md:rounded-xl md:overflow-hidden md:shadow-xl md:my-4 md:h-[min(100dvh,52rem)] md:max-h-[min(100dvh,52rem)] border border-white/10">
      {nanoCtxProduct ? (
        <>
          <NanoAiProductPageContext
            sku={nanoSku}
            primaryImageUrl={nanoPrimaryImage}
            secondaryImageUrl={nanoSecondaryImage}
            productPath={nanoProductPath}
            inventoryId={nanoCtxProduct.inventory_id ?? null}
          />
          {/*
            Giống ProductDetailMobile / ProductGallery: class image_list để widget NanoAI quét ảnh
            nếu không chỉ dựa vào data-ctx-* trên script.
          */}
          <div className="image_list sr-only" aria-hidden>
            {nanoImageList.map((url, idx) => (
              <img key={`${nanoCtxProduct.id}-${idx}`} src={url} alt="" decoding="async" loading="lazy" />
            ))}
          </div>
        </>
      ) : null}

      <header className="pointer-events-none absolute left-0 right-0 top-0 z-40 flex shrink-0 items-center gap-2 bg-gradient-to-b from-black/88 via-black/45 to-transparent px-3 pb-10 pt-[max(0.5rem,env(safe-area-inset-top,0px))] text-white md:rounded-t-xl">
        <button
          type="button"
          onClick={() => router.back()}
          className="pointer-events-auto min-h-[44px] min-w-[44px] rounded-full bg-white/15 flex items-center justify-center hover:bg-white/25 active:bg-white/35"
          aria-label="Quay lại"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div className="pointer-events-none min-w-0 flex-1">
          <h1 className="text-sm font-semibold truncate">Video cùng shop bạn vừa xem</h1>
          <p className="text-[11px] text-white/70 truncate">Theo shop_name · tối đa 8 SP xem gần nhất</p>
        </div>
      </header>

      <div
        ref={scrollRef}
        onScroll={onScrollPane}
        className="h-full min-h-0 flex-1 overflow-y-auto overflow-x-hidden snap-y snap-mandatory overscroll-y-contain touch-pan-y"
        style={{
          WebkitOverflowScrolling: 'touch',
          overscrollBehaviorY: 'contain',
        }}
      >
        {loading && (
          <div className="h-full min-h-full shrink-0 snap-start flex items-center justify-center text-white/80 text-sm px-4">
            Đang tải video gợi ý…
          </div>
        )}

        {!loading && error && (
          <div className="h-full min-h-full shrink-0 snap-start flex flex-col items-center justify-center gap-3 px-6 text-center text-white">
            <p className="text-sm">{error}</p>
            <button
              type="button"
              onClick={() => router.refresh()}
              className="rounded-full bg-[#ea580c] px-4 py-2 text-sm font-medium text-white"
            >
              Thử lại
            </button>
          </div>
        )}

        {!loading && !error && products.length === 0 && (
          <div className="h-full min-h-full shrink-0 snap-start flex flex-col items-center justify-center gap-4 px-6 text-center text-white">
            <p className="text-sm text-white/90">
              Chưa có video trong nhóm shop gợi ý. Xem thêm sản phẩm (ưu tiên SP có link video YouTube hoặc file .mp4).
            </p>
            <Link
              href="/"
              className="rounded-full bg-[#ea580c] px-5 py-2.5 text-sm font-semibold text-white shadow-lg"
            >
              Về trang chủ
            </Link>
          </div>
        )}

        {products.map((product, index) => (
          <section
            key={product.id}
            className="relative h-full min-h-full shrink-0 snap-start snap-always bg-black border-b border-white/10 box-border overflow-hidden"
            aria-label={product.name}
          >
            <div className="absolute inset-0 z-0 min-h-0 overflow-hidden bg-black">
              <VideoPane
                product={product}
                isActive={index === activeIndex}
                soundOn={index === activeIndex ? feedSoundOn : false}
              />
            </div>
            {index === activeIndex ? (
              <FeedSoundToggle soundOn={feedSoundOn} onToggle={toggleFeedSound} />
            ) : null}
            <div className="pointer-events-none absolute bottom-0 left-0 right-0 z-30 bg-gradient-to-t from-black via-black/92 to-transparent p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-16">
              <div className="pointer-events-auto">
                <VideoFeedProductBar
                  product={product}
                  href={productHref(product)}
                  isFavorited={favoriteIds.has(product.id)}
                  favoriteBusy={favoriteBusyId === product.id}
                  cartBusy={cartBusy}
                  canAddToCart={(product.available ?? 0) > 0}
                  onOpenCartModal={() => openCartVariantModal(product)}
                  onToggleFavorite={() => void handleToggleFavorite(product)}
                />
              </div>
            </div>
          </section>
        ))}

        {hasMore && (
          <div
            ref={loadMoreSentinelRef}
            className="h-24 snap-start flex items-center justify-center text-white/60 text-xs shrink-0"
          >
            {loadingMore ? 'Đang tải thêm…' : ''}
          </div>
        )}
      </div>

      {variantModalProduct ? (
        <ProductVariantModal
          product={variantModalProduct}
          isOpen
          onClose={() => setVariantModalProduct(null)}
          onAddToCart={(p, qty, size, color) => void handleVariantModalAddToCart(p, qty, size, color)}
          onBuyNow={handleVariantModalBuyNow}
          isCartLoading={cartBusy}
          action="add"
          displayStockByVariant={displayStockByVariant}
          setDisplayStockByVariant={setDisplayStockByVariant}
        />
      ) : null}
    </div>
  );
}
