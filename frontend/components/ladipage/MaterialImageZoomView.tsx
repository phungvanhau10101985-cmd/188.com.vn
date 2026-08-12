'use client';

import { useCallback, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

type MaterialImageZoomViewProps = {
  url: string;
  alt?: string;
  className?: string;
  imgClassName?: string;
  objectPosition?: string;
  zoomEnabled?: boolean;
  lensSize?: number;
  zoomScale?: number;
  previewSize?: number;
  maxNativeZoom?: boolean;
};

type Point = { x: number; y: number };
type Size = { w: number; h: number };

function normalizeImageUrl(url: string): string {
  const trimmed = url.trim();
  if (!trimmed) return '';
  try {
    const parsed = new URL(trimmed);
    return `${parsed.origin}${parsed.pathname}`.replace(/\/$/, '').toLowerCase();
  } catch {
    return trimmed.split('?')[0].split('#')[0].replace(/\/$/, '').toLowerCase();
  }
}

function clampPreviewPosition(clientX: number, clientY: number, previewSize: number) {
  const pad = 12;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  let left = clientX + pad;
  let top = clientY - previewSize / 2;
  if (left + previewSize > vw - pad) left = clientX - previewSize - pad;
  if (left < pad) left = pad;
  if (top < pad) top = pad;
  if (top + previewSize > vh - pad) top = vh - previewSize - pad;
  return { left, top };
}

export function MaterialImageZoomView({
  url,
  alt = '',
  className = '',
  imgClassName = 'object-contain',
  objectPosition,
  zoomEnabled = false,
  lensSize = 96,
  zoomScale = 5.5,
  previewSize = 320,
  maxNativeZoom = true,
}: MaterialImageZoomViewProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [hovering, setHovering] = useState(false);
  const [pointer, setPointer] = useState<Point>({ x: 0, y: 0 });
  const [clientPoint, setClientPoint] = useState<Point>({ x: 0, y: 0 });
  const [size, setSize] = useState<Size>({ w: 1, h: 1 });
  const [natural, setNatural] = useState<Size | null>(null);

  const refreshSize = useCallback(() => {
    const rect = rootRef.current?.getBoundingClientRect();
    if (!rect) return;
    setSize({ w: Math.max(1, rect.width), h: Math.max(1, rect.height) });
  }, []);

  const onPointerMove = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      if (!zoomEnabled) return;
      const rect = rootRef.current?.getBoundingClientRect();
      if (!rect) return;
      const x = Math.min(Math.max(event.clientX - rect.left, 0), rect.width);
      const y = Math.min(Math.max(event.clientY - rect.top, 0), rect.height);
      setPointer({ x, y });
      setClientPoint({ x: event.clientX, y: event.clientY });
    },
    [zoomEnabled],
  );

  const effectiveScale = useMemo(() => {
    if (!maxNativeZoom || !natural || size.w <= 0 || size.h <= 0) return zoomScale;
    const nativeScale = Math.min(natural.w / size.w, natural.h / size.h);
    if (!Number.isFinite(nativeScale) || nativeScale <= 1) return zoomScale;
    return Math.max(zoomScale, nativeScale);
  }, [maxNativeZoom, natural, size.h, size.w, zoomScale]);

  if (!zoomEnabled) {
    return (
      <div className={`relative overflow-hidden ${className}`}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={url}
          alt={alt}
          className={`absolute inset-0 h-full w-full ${imgClassName}`}
          style={objectPosition ? { objectPosition } : undefined}
        />
      </div>
    );
  }

  const lensLeft = pointer.x - lensSize / 2;
  const lensTop = pointer.y - lensSize / 2;
  const bgW = size.w * effectiveScale;
  const bgH = size.h * effectiveScale;
  const bgX = -(pointer.x * effectiveScale - previewSize / 2);
  const bgY = -(pointer.y * effectiveScale - previewSize / 2);
  const previewPos =
    typeof window !== 'undefined'
      ? clampPreviewPosition(clientPoint.x, clientPoint.y, previewSize)
      : { left: 0, top: 0 };

  const previewPanel =
    hovering && typeof document !== 'undefined'
      ? createPortal(
          <div
            className="pointer-events-none fixed z-[99999] overflow-hidden rounded-xl border-2 border-sky-400/80 bg-white shadow-2xl ring-4 ring-black/10"
            style={{
              width: previewSize,
              height: previewSize,
              left: previewPos.left,
              top: previewPos.top,
            }}
            aria-hidden
          >
            <div
              className="h-full w-full"
              style={{
                backgroundImage: `url("${url}")`,
                backgroundRepeat: 'no-repeat',
                backgroundSize: `${bgW}px ${bgH}px`,
                backgroundPosition: `${bgX}px ${bgY}px`,
              }}
            />
          </div>,
          document.body,
        )
      : null;

  return (
    <>
      <div
        ref={rootRef}
        className={`relative overflow-hidden ${className}`}
        onMouseEnter={() => {
          refreshSize();
          setHovering(true);
        }}
        onMouseLeave={() => setHovering(false)}
        onMouseMove={onPointerMove}
        style={{ cursor: 'zoom-in' }}
        role="img"
        aria-label={alt || 'Ảnh chất liệu — di chuột để phóng to chi tiết'}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={url}
          alt={alt}
          className={`absolute inset-0 h-full w-full ${imgClassName}`}
          draggable={false}
          style={objectPosition ? { objectPosition } : undefined}
          onLoad={(event) => {
            const img = event.currentTarget;
            if (img.naturalWidth > 0 && img.naturalHeight > 0) {
              setNatural({ w: img.naturalWidth, h: img.naturalHeight });
            }
            refreshSize();
          }}
        />
        {hovering ? (
          <div
            className="pointer-events-none absolute rounded-full border-2 border-white shadow-md ring-2 ring-sky-500/80"
            style={{
              width: lensSize,
              height: lensSize,
              left: lensLeft,
              top: lensTop,
            }}
            aria-hidden
          />
        ) : null}
      </div>
      {previewPanel}
    </>
  );
}

/** Ảnh chất liệu do AI tạo — bật kính lúp trên trang công khai. */
export function isAiMaterialImage(
  data: {
    image_url?: string | null;
    image_source?: string | null;
  },
  options?: {
    singleProductMode?: boolean;
    productImageUrls?: string[];
  },
): boolean {
  const url = (data.image_url || '').trim();
  if (!url) return false;

  const normalizedUrl = normalizeImageUrl(url);
  const source = (data.image_source || '').trim().toLowerCase();
  const productSet = new Set(
    (options?.productImageUrls || [])
      .map((item) => normalizeImageUrl(item))
      .filter(Boolean),
  );
  const isProductGalleryUrl = productSet.has(normalizedUrl);
  const isAiPipelineUrl =
    /\/ladipage\/\d+\//i.test(url) || /\/manual-products\//i.test(url);

  // Pipeline AI (Gemini Ladipage / Studio) — zoom kể cả tag cũ sai
  if (isAiPipelineUrl) return true;

  if (source === 'ai') return true;
  if (source === 'product') return false;

  // Không tag: URL trùng gallery SP → ảnh pick từ SP, không zoom
  if (isProductGalleryUrl) return false;

  // Ladipage đa SP: backend mặc định AI
  if (!options?.singleProductMode) return true;

  // Ladipage 1 SP, URL khác gallery → coi là AI (Studio/Ladipage chưa gắn tag)
  return true;
}
