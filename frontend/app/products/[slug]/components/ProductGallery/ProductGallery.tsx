// frontend/app/products/[slug]/components/ProductGallery/ProductGallery.tsx
'use client';

import { useState, useMemo, useCallback, useEffect } from 'react';
import Image from 'next/image';
import { Product } from '@/types/api';
import { mergeProductGalleryPhotoUrls, normalizeProductImageUrl } from '@/lib/product-gallery-merge';
import { getOptimizedImage } from '@/lib/image-utils';
import { reportUnreachableProductMedia } from '@/lib/report-broken-product-media';
import { hasVideoLink, parseVideoLink, buildYoutubeEmbedSrc } from '@/lib/video-utils';

interface ProductGalleryProps {
  product: Product;
  selectedImageUrl?: string | null;
  onSelectImage?: (imageUrl: string | null) => void;
}

export default function ProductGallery({ product, selectedImageUrl, onSelectImage }: ProductGalleryProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [broken, setBroken] = useState<Record<string, true>>({});

  const parsedVideo = parseVideoLink(product.video_link);
  const hasVideo = hasVideoLink(product.video_link);

  const galleryPhotoUrls = useMemo(() => mergeProductGalleryPhotoUrls(product), [product]);

  const visiblePhotoUrls = useMemo(
    () => galleryPhotoUrls.filter((u) => !broken[u]),
    [galleryPhotoUrls, broken],
  );

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

  const isShowingVideo = hasVideo && selectedIndex === 0 && !selectedImageUrl?.trim();
  const mediaCount = hasVideo ? 1 + visiblePhotoUrls.length : visiblePhotoUrls.length;

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

  const showMainFrame = (isShowingVideo && parsedVideo) || mainRaw;

  return (
    <div className="space-y-2 image_list">
      {showMainFrame ? (
      <div className="aspect-square bg-gray-100 rounded-lg overflow-hidden">
        {isShowingVideo && parsedVideo ? (
          parsedVideo.kind === 'youtube' ? (
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
          )
        ) : mainRaw ? (
          <Image
            src={getOptimizedImage(mainRaw, { width: 900, height: 900 })}
            alt={product.name}
            width={900}
            height={900}
            className="w-full h-full object-cover"
            priority
            onError={() => markBroken(mainRaw)}
          />
        ) : null}
      </div>
      ) : null}

      {mediaCount > 1 && (
        <div className="flex space-x-1.5 overflow-x-auto pb-1">
          {hasVideo && (
            <button
              type="button"
              onClick={() => {
                setSelectedIndex(0);
                onSelectImage?.(null);
              }}
              className={`flex-shrink-0 w-14 h-14 rounded border-2 transition-all ${
                selectedIndex === 0 ? 'border-blue-500 scale-105 shadow-md' : 'border-gray-300 hover:border-gray-400'
              }`}
              aria-label="Xem video"
            >
              <div className="relative w-full h-full bg-gray-800 rounded overflow-hidden">
                {parsedVideo?.thumbUrl ? (
                  <Image
                    src={parsedVideo.thumbUrl}
                    alt="Video"
                    width={64}
                    height={64}
                    className="w-full h-full object-cover"
                  />
                ) : null}
                <span className="absolute inset-0 flex items-center justify-center">
                  <svg className="w-7 h-7 text-white drop-shadow" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M8 5v14l11-7z" />
                  </svg>
                </span>
              </div>
            </button>
          )}
          {visiblePhotoUrls.map((image, index) => {
            const mediaIndex = hasVideo ? index + 1 : index;
            return (
              <button
                key={image}
                type="button"
                onClick={() => {
                  setSelectedIndex(mediaIndex);
                  onSelectImage?.(image);
                }}
                className={`flex-shrink-0 w-14 h-14 rounded border-2 transition-all ${
                  selectedIndex === mediaIndex ? 'border-blue-500 scale-105 shadow-md' : 'border-gray-300 hover:border-gray-400'
                }`}
                aria-label={`Xem ảnh ${index + 1}`}
              >
                <div className="relative w-full h-full">
                  <Image
                    src={getOptimizedImage(image, { width: 64, height: 64 })}
                    alt={`${product.name} ${index + 1}`}
                    width={64}
                    height={64}
                    className="w-full h-full object-cover rounded"
                    onError={() => markBroken(image)}
                  />
                </div>
              </button>
            );
          })}
        </div>
      )}

      {process.env.NODE_ENV === 'development' && (
        <div className="text-xs text-gray-500 mt-2 p-2 bg-gray-50 rounded">
          <div>
            📊 Debug: main_image ✓/✗, images: {product.images?.length ?? 0}, gallery: {product.gallery?.length ?? 0}, URLs:{' '}
            {galleryPhotoUrls.length} → hiển thị {visiblePhotoUrls.length}, media: {mediaCount}, video: {hasVideo ? '✓' : '✗'}
          </div>
        </div>
      )}
    </div>
  );
}
