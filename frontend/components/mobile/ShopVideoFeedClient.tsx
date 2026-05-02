'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { useRouter, useSearchParams } from 'next/navigation';
import type { Product } from '@/types/api';
import { apiClient } from '@/lib/api-client';
import { parseVideoLink, buildYoutubeEmbedSrc } from '@/lib/video-utils';
import { formatPrice } from '@/lib/utils';

function productHref(p: Product): string {
  const s = (p.slug || '').trim();
  if (s) return `/products/${encodeURIComponent(s)}`;
  return `/products/${encodeURIComponent(p.product_id)}`;
}

function VideoPane({ product, isActive }: { product: Product; isActive: boolean }) {
  const parsed = parseVideoLink(product.video_link);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const el = videoRef.current;
    if (!el || parsed?.kind !== 'cdn_mp4') return;
    if (isActive) {
      el.muted = true;
      void el.play().catch(() => {});
    } else {
      el.pause();
    }
  }, [isActive, parsed?.kind]);

  if (!parsed) return null;

  if (parsed.kind === 'youtube') {
    const src = buildYoutubeEmbedSrc(parsed.urlOrId, { autoplay: isActive, muted: true });
    if (!isActive && parsed.thumbUrl) {
      return (
        <div className="relative w-full h-full bg-black">
          <Image src={parsed.thumbUrl} alt="" fill className="object-contain" sizes="100vw" unoptimized />
          <div className="absolute inset-0 flex items-center justify-center bg-black/35">
            <span className="rounded-full bg-white/90 text-gray-900 px-4 py-2 text-sm font-medium shadow-lg">
              Vuốt để xem
            </span>
          </div>
        </div>
      );
    }
    return (
      <iframe
        title={product.name}
        src={src}
        className="absolute inset-0 h-full w-full border-0 bg-black"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
        allowFullScreen
      />
    );
  }

  return (
    <video
      ref={videoRef}
      src={parsed.urlOrId}
      className="absolute inset-0 h-full w-full object-contain bg-black"
      playsInline
      loop
      muted
      controls={isActive}
    />
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

  const [products, setProducts] = useState<Product[]>([]);
  const [total, setTotal] = useState(0);
  const [seed, setSeed] = useState<number | null>(parsedSeed ?? null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const loadMoreSentinelRef = useRef<HTMLDivElement>(null);

  const fetchPage = useCallback(
    async (offset: number, nextSeed: number | undefined, append: boolean) => {
      const res = await apiClient.getProductsSameShopAsRecentViews(15, offset, nextSeed ?? null, true);
      const batch = res.products || [];
      if (append) {
        setProducts((prev) => {
          const seen = new Set(prev.map((p) => p.id));
          const extra = batch.filter((p) => !seen.has(p.id));
          return [...prev, ...extra];
        });
      } else {
        setProducts(batch);
      }
      setTotal(res.total ?? 0);
      if (res.seed != null) setSeed(res.seed);
      return batch.length;
    },
    []
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchPage(0, parsedSeed, false)
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Không tải được danh sách video');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [parsedSeed, fetchPage]);

  const hasMore = products.length < total && total > 0;

  const loadMore = useCallback(async () => {
    if (!hasMore || loadingMore || seed == null) return;
    setLoadingMore(true);
    try {
      await fetchPage(products.length, seed, true);
    } finally {
      setLoadingMore(false);
    }
  }, [hasMore, loadingMore, seed, products.length, fetchPage]);

  useEffect(() => {
    if (!hasMore || loadingMore || products.length === 0) return;
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
  }, [hasMore, loadingMore, products.length, loadMore]);

  const onScrollPane = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const h = el.clientHeight || 1;
    const idx = Math.round(el.scrollTop / h);
    setActiveIndex(Math.max(0, Math.min(idx, Math.max(0, products.length - 1))));
  }, [products.length]);

  return (
    <div className="flex min-h-[100dvh] flex-col bg-black w-full md:max-w-lg md:mx-auto md:rounded-xl md:overflow-hidden md:shadow-xl md:my-4 border border-white/10">
      <header className="flex shrink-0 items-center gap-2 px-3 py-2 pt-[max(0.5rem,env(safe-area-inset-top,0px))] bg-black/80 text-white md:rounded-t-xl border-b border-white/10">
        <button
          type="button"
          onClick={() => router.back()}
          className="min-h-[44px] min-w-[44px] rounded-full bg-white/15 flex items-center justify-center hover:bg-white/25 active:bg-white/35"
          aria-label="Quay lại"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div className="min-w-0 flex-1">
          <h1 className="text-sm font-semibold truncate">Video cùng shop bạn vừa xem</h1>
          <p className="text-[11px] text-white/70 truncate">Theo shop_name · tối đa 8 SP xem gần nhất</p>
        </div>
      </header>

      <div
        ref={scrollRef}
        onScroll={onScrollPane}
        className="flex-1 overflow-y-auto snap-y snap-mandatory overscroll-y-contain"
        style={{ WebkitOverflowScrolling: 'touch' }}
      >
        {loading && (
          <div className="h-[calc(100dvh-52px)] md:min-h-[70vh] snap-start flex items-center justify-center text-white/80 text-sm">
            Đang tải video gợi ý…
          </div>
        )}

        {!loading && error && (
          <div className="h-[calc(100dvh-52px)] snap-start flex flex-col items-center justify-center gap-3 px-6 text-center text-white">
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
          <div className="h-[calc(100dvh-52px)] snap-start flex flex-col items-center justify-center gap-4 px-6 text-center text-white">
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
            className="relative h-[calc(100dvh-52px)] md:min-h-[min(100dvh-52px,720px)] snap-start snap-always flex flex-col bg-black border-b border-white/10"
            aria-label={product.name}
          >
            <div className="relative flex-1 min-h-0">
              {parseVideoLink(product.video_link) ? (
                <VideoPane product={product} isActive={index === activeIndex} />
              ) : (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-neutral-900 px-6 text-center text-white/85 text-sm">
                  <p>Không phát được định dạng video này.</p>
                  <Link
                    href={productHref(product)}
                    className="rounded-full bg-[#ea580c] px-4 py-2 text-xs font-semibold text-white"
                  >
                    Xem chi tiết sản phẩm
                  </Link>
                </div>
              )}
            </div>
            <div className="shrink-0 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] bg-gradient-to-t from-black via-black/95 to-transparent">
              <p className="text-white text-sm font-medium line-clamp-2 mb-1">{product.name}</p>
              {product.shop_name ? (
                <p className="text-[11px] text-white/65 mb-2 truncate">{product.shop_name}</p>
              ) : null}
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[#ea580c] font-bold">{formatPrice(product.price)}</span>
                <Link
                  href={productHref(product)}
                  className="ml-auto rounded-full bg-white text-gray-900 px-4 py-2 text-xs font-semibold shadow-md active:scale-[0.98]"
                >
                  Xem sản phẩm
                </Link>
              </div>
            </div>
          </section>
        ))}

        {hasMore && products.length > 0 && (
          <div
            ref={loadMoreSentinelRef}
            className="h-24 snap-start flex items-center justify-center text-white/60 text-xs"
          >
            {loadingMore ? 'Đang tải thêm…' : ''}
          </div>
        )}
      </div>
    </div>
  );
}
