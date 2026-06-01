// frontend/app/products/[slug]/components/ProductGallery/ProductGallery.tsx
'use client';

import { useState, useMemo, useCallback, useEffect } from 'react';
import Image from 'next/image';
import { Product } from '@/types/api';
import { mergeProductGalleryPhotoUrls, normalizeProductImageUrl } from '@/lib/product-gallery-merge';
import { getOptimizedImage } from '@/lib/image-utils';
import { reportUnreachableProductMedia } from '@/lib/report-broken-product-media';
import { ProductFillImage, GalleryThumbImage } from '@/components/product-detail/HideOnImageError';
import { hasVideoLink, parseVideoLink, buildYoutubeEmbedSrc } from '@/lib/video-utils';

/** Số ô thumbnail khi thu gọn (tối đa 7); ô thứ 8 là «+N» nếu còn ảnh/video. */
const COLLAPSED_THUMB_COUNT = 7;

interface ProductGalleryProps {
  product: Product;
  selectedImageUrl?: string | null;
  onSelectImage?: (imageUrl: string | null) => void;
}

type GalleryThumbItem =
  | { kind: 'video'; mediaIndex: number }
  | { kind: 'photo'; mediaIndex: number; url: string };

export default function ProductGallery({ product, selectedImageUrl, onSelectImage }: ProductGalleryProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [broken, setBroken] = useState<Record<string, true>>({});
  const [thumbsExpanded, setThumbsExpanded] = useState(false);

  const parsedVideo = parseVideoLink(product.video_link);
  const hasVideo = hasVideoLink(product.video_link);

  const galleryPhotoUrls = useMemo(() => mergeProductGalleryPhotoUrls(product), [product]);

  const visiblePhotoUrls = useMemo(
    () => galleryPhotoUrls.filter((u) => !broken[u]),
    [galleryPhotoUrls, broken],
  );

  const thumbItems = useMemo((): GalleryThumbItem[] => {
    const items: GalleryThumbItem[] = [];
    if (hasVideo) items.push({ kind: 'video', mediaIndex: 0 });
    visiblePhotoUrls.forEach((url, index) => {
      items.push({ kind: 'photo', mediaIndex: hasVideo ? index + 1 : index, url });
    });
    return items;
  }, [hasVideo, visiblePhotoUrls]);

  const markBroken = useCallback(
    (rawUrl: string) => {
      const u = typeof rawUrl === 'string' ? rawUrl.trim() : '';
      if (!u) return;
      reportUnreachableProductMedia(product.id, u);
      setBroken((prev) => (prev[u] ? prev : { ...prev, [u]: true }));
    },
    [product.id],
  );

  useEffect(() => {
    setSelectedIndex((prev) => {
      const n = visiblePhotoUrls.length;
      if (hasVideo) {
        if (prev === 0) return prev;
        if (prev > n) return n >= 1 ? n : 0;
        return prev;
      }
      if (n === 0) return 0;
      if (prev >= n) return n - 1;
      return prev;
    });
  }, [hasVideo, visiblePhotoUrls]);

  useEffect(() => {
    if (thumbItems.length <= COLLAPSED_THUMB_COUNT) {
      setThumbsExpanded(false);
    }
  }, [thumbItems.length]);

  const isShowingVideo = hasVideo && selectedIndex === 0 && !selectedImageUrl?.trim();
  const mediaCount = thumbItems.length;

  const displayPhotoUrl: string | null = (() => {
    if (isShowingVideo) return null;
    if (hasVideo && selectedIndex > 0) return visiblePhotoUrls[selectedIndex - 1] ?? null;
    if (!hasVideo) return visiblePhotoUrls[selectedIndex] ?? null;
    return null;
  })();

  const variantPick = selectedImageUrl?.trim() || null;
  const variantAbsolute = variantPick ? normalizeProductImageUrl(variantPick) : null;
  const logicalMainUrl = variantAbsolute || displayPhotoUrl;
  const mainRaw =
    logicalMainUrl && broken[logicalMainUrl]
      ? (visiblePhotoUrls[0] ?? null)
      : logicalMainUrl;

  const overflowCount = thumbsExpanded ? 0 : Math.max(0, thumbItems.length - COLLAPSED_THUMB_COUNT);
  const visibleThumbItems = thumbsExpanded
    ? thumbItems
    : thumbItems.slice(0, COLLAPSED_THUMB_COUNT);

  const selectMedia = (mediaIndex: number, photoUrl?: string) => {
    setSelectedIndex(mediaIndex);
    onSelectImage?.(photoUrl ?? null);
  };

  const thumbSizeClass = 'w-16 h-16';

  return (
    <div className="image_list min-w-0 flex flex-col gap-2">
      <div className="min-w-0 w-full">
        {isShowingVideo && parsedVideo ? (
          <div className="aspect-square bg-gray-100 rounded-lg overflow-hidden">
            {parsedVideo.kind === 'youtube' ? (
              <iframe
                title={`Video ${product.name}`}
                src={buildYoutubeEmbedSrc(parsedVideo.urlOrId)}
                className="w-full h-full"
                loading="lazy"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share; fullscreen"
                allowFullScreen
                referrerPolicy="strict-origin-when-cross-origin"
              />
            ) : (
              <video
                src={parsedVideo.urlOrId}
                controls
                className="w-full h-full object-contain bg-black"
                playsInline
              />
            )}
          </div>
        ) : mainRaw ? (
          <ProductFillImage
            src={getOptimizedImage(mainRaw, { width: 900, height: 900, hideProductPng: true })}
            alt={product.name}
            frameClassName="aspect-square relative w-full overflow-hidden rounded-lg bg-gray-100"
            onBroken={() => markBroken(mainRaw)}
          />
        ) : null}
      </div>

      {mediaCount > 1 && (
        <div className="min-w-0">
          <nav
            className="product-gallery-thumb-strip flex items-center gap-2 overflow-x-auto scrollbar-hide snap-x snap-mandatory py-1"
            aria-label="Thư viện ảnh sản phẩm"
          >
            {visibleThumbItems.map((item) =>
              item.kind === 'video' ? (
                <button
                  key="video"
                  type="button"
                  onClick={() => selectMedia(0)}
                  className={`relative flex-shrink-0 snap-center ${thumbSizeClass} rounded-lg border-2 transition-all overflow-hidden ${
                    selectedIndex === 0
                      ? 'border-[#ea580c] scale-[1.02] shadow-md'
                      : 'border-gray-300 hover:border-gray-400'
                  }`}
                  aria-label="Xem video"
                  aria-current={selectedIndex === 0 ? 'true' : undefined}
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
                  sizeClass={`${thumbSizeClass} snap-center flex-shrink-0`}
                  selectedClassName="border-[#ea580c] scale-[1.02] shadow-md"
                  unselectedClassName="border-gray-300 hover:border-gray-400"
                  selected={selectedIndex === item.mediaIndex}
                  onClick={() => selectMedia(item.mediaIndex, item.url)}
                  onBroken={() => markBroken(item.url)}
                />
              ),
            )}

            {overflowCount > 0 && (
              <button
                type="button"
                onClick={() => setThumbsExpanded(true)}
                className={`flex-shrink-0 snap-center ${thumbSizeClass} rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 text-xs font-semibold text-gray-600 hover:border-[#ea580c] hover:text-[#ea580c] hover:bg-orange-50 transition-colors`}
                aria-label={`Xem thêm ${overflowCount} ảnh`}
              >
                +{overflowCount}
              </button>
            )}
          </nav>

          {thumbsExpanded && thumbItems.length > COLLAPSED_THUMB_COUNT && (
            <div className="flex justify-end mt-1">
              <button
                type="button"
                onClick={() => setThumbsExpanded(false)}
                className="text-xs font-medium text-gray-500 hover:text-[#ea580c] transition-colors"
              >
                Thu gọn
              </button>
            </div>
          )}
        </div>
      )}

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
