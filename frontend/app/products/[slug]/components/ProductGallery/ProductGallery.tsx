// frontend/app/products/[slug]/components/ProductGallery/ProductGallery.tsx
'use client';

import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import Image from 'next/image';
import { Product } from '@/types/api';
import { mergeProductGalleryPhotoUrls, normalizeProductImageUrl } from '@/lib/product-gallery-merge';
import { getOptimizedImage } from '@/lib/image-utils';
import { reportUnreachableProductMedia } from '@/lib/report-broken-product-media';
import { ProductFillImage, GalleryThumbImage } from '@/components/product-detail/HideOnImageError';
import MobileProductMediaCarousel, {
  MobileProductMediaSlide,
  type MobileProductMediaCarouselHandle,
} from '@/components/product-detail/MobileProductMediaCarousel';
import { hasVideoLink, parseVideoLink, buildYoutubeEmbedSrc } from '@/lib/video-utils';

interface ProductGalleryProps {
  product: Product;
  selectedImageUrl?: string | null;
  onSelectImage?: (imageUrl: string | null) => void;
  /** bleed = full-width swipe hero (mobile ladipage / compact PDP) */
  layout?: 'default' | 'bleed';
}

type GalleryThumbItem =
  | { kind: 'video'; mediaIndex: number }
  | { kind: 'photo'; mediaIndex: number; url: string };

export default function ProductGallery({
  product,
  selectedImageUrl,
  onSelectImage,
  layout = 'default',
}: ProductGalleryProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [broken, setBroken] = useState<Record<string, true>>({});
  const mediaCarouselRef = useRef<MobileProductMediaCarouselHandle>(null);
  const thumbStripRef = useRef<HTMLElement>(null);
  const thumbButtonRefs = useRef<Record<number, HTMLButtonElement | null>>({});
  const isBleed = layout === 'bleed';

  const parsedVideo = parseVideoLink(product.video_link);
  const hasVideo = hasVideoLink(product.video_link);

  const galleryPhotoUrls = useMemo(() => mergeProductGalleryPhotoUrls(product), [product]);

  const visiblePhotoUrls = useMemo(
    () => galleryPhotoUrls.filter((u) => !broken[u]),
    [galleryPhotoUrls, broken],
  );

  // Thứ tự: ảnh đầu → video → ảnh còn lại. Không có ảnh thì video ở index 0.
  const videoIndex = hasVideo ? (visiblePhotoUrls.length > 0 ? 1 : 0) : -1;

  const thumbItems = useMemo((): GalleryThumbItem[] => {
    const items: GalleryThumbItem[] = [];
    if (visiblePhotoUrls.length > 0) {
      items.push({ kind: 'photo', mediaIndex: 0, url: visiblePhotoUrls[0] });
    }
    if (hasVideo) {
      items.push({ kind: 'video', mediaIndex: videoIndex });
    }
    visiblePhotoUrls.slice(1).forEach((url, index) => {
      const photoIndex = index + 1;
      items.push({
        kind: 'photo',
        mediaIndex: hasVideo ? photoIndex + 1 : photoIndex,
        url,
      });
    });
    return items;
  }, [hasVideo, visiblePhotoUrls, videoIndex]);

  const markBroken = useCallback(
    (rawUrl: string) => {
      const u = typeof rawUrl === 'string' ? rawUrl.trim() : '';
      if (!u) return;
      reportUnreachableProductMedia(product.id, u);
      setBroken((prev) => (prev[u] ? prev : { ...prev, [u]: true }));
    },
    [product.id],
  );

  const mediaCount = thumbItems.length;
  const firstPhotoUrl = visiblePhotoUrls[0] ?? null;
  const restPhotoUrls = visiblePhotoUrls.slice(1);

  useEffect(() => {
    setSelectedIndex((prev) => {
      if (mediaCount <= 0) return 0;
      if (prev >= mediaCount) return mediaCount - 1;
      return prev;
    });
  }, [mediaCount]);

  // Khi chọn ảnh màu từ ProductInfo → nhảy tới slide ảnh tương ứng
  useEffect(() => {
    const pick = selectedImageUrl?.trim();
    if (!pick) return;
    const abs = normalizeProductImageUrl(pick);
    const photoIdx = visiblePhotoUrls.findIndex(
      (u) => u === abs || u === pick || normalizeProductImageUrl(u) === abs,
    );
    if (photoIdx < 0) return;
    const mediaIdx = !hasVideo || visiblePhotoUrls.length === 0
      ? photoIdx
      : photoIdx === 0
        ? 0
        : photoIdx + 1;
    setSelectedIndex(mediaIdx);
    mediaCarouselRef.current?.scrollToIndex(mediaIdx, 'smooth');
  }, [selectedImageUrl, visiblePhotoUrls, hasVideo]);

  useEffect(() => {
    if (!isBleed) return;
    const btn = thumbButtonRefs.current[selectedIndex];
    const strip = thumbStripRef.current;
    if (!btn || !strip) return;
    const stripRect = strip.getBoundingClientRect();
    const btnRect = btn.getBoundingClientRect();
    const left = btn.offsetLeft - strip.offsetLeft - (stripRect.width - btnRect.width) / 2;
    strip.scrollTo({ left: Math.max(0, left), behavior: 'auto' });
  }, [selectedIndex, isBleed, mediaCount]);

  const isShowingVideo = hasVideo && selectedIndex === videoIndex && !selectedImageUrl?.trim();

  const displayPhotoUrl: string | null = (() => {
    if (isShowingVideo) return null;
    if (!hasVideo) return visiblePhotoUrls[selectedIndex] ?? null;
    if (selectedIndex < videoIndex) return visiblePhotoUrls[selectedIndex] ?? null;
    if (selectedIndex > videoIndex) return visiblePhotoUrls[selectedIndex - 1] ?? null;
    return null;
  })();

  const variantPick = selectedImageUrl?.trim() || null;
  const variantAbsolute = variantPick ? normalizeProductImageUrl(variantPick) : null;
  const logicalMainUrl = variantAbsolute || displayPhotoUrl;
  const mainRaw =
    logicalMainUrl && broken[logicalMainUrl]
      ? (visiblePhotoUrls[0] ?? null)
      : logicalMainUrl;

  const selectMedia = (mediaIndex: number, photoUrl?: string) => {
    setSelectedIndex(mediaIndex);
    mediaCarouselRef.current?.scrollToIndex(mediaIndex);
    onSelectImage?.(photoUrl ?? null);
  };

  const handleCarouselIndexChange = (index: number) => {
    setSelectedIndex(index);
    const item = thumbItems[index];
    if (item?.kind === 'photo') onSelectImage?.(item.url);
    else onSelectImage?.(null);
  };

  const thumbSizeClass = isBleed ? 'w-14 h-14' : 'w-16 h-16';
  // bleed: vuông full-width sát mép (chiều cao = 100vw, không inset)
  const frameAspect = isBleed
    ? 'aspect-square relative w-full overflow-hidden bg-gray-100'
    : 'aspect-square relative w-full overflow-hidden bg-gray-100 lg:rounded-lg';

  const renderVideoSlide = () => {
    if (!parsedVideo) return null;
    return (
      <div className={frameAspect}>
        {parsedVideo.kind === 'youtube' ? (
          <iframe
            title={`Video ${product.name}`}
            src={buildYoutubeEmbedSrc(parsedVideo.urlOrId)}
            className="absolute inset-0 w-full h-full"
            loading="lazy"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share; fullscreen"
            allowFullScreen
            referrerPolicy="strict-origin-when-cross-origin"
          />
        ) : (
          <video
            src={parsedVideo.urlOrId}
            controls
            className="absolute inset-0 w-full h-full object-contain bg-black"
            playsInline
          />
        )}
      </div>
    );
  };

  const renderPhotoSlide = (url: string, priority = false) => (
    <ProductFillImage
      src={getOptimizedImage(url, {
        width: isBleed ? 720 : 900,
        height: isBleed ? 720 : 900,
        hideProductPng: true,
      })}
      alt={product.name}
      frameClassName={frameAspect}
      priority={priority}
      onBroken={() => markBroken(url)}
    />
  );

  const thumbStrip = mediaCount > 1 ? (
    <nav
      ref={thumbStripRef}
      className={`product-gallery-thumb-strip flex items-center gap-2 overflow-x-auto scrollbar-hide snap-x snap-mandatory ${
        isBleed ? 'py-2 px-4' : 'py-1'
      }`}
      style={{ WebkitOverflowScrolling: 'touch' }}
      aria-label="Thư viện ảnh sản phẩm"
    >
      {thumbItems.map((item) =>
        item.kind === 'video' ? (
          <button
            key="video"
            ref={(el) => {
              thumbButtonRefs.current[item.mediaIndex] = el;
            }}
            type="button"
            onClick={() => selectMedia(item.mediaIndex)}
            className={`relative flex-shrink-0 snap-center snap-always ${thumbSizeClass} rounded-lg border-2 transition-all overflow-hidden ${
              selectedIndex === item.mediaIndex
                ? 'border-[#ea580c] scale-[1.02] shadow-md'
                : 'border-gray-300 hover:border-gray-400'
            }`}
            aria-label="Xem video"
            aria-current={selectedIndex === item.mediaIndex ? 'true' : undefined}
          >
            <div className="relative w-full h-full bg-gray-800">
              {parsedVideo?.thumbUrl ? (
                <Image
                  src={parsedVideo.thumbUrl}
                  alt=""
                  width={64}
                  height={64}
                  className="w-full h-full object-cover"
                />
              ) : null}
              <span className="absolute inset-0 flex items-center justify-center">
                <svg className="w-6 h-6 text-white drop-shadow" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M8 5v14l11-7z" />
                </svg>
              </span>
            </div>
          </button>
        ) : (
          <GalleryThumbImage
            key={item.url}
            src={getOptimizedImage(item.url, { width: 64, height: 64, hideProductPng: true })}
            sizeClass={`${thumbSizeClass} snap-center snap-always flex-shrink-0`}
            selectedClassName="border-[#ea580c] scale-[1.02] shadow-md"
            unselectedClassName="border-gray-300 hover:border-gray-400"
            selected={selectedIndex === item.mediaIndex}
            onClick={() => selectMedia(item.mediaIndex, item.url)}
            onBroken={() => markBroken(item.url)}
            buttonRef={(el) => {
              thumbButtonRefs.current[item.mediaIndex] = el;
            }}
          />
        ),
      )}
    </nav>
  ) : null;

  if (isBleed) {
    return (
      <div className="image_list min-w-0 w-full overflow-x-hidden bg-white">
        {mediaCount > 0 && (
          <div className="relative w-full min-w-0 overflow-hidden">
            <MobileProductMediaCarousel
              ref={mediaCarouselRef}
              selectedIndex={selectedIndex}
              onSelectedIndexChange={handleCarouselIndexChange}
              slideCount={mediaCount}
              className="min-w-0"
              renderOverlay={
                mediaCount > 1
                  ? (liveIndex) => (
                      <>
                        <div className="pointer-events-none absolute top-2.5 right-2.5 z-[1] rounded-full bg-black/55 px-2 py-0.5 text-[10px] font-medium tabular-nums text-white">
                          {liveIndex + 1}/{mediaCount}
                        </div>
                        <div className="pointer-events-none absolute bottom-2.5 left-0 right-0 z-[1] flex items-center justify-center gap-1">
                          {Array.from({ length: Math.min(mediaCount, 10) }, (_, i) => (
                            <span
                              key={i}
                              className={
                                i === liveIndex
                                  ? 'h-1 w-3.5 rounded-full bg-white shadow-sm'
                                  : 'h-1 w-1 rounded-full bg-white/55'
                              }
                            />
                          ))}
                        </div>
                      </>
                    )
                  : undefined
              }
            >
              {firstPhotoUrl ? (
                <MobileProductMediaSlide key={firstPhotoUrl} className="overflow-hidden bg-gray-100">
                  {renderPhotoSlide(firstPhotoUrl, true)}
                </MobileProductMediaSlide>
              ) : null}
              {hasVideo && parsedVideo ? (
                <MobileProductMediaSlide className="overflow-hidden bg-gray-100">
                  {renderVideoSlide()}
                </MobileProductMediaSlide>
              ) : null}
              {restPhotoUrls.map((img) => (
                <MobileProductMediaSlide key={img} className="overflow-hidden bg-gray-100">
                  {renderPhotoSlide(img)}
                </MobileProductMediaSlide>
              ))}
            </MobileProductMediaCarousel>
          </div>
        )}
        {thumbStrip}
      </div>
    );
  }

  return (
    <div className="image_list min-w-0 flex flex-col gap-2">
      <div className="min-w-0 w-full lg:rounded-lg lg:overflow-hidden">
        {isShowingVideo && parsedVideo ? (
          renderVideoSlide()
        ) : mainRaw ? (
          renderPhotoSlide(mainRaw, true)
        ) : null}
      </div>

      {thumbStrip}

      {process.env.NODE_ENV === 'development' && (
        <div className="text-xs text-gray-500 mt-2 p-2 bg-gray-50 rounded">
          <div>
            📊 Debug: images: {product.images?.length ?? 0}, URLs: {galleryPhotoUrls.length} →{' '}
            {visiblePhotoUrls.length}, media: {mediaCount}, video: {hasVideo ? '✓' : '✗'}
          </div>
        </div>
      )}
    </div>
  );
}
