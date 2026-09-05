'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';

import { apiClient } from '@/lib/api-client';
import { trackEvent } from '@/lib/analytics';
import type { MarketingBannerItem } from '@/types/api';

type Props = {
  refreshKey: string;
};

export default function MarketingBannerCarousel({ refreshKey }: Props) {
  const [items, setItems] = useState<MarketingBannerItem[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [paused, setPaused] = useState(false);
  const viewedCampaign = useRef<string | null>(null);
  const touchStartX = useRef<number | null>(null);
  const didSwipe = useRef(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const response = await apiClient.getCurrentMarketingBanners();
      setItems(response.items ?? []);
      setActiveIndex(0);
    } catch {
      setItems([]);
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  useEffect(() => {
    if (paused || items.length < 2) return;
    const timer = window.setInterval(() => {
      setActiveIndex((index) => (index + 1) % items.length);
    }, 6500);
    return () => window.clearInterval(timer);
  }, [items.length, paused]);

  const active = items[activeIndex] ?? null;
  useEffect(() => {
    if (activeIndex >= items.length) setActiveIndex(0);
  }, [activeIndex, items.length]);
  useEffect(() => {
    if (!active || viewedCampaign.current === active.campaign_key) return;
    viewedCampaign.current = active.campaign_key;
    trackEvent('marketing_banner_view', {
      kind: active.kind,
      campaign_key: active.campaign_key,
      discount_percent: active.discount_percent,
    });
  }, [active]);

  if (loading) {
    return (
      <div
        className="mb-4 aspect-[21/9] w-full animate-pulse rounded-xl bg-orange-100 md:mb-5"
        aria-label="Đang tải banner ưu đãi"
      />
    );
  }

  if (error) {
    return (
      <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
        Chưa tải được banner ưu đãi.{' '}
        <button type="button" onClick={() => void load()} className="font-medium underline">
          Thử lại
        </button>
      </div>
    );
  }

  if (!active) return null;

  const move = (direction: number) => {
    setActiveIndex((index) => (index + direction + items.length) % items.length);
  };
  const destination = '/#san-pham-cung-shop';

  return (
    <section
      className="relative mb-4 overflow-hidden rounded-xl border border-orange-100 bg-white shadow-sm md:mb-5"
      aria-label="Ưu đãi dành cho bạn"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
      onTouchStart={(event) => {
        touchStartX.current = event.touches[0]?.clientX ?? null;
        didSwipe.current = false;
        setPaused(true);
      }}
      onTouchEnd={(event) => {
        const start = touchStartX.current;
        const end = event.changedTouches[0]?.clientX;
        touchStartX.current = null;
        setPaused(false);
        if (start == null || end == null || items.length < 2) return;
        const distance = end - start;
        if (Math.abs(distance) < 40) return;
        didSwipe.current = true;
        move(distance < 0 ? 1 : -1);
      }}
    >
      <div className="relative aspect-[21/9] w-full overflow-hidden">
        {items.map((item, index) => (
          <Link
            key={item.id}
            href={destination}
            tabIndex={index === activeIndex ? 0 : -1}
            aria-hidden={index !== activeIndex}
            className={`absolute inset-0 block transition-opacity duration-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-500 ${
              index === activeIndex ? 'z-[1] opacity-100' : 'pointer-events-none opacity-0'
            }`}
            onClick={(event) => {
              if (didSwipe.current) {
                event.preventDefault();
                didSwipe.current = false;
                return;
              }
              trackEvent('marketing_banner_click', {
                kind: item.kind,
                campaign_key: item.campaign_key,
              });
            }}
            aria-label={`${item.kind === 'birthday' ? 'Nhận quà sinh nhật' : 'Xem sản phẩm sale'} giảm ${item.discount_percent}%`}
          >
            {/* Render sẵn cả hai ảnh để vuốt/chuyển không giữ nhầm ảnh cũ trong lúc tải. */}
            <img
              src={item.image_url}
              alt={
                item.kind === 'birthday'
                  ? `Banner mừng sinh nhật ${item.date_key}, tặng ${item.discount_percent}%`
                  : `Banner sale ${item.date_key}, giảm ${item.discount_percent}%`
              }
              width={2100}
              height={900}
              className="block h-full w-full object-contain"
              loading="eager"
              decoding="async"
              onError={() =>
                setItems((current) => current.filter((candidate) => candidate.id !== item.id))
              }
            />
          </Link>
        ))}
      </div>

      {active.greeting ? (
        <p className="border-t border-orange-100 bg-orange-50/80 px-3 py-2 text-center text-sm font-semibold text-orange-900">
          {active.greeting}
        </p>
      ) : null}

      {items.length > 1 ? (
        <>
          <button
            type="button"
            onClick={() => move(-1)}
            className="absolute left-2 top-1/2 z-[2] -translate-y-1/2 rounded-full bg-white/90 px-2.5 py-1.5 text-lg text-orange-700 shadow hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-500"
            aria-label="Banner trước"
          >
            ‹
          </button>
          <button
            type="button"
            onClick={() => move(1)}
            className="absolute right-2 top-1/2 z-[2] -translate-y-1/2 rounded-full bg-white/90 px-2.5 py-1.5 text-lg text-orange-700 shadow hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-500"
            aria-label="Banner tiếp theo"
          >
            ›
          </button>
          <div className="absolute bottom-2 left-1/2 z-[2] flex -translate-x-1/2 gap-1.5">
            {items.map((item, index) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setActiveIndex(index)}
                aria-label={`Xem banner ${index + 1}`}
                aria-current={index === activeIndex ? 'true' : undefined}
                className={`h-1.5 rounded-full shadow-sm transition-all ${
                  index === activeIndex ? 'w-5 bg-orange-600' : 'w-1.5 bg-white/90'
                }`}
              />
            ))}
          </div>
        </>
      ) : null}
    </section>
  );
}
