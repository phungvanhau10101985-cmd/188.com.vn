'use client';

import { useEffect, useRef } from 'react';

function hideBrokenImg(img: HTMLImageElement) {
  const block = img.closest('[data-detail-img-block]') as HTMLElement | null;
  if (block) {
    block.remove();
    return;
  }
  img.remove();
}

function wireImage(img: HTMLImageElement) {
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
