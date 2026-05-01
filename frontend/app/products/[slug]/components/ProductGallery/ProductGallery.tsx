// frontend/app/products/[slug]/components/ProductGallery/ProductGallery.tsx
'use client';

import { useState } from 'react';
import Image from 'next/image';
import { Product } from '@/types/api';
import { getOptimizedImage } from '@/lib/image-utils';
import { hasVideoLink, parseVideoLink, buildYoutubeEmbedSrc } from '@/lib/video-utils';

interface ProductGalleryProps {
  product: Product;
  selectedImageUrl?: string | null;
  onSelectImage?: (imageUrl: string | null) => void;
}

export default function ProductGallery({ product, selectedImageUrl, onSelectImage }: ProductGalleryProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);

  const parsedVideo = parseVideoLink(product.video_link);
  const hasVideo = hasVideoLink(product.video_link);

  // CHỈ lấy thư viện ảnh (images từ cột P - gallery_images)
  const getProductImages = () => {
    const images: string[] = [];
    if (product.main_image) images.push(product.main_image);
    if (product.images?.length) {
      const unique = product.images.filter((img) => img !== product.main_image);
      images.push(...unique);
    }
    if (images.length === 0) return [getOptimizedImage(undefined)];
    return images;
  };

  const images = getProductImages();
  // Khi có video: media = [video, ...ảnh]. Video luôn hiển thị đầu tiên (index 0).
  const mediaCount = hasVideo ? 1 + images.length : images.length;

  const isShowingVideo = hasVideo && selectedIndex === 0 && !selectedImageUrl;
  const displayImageUrl = hasVideo
    ? selectedIndex === 0
      ? (parsedVideo?.thumbUrl || images[0])
      : images[selectedIndex - 1]
    : images[selectedIndex];
  const effectiveImageUrl = selectedImageUrl && selectedImageUrl.trim() ? selectedImageUrl : displayImageUrl;

  return (
    <div className="space-y-2 image_list">
      {/* Khung ảnh/video chính — class image_list để NanoAI widget có thể quét ảnh nếu không dùng data-ctx */}
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
        ) : (
          <Image
            src={getOptimizedImage(effectiveImageUrl, { width: 900, height: 900 })}
            alt={product.name}
            width={900}
            height={900}
            className="w-full h-full object-cover"
            priority
          />
        )}
      </div>

      {/* Thumbnail dưới khung chính: chỉ hiển thị nút video khi có video_url */}
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
                selectedIndex === 0
                  ? 'border-blue-500 scale-105 shadow-md'
                  : 'border-gray-300 hover:border-gray-400'
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
          {images.map((image, index) => {
            const mediaIndex = hasVideo ? index + 1 : index;
            return (
              <button
                key={index}
                type="button"
                onClick={() => {
                  setSelectedIndex(mediaIndex);
                  onSelectImage?.(image);
                }}
                className={`flex-shrink-0 w-14 h-14 rounded border-2 transition-all ${
                  selectedIndex === mediaIndex
                    ? 'border-blue-500 scale-105 shadow-md'
                    : 'border-gray-300 hover:border-gray-400'
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
                  />
                </div>
              </button>
            );
          })}
        </div>
      )}

      {process.env.NODE_ENV === 'development' && (
        <div className="text-xs text-gray-500 mt-2 p-2 bg-gray-50 rounded">
          <div>📊 Debug: main_image ✓/✗, images: {product.images?.length ?? 0}, gallery: {product.gallery?.length ?? 0}, media: {mediaCount}, video: {hasVideo ? '✓' : '✗'}</div>
        </div>
      )}
    </div>
  );
}