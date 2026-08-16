'use client';

import Image, { type ImageProps } from 'next/image';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { getOptimizedImage, getOriginalImageUrl } from '@/lib/image-utils';

type CdnFillImageProps = Omit<ImageProps, 'src' | 'fill'> & {
  rawSrc: string;
  widthHint?: number;
  heightHint?: number;
  quality?: number;
};

/**
 * next/image + URL CDN đã resize; nếu 404 thì đổi sang file gốc (không giảm nét tay).
 */
export default function CdnFillImage({
  rawSrc,
  widthHint = 300,
  heightHint = 300,
  quality = 90,
  onError,
  alt,
  ...rest
}: CdnFillImageProps) {
  const optimized = useMemo(
    () =>
      getOptimizedImage(rawSrc, {
        width: widthHint,
        height: heightHint,
        quality,
        fallbackStrategy: 'local',
      }),
    [rawSrc, widthHint, heightHint, quality]
  );
  const [src, setSrc] = useState(optimized);
  const [usedOriginal, setUsedOriginal] = useState(false);

  useEffect(() => {
    setSrc(optimized);
    setUsedOriginal(false);
  }, [optimized]);

  const handleError: NonNullable<ImageProps['onError']> = useCallback(
    (event) => {
      if (!usedOriginal) {
        const original = getOriginalImageUrl(rawSrc, {
          width: widthHint,
          height: heightHint,
          quality,
          fallbackStrategy: 'local',
        });
        if (original && original !== src && !original.startsWith('data:')) {
          setUsedOriginal(true);
          setSrc(original);
          return;
        }
      }
      onError?.(event);
    },
    [usedOriginal, rawSrc, widthHint, heightHint, quality, src, onError]
  );

  return <Image {...rest} src={src} alt={alt} fill onError={handleError} />;
}
