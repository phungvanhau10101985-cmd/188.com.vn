'use client';

import Image from 'next/image';

import { APP_WEB_ICON_URL } from '@/lib/app-web-icon';
import { cdnUrl } from '@/lib/cdn-url';
import { useAppWebIcon } from '@/lib/use-app-web-icon';

const WORDMARK = cdnUrl('/logo head 188.png');

const VARIANT_CLASS = {
  mobile: {
    wrap: 'flex items-center justify-center gap-2',
    sale: 'h-10 w-10 sm:h-11 sm:w-11 rounded-2xl object-cover shadow-sm shadow-black/15',
    wordmark: 'h-10 sm:h-11 w-auto object-contain block',
    saleSize: 44,
    wordmarkWidth: 200,
    wordmarkHeight: 40,
  },
  mobileCompact: {
    wrap: 'flex items-center justify-center gap-1.5',
    sale: 'h-8 w-8 rounded-xl object-cover shadow-sm shadow-black/15',
    wordmark: 'h-8 w-auto object-contain block',
    saleSize: 32,
    wordmarkWidth: 200,
    wordmarkHeight: 40,
  },
  desktop: {
    wrap: 'flex items-center gap-3 h-full',
    sale: 'h-16 w-16 sm:h-[4.5rem] sm:w-[4.5rem] rounded-2xl object-cover shadow-sm shadow-black/10',
    wordmark: 'h-full max-h-20 w-auto object-contain transform group-hover:scale-[1.02] transition-transform duration-200',
    saleSize: 80,
    wordmarkWidth: 320,
    wordmarkHeight: 80,
  },
  sticky: {
    wrap: 'flex items-center gap-2',
    sale: 'h-7 w-7 rounded-lg object-cover',
    wordmark: 'h-7 w-auto max-w-[7rem] sm:max-w-[8.5rem] object-contain object-left',
    saleSize: 28,
    wordmarkWidth: 140,
    wordmarkHeight: 35,
  },
} as const;

type AppBrandMarkProps = {
  variant: keyof typeof VARIANT_CLASS;
  priority?: boolean;
  className?: string;
};

/**
 * Ảnh đại diện trong app: sale cùng ngày-tháng thì hiện icon vuông AI,
 * hết sale tự về logo chữ. Khách thấy ngay khi mở shop — không cần cài lại.
 */
export default function AppBrandMark({ variant, priority = false, className = '' }: AppBrandMarkProps) {
  const { icon_url: iconUrl, is_sale: isSale } = useAppWebIcon();
  const styles = VARIANT_CLASS[variant];
  const showSaleIcon = isSale && Boolean(iconUrl) && iconUrl !== APP_WEB_ICON_URL;

  const wordmark = (
    <Image
      src={WORDMARK}
      data-allow-png
      alt="188.com.vn"
      width={styles.wordmarkWidth}
      height={styles.wordmarkHeight}
      priority={priority}
      className={`${styles.wordmark} ${className}`.trim()}
    />
  );

  if (showSaleIcon) {
    return (
      <span className={styles.wrap}>
        <Image
          src={iconUrl}
          data-allow-png
          alt="Ảnh đại diện 188 đang sale"
          width={styles.saleSize}
          height={styles.saleSize}
          priority={priority}
          className={styles.sale}
        />
        {wordmark}
      </span>
    );
  }

  return wordmark;
}
