'use client';

import { useEffect, useRef } from 'react';
import {
  getOptimizedImage,
  isAlibabaCdnImageUrl,
  isHiddenWebPngImageUrl,
} from '@/lib/image-utils';
import { normalizeRemoteImageUrlForDisplay } from '@/lib/cdn-url';

function hideBrokenImg(img: HTMLImageElement) {
  const block = img.closest('[data-detail-img-block]') as HTMLElement | null;
  if (block) {
    block.remove();
    return;
  }
  img.remove();
}

function wireImage(img: HTMLImageElement) {
  const raw = (img.getAttribute('src') || '').trim();
  if (!raw) return;
  if (isHiddenWebPngImageUrl(raw)) {
    hideBrokenImg(img);
    return;
  }
  const normalized = isAlibabaCdnImageUrl(raw)
    ? normalizeRemoteImageUrlForDisplay(raw)
    : raw;
  const displaySrc =
    normalized.startsWith('http') || normalized.startsWith('//') || normalized.startsWith('/')
      ? getOptimizedImage(
          normalized.startsWith('//') ? `https:${normalized}` : normalized,
          { width: 600, height: 600, fallbackStrategy: 'local', hideProductPng: true },
        )
      : raw;
  if (displaySrc !== raw) {
    img.setAttribute('src', displaySrc);
    if (isAlibabaCdnImageUrl(raw)) {
      img.setAttribute('referrerpolicy', 'no-referrer');
    }
  }
  const onFail = () => hideBrokenImg(img);
  const onLoad = () => {
    if (img.naturalWidth < 2 || img.naturalHeight < 2) onFail();
  };
  if (img.complete) {
    if (img.naturalWidth < 2 || img.naturalHeight < 2) onFail();
    return;
  }
  img.addEventListener('error', onFail, { once: true });
  img.addEventListener('load', onLoad, { once: true });
}

type DescriptionHtmlSafeImagesProps = {
  html: string;
  className?: string;
};

/** Mô tả HTML có thể chứa <img src="https://img.alicdn.com/..."> — ẩn ảnh lỗi. */
export default function DescriptionHtmlSafeImages({ html, className }: DescriptionHtmlSafeImagesProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    root.querySelectorAll('img').forEach((node) => wireImage(node as HTMLImageElement));
  }, [html]);

  return (
    <div
      ref={ref}
      className={className}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
