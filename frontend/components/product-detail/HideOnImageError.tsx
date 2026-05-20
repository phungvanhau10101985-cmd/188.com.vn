'use client';

import { useCallback, useState } from 'react';

type HideOnImageErrorProps = {
  src: string;
  alt: string;
  className?: string;
  wrapperClassName?: string;
  onBroken?: () => void;
};

/**
 * Hiển thị ảnh bình thường; chỉ ẩn hẳn khi load lỗi hoặc ảnh 1px (alicdn chặn…).
 */
export default function HideOnImageError({
  src,
  alt,
  className = 'w-full h-auto max-w-4xl mx-auto block',
  wrapperClassName = 'bg-white rounded-xl overflow-hidden border border-gray-200 shadow-sm',
  onBroken,
}: HideOnImageErrorProps) {
  const [failed, setFailed] = useState(false);

  const markFailed = useCallback(() => {
    setFailed(true);
    onBroken?.();
  }, [onBroken]);

  const handleLoad = useCallback(
    (e: React.SyntheticEvent<HTMLImageElement>) => {
      const img = e.currentTarget;
      if (img.naturalWidth < 2 && img.naturalHeight < 2) {
        markFailed();
      }
    },
    [markFailed],
  );

  if (failed || !src.trim()) return null;

  return (
    <div className={wrapperClassName}>
      <img
        src={src}
        alt={alt}
        loading="lazy"
        decoding="async"
        className={className}
        onLoad={handleLoad}
        onError={markFailed}
      />
    </div>
  );
}

type ProductFillImageProps = {
  src: string;
  alt: string;
  frameClassName?: string;
  onBroken?: () => void;
  children?: React.ReactNode;
};

/** Ảnh chính gallery — luôn hiện khung; chỉ gỡ khi ảnh lỗi. */
export function ProductFillImage({
  src,
  alt,
  frameClassName = 'aspect-[4/5] max-h-[70vh] relative',
  onBroken,
  children,
}: ProductFillImageProps) {
  const [failed, setFailed] = useState(false);

  const markFailed = useCallback(() => {
    setFailed(true);
    onBroken?.();
  }, [onBroken]);

  const handleLoad = useCallback(
    (e: React.SyntheticEvent<HTMLImageElement>) => {
      const img = e.currentTarget;
      if (img.naturalWidth < 2 && img.naturalHeight < 2) {
        markFailed();
      }
    },
    [markFailed],
  );

  if (failed || !src.trim()) return null;

  return (
    <div className={frameClassName}>
      <img
        src={src}
        alt={alt}
        className="absolute inset-0 h-full w-full object-cover"
        decoding="async"
        onLoad={handleLoad}
        onError={markFailed}
      />
      {children}
    </div>
  );
}

type GalleryThumbImageProps = {
  src: string;
  selected: boolean;
  onClick: () => void;
  onBroken?: () => void;
  sizeClass?: string;
  selectedClassName?: string;
  unselectedClassName?: string;
};

/** Thumbnail — hiện ngay; ẩn nút nếu ảnh lỗi. */
export function GalleryThumbImage({
  src,
  selected,
  onClick,
  onBroken,
  sizeClass = 'w-16 h-16',
  selectedClassName = 'border-[#ea580c]',
  unselectedClassName = 'border-gray-200',
}: GalleryThumbImageProps) {
  const [failed, setFailed] = useState(false);

  const markFailed = useCallback(() => {
    setFailed(true);
    onBroken?.();
  }, [onBroken]);

  const handleLoad = useCallback(
    (e: React.SyntheticEvent<HTMLImageElement>) => {
      const img = e.currentTarget;
      if (img.naturalWidth < 2 && img.naturalHeight < 2) {
        markFailed();
      }
    },
    [markFailed],
  );

  if (failed || !src.trim()) return null;

  return (
    <button
      type="button"
      onClick={onClick}
      className={`relative flex-shrink-0 ${sizeClass} snap-center snap-always rounded-lg overflow-hidden border-2 transition-all ${
        selected ? selectedClassName : unselectedClassName
      }`}
    >
      <img
        src={src}
        alt=""
        className="h-full w-full object-cover"
        decoding="async"
        onLoad={handleLoad}
        onError={markFailed}
      />
    </button>
  );
}
