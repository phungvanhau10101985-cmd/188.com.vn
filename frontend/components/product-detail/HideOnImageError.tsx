'use client';

import { useCallback, useEffect, useState } from 'react';
import { getOptimizedImage, isAlibabaCdnImageUrl, stripAlicdnToBaseJpg } from '@/lib/image-utils';

function buildRemoteImgSrc(raw: string, size: number, rawOverride?: string): string {
  const s = (rawOverride || raw).trim();
  if (!s) return '';
  return getOptimizedImage(s, {
    width: size,
    height: size,
    fallbackStrategy: 'local',
    hideProductPng: true,
  });
}

type RemoteProductImgProps = {
  src: string;
  alt: string;
  className?: string;
  displaySize?: number;
  onLoad?: (e: React.SyntheticEvent<HTMLImageElement>) => void;
  onBroken?: () => void;
};

/** img/alicdn + cbu01.alicdn — resize an toàn, fallback bản .jpg gốc. */
function RemoteProductImg({
  src,
  alt,
  className,
  displaySize = 800,
  onLoad,
  onBroken,
}: RemoteProductImgProps) {
  const [currentSrc, setCurrentSrc] = useState(() => buildRemoteImgSrc(src, displaySize));
  const [triedBase, setTriedBase] = useState(false);

  useEffect(() => {
    setCurrentSrc(buildRemoteImgSrc(src, displaySize));
    setTriedBase(false);
  }, [src, displaySize]);

  const handleError = () => {
    if (!triedBase && isAlibabaCdnImageUrl(src)) {
      const base = stripAlicdnToBaseJpg(src);
      if (base && base !== stripAlicdnToBaseJpg(currentSrc)) {
        setTriedBase(true);
        setCurrentSrc(buildRemoteImgSrc(src, displaySize, base));
        return;
      }
    }
    onBroken?.();
  };

  if (!currentSrc.trim()) {
    onBroken?.();
    return null;
  }

  return (
    <img
      src={currentSrc}
      alt={alt}
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      className={className}
      onLoad={onLoad}
      onError={handleError}
    />
  );
}

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
      <RemoteProductImg
        src={src}
        alt={alt}
        className={className}
        displaySize={800}
        onLoad={handleLoad}
        onBroken={markFailed}
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
      <RemoteProductImg
        src={src}
        alt={alt}
        className="absolute inset-0 h-full w-full object-cover"
        displaySize={960}
        onLoad={handleLoad}
        onBroken={markFailed}
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
  buttonRef?: (el: HTMLButtonElement | null) => void;
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
  buttonRef,
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
      ref={buttonRef}
      type="button"
      onClick={onClick}
      className={`relative flex-shrink-0 ${sizeClass} snap-center snap-always rounded-lg overflow-hidden border-2 transition-all ${
        selected ? selectedClassName : unselectedClassName
      }`}
    >
      <RemoteProductImg
        src={src}
        alt=""
        className="h-full w-full object-cover"
        displaySize={160}
        onLoad={handleLoad}
        onBroken={markFailed}
      />
    </button>
  );
}
