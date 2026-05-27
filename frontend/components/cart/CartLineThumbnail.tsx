'use client';

import { useEffect, useState } from 'react';
import Image from 'next/image';
import type { CartItem } from '@/features/cart/types/cart';
import { getOptimizedImage, stripAlicdnToBaseJpg } from '@/lib/image-utils';
import { resolveCartItemImageUrl } from '@/lib/product-color-variant';

type CartLineThumbnailProps = {
  item: CartItem;
  size?: number;
  className?: string;
};

function buildSrc(item: CartItem, size: number, rawOverride?: string): string {
  const raw = (rawOverride || resolveCartItemImageUrl(item)).trim();
  if (!raw) {
    return getOptimizedImage(undefined, { width: size, height: size, fallbackStrategy: 'local' });
  }
  return getOptimizedImage(raw, { width: size, height: size, fallbackStrategy: 'local' });
}

/** Ảnh dòng giỏ — fallback bản .jpg gốc nếu URL resize alicdn lỗi (404). */
export default function CartLineThumbnail({ item, size = 80, className = '' }: CartLineThumbnailProps) {
  const raw = resolveCartItemImageUrl(item);
  const [src, setSrc] = useState(() => buildSrc(item, size));
  const [triedBase, setTriedBase] = useState(false);

  useEffect(() => {
    setSrc(buildSrc(item, size));
    setTriedBase(false);
  }, [item.id, item.product_image, item.product_data?.main_image, size]);

  const handleError = () => {
    if (triedBase || !raw) return;
    const base = stripAlicdnToBaseJpg(raw);
    if (!base || base === raw) {
      setTriedBase(true);
      setSrc(getOptimizedImage(undefined, { width: size, height: size, fallbackStrategy: 'local' }));
      return;
    }
    setTriedBase(true);
    setSrc(buildSrc(item, size, base));
  };

  return (
    <Image
      src={src}
      alt={item.product_data?.name ?? 'Sản phẩm'}
      width={size}
      height={size}
      sizes={`${Math.min(size, 80)}px`}
      className={className || 'h-full w-full object-cover'}
      draggable={false}
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={handleError}
    />
  );
}
