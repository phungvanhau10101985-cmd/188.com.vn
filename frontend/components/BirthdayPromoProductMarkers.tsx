'use client';

import { BIRTHDAY_PROGRAM_NAME } from '@/lib/birthday-discount';

/** Badge góc ảnh khi đang trong chương trình CMSN (ưu tiên z dưới nút tim / video). */
export function BirthdayPromoImageBadge({
  active,
  percent,
  className = '',
  embedded = false,
}: {
  active: boolean;
  percent: number;
  className?: string;
  embedded?: boolean;
}) {
  if (!active) return null;
  return (
    <div
      className={`${
        embedded
          ? 'relative'
          : 'pointer-events-none absolute left-2 top-2 z-[1] sm:left-2 sm:top-2'
      } rounded-full bg-pink-600 px-1.5 py-0.5 text-[10px] font-bold text-white shadow-md ring-1 ring-white/50 sm:text-xs ${className}`}
      aria-hidden
    >
      {BIRTHDAY_PROGRAM_NAME} -{percent}%
    </div>
  );
}

/** Icon 🎂 cạnh giá — nhất quán trên lưới sản phẩm. */
export function BirthdayPromoPriceCakeIcon({ active, percent }: { active: boolean; percent: number }) {
  if (!active) return null;
  return (
    <span
      className="inline-flex shrink-0 select-none text-[15px] leading-none sm:text-base"
      title={`${BIRTHDAY_PROGRAM_NAME} -${percent}%`}
      aria-label={`${BIRTHDAY_PROGRAM_NAME}, giảm ${percent} phần trăm`}
      role="img"
    >
      🎂
    </span>
  );
}
