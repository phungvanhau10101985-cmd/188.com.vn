'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

type HideOnImageErrorProps = {
  src: string;
  alt: string;
  className?: string;
  wrapperClassName?: string;
  onBroken?: (src: string) => void;
  /** Ảnh treo (alicdn chặn hotlink…) — coi là lỗi */
  loadTimeoutMs?: number;
};

/**
 * Chỉ render khung ảnh sau khi load OK (naturalWidth > 1).
 * Lỗi / timeout / ảnh 1px → return null (không khoảng trắng, không viền).
 */
export default function HideOnImageError({
  src,
  alt,
  className = 'w-full h-auto max-w-4xl mx-auto block',
  wrapperClassName = 'bg-white rounded-xl overflow-hidden border border-gray-200 shadow-sm',
  onBroken,
  loadTimeoutMs = 12_000,
}: HideOnImageErrorProps) {
  const [visible, setVisible] = useState(false);
  const [removed, setRemoved] = useState(false);
  const settled = useRef(false);

  const fail = useCallback(() => {
    if (settled.current) return;
    settled.current = true;
    setRemoved(true);
    setVisible(false);
    onBroken?.(src);
  }, [onBroken, src]);

  useEffect(() => {
    settled.current = false;
    setVisible(false);
    setRemoved(false);
    const timer = window.setTimeout(() => fail(), loadTimeoutMs);
    return () => window.clearTimeout(timer);
  }, [src, loadTimeoutMs, fail]);

  const handleLoad = useCallback(
    (e: React.SyntheticEvent<HTMLImageElement>) => {
      if (settled.current) return;
      const img = e.currentTarget;
      if (img.naturalWidth < 2 || img.naturalHeight < 2) {
        fail();
        return;
      }
      settled.current = true;
      setVisible(true);
    },
    [fail],
  );

  if (removed) return null;

  if (!visible) {
    return (
      <img
        src={src}
        alt=""
        aria-hidden
        className="pointer-events-none fixed -left-[9999px] top-0 h-px w-px opacity-0"
        decoding="async"
        onLoad={handleLoad}
        onError={() => fail()}
      />
    );
  }

  return (
    <div className={wrapperClassName}>
      <img
        src={src}
        alt={alt}
        loading="lazy"
        decoding="async"
        className={className}
        onLoad={handleLoad}
        onError={() => fail()}
      />
    </div>
  );
}

type ProductFillImageProps = {
  src: string;
  alt: string;
  frameClassName?: string;
  onBroken?: (src: string) => void;
  children?: React.ReactNode;
  loadTimeoutMs?: number;
};

/** Ảnh chính mobile/desktop fill — không mở khung aspect cho đến khi load OK. */
export function ProductFillImage({
  src,
  alt,
  frameClassName = 'aspect-[4/5] max-h-[70vh] relative',
  onBroken,
  children,
  loadTimeoutMs = 12_000,
}: ProductFillImageProps) {
  const [visible, setVisible] = useState(false);
  const [removed, setRemoved] = useState(false);
  const settled = useRef(false);

  const fail = useCallback(() => {
    if (settled.current) return;
    settled.current = true;
    setRemoved(true);
    setVisible(false);
    onBroken?.(src);
  }, [onBroken, src]);

  useEffect(() => {
    settled.current = false;
    setVisible(false);
    setRemoved(false);
    const timer = window.setTimeout(() => fail(), loadTimeoutMs);
    return () => window.clearTimeout(timer);
  }, [src, loadTimeoutMs, fail]);

  const handleLoad = useCallback(
    (e: React.SyntheticEvent<HTMLImageElement>) => {
      if (settled.current) return;
      const img = e.currentTarget;
      if (img.naturalWidth < 2 || img.naturalHeight < 2) {
        fail();
        return;
      }
      settled.current = true;
      setVisible(true);
    },
    [fail],
  );

  if (removed) return null;

  if (!visible) {
    return (
      <img
        src={src}
        alt=""
        aria-hidden
        className="pointer-events-none fixed -left-[9999px] top-0 h-px w-px opacity-0"
        decoding="async"
        onLoad={handleLoad}
        onError={() => fail()}
      />
    );
  }

  return (
    <div className={frameClassName}>
      <img
        src={src}
        alt={alt}
        className="absolute inset-0 h-full w-full object-cover"
        decoding="async"
        onLoad={handleLoad}
        onError={() => fail()}
      />
      {children}
    </div>
  );
}

type GalleryThumbImageProps = {
  src: string;
  selected: boolean;
  onClick: () => void;
  onBroken?: (src: string) => void;
  /** Tailwind kích thước nút, mặc định w-16 h-16 */
  sizeClass?: string;
  selectedClassName?: string;
  unselectedClassName?: string;
};

/** Thumbnail gallery — không render nút nếu ảnh alicdn/URL lỗi. */
export function GalleryThumbImage({
  src,
  selected,
  onClick,
  onBroken,
  sizeClass = 'w-16 h-16',
  selectedClassName = 'border-[#ea580c]',
  unselectedClassName = 'border-gray-200',
}: GalleryThumbImageProps) {
  const [visible, setVisible] = useState(false);
  const [removed, setRemoved] = useState(false);
  const settled = useRef(false);

  const fail = useCallback(() => {
    if (settled.current) return;
    settled.current = true;
    setRemoved(true);
    onBroken?.(src);
  }, [onBroken, src]);

  useEffect(() => {
    settled.current = false;
    setVisible(false);
    setRemoved(false);
    const timer = window.setTimeout(() => fail(), 10_000);
    return () => window.clearTimeout(timer);
  }, [src, fail]);

  const handleLoad = useCallback(
    (e: React.SyntheticEvent<HTMLImageElement>) => {
      if (settled.current) return;
      const img = e.currentTarget;
      if (img.naturalWidth < 2 || img.naturalHeight < 2) {
        fail();
        return;
      }
      settled.current = true;
      setVisible(true);
    },
    [fail],
  );

  if (removed) return null;

  if (!visible) {
    return (
      <img
        src={src}
        alt=""
        aria-hidden
        className="pointer-events-none fixed -left-[9999px] top-0 h-px w-px opacity-0"
        decoding="async"
        onLoad={handleLoad}
        onError={() => fail()}
      />
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className={`relative flex-shrink-0 ${sizeClass} snap-center snap-always rounded-lg overflow-hidden border-2 transition-all ${
        selected ? selectedClassName : unselectedClassName
      }`}
    >
      <img src={src} alt="" className="h-full w-full object-cover" decoding="async" />
    </button>
  );
}
