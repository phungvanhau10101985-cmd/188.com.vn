'use client';

/** Badge góc ảnh khi đang trong chương trình CMSN (ưu tiên z dưới nút tim / video). */
export function BirthdayPromoImageBadge({
  active,
  percent,
  className = '',
}: {
  active: boolean;
  percent: number;
  className?: string;
}) {
  if (!active) return null;
  return (
    <div
      className={`pointer-events-none absolute left-2 top-2 z-[1] rounded-full bg-pink-600 px-1.5 py-0.5 text-[10px] font-bold text-white shadow-md ring-1 ring-white/50 sm:left-2 sm:top-2 sm:text-xs ${className}`}
      aria-hidden
    >
      SN -{percent}%
    </div>
  );
}

/** Icon 🎂 cạnh giá — nhất quán trên lưới sản phẩm. */
export function BirthdayPromoPriceCakeIcon({ active, percent }: { active: boolean; percent: number }) {
  if (!active) return null;
  return (
    <span
      className="inline-flex shrink-0 select-none text-[15px] leading-none sm:text-base"
      title={`Ưu đãi sinh nhật -${percent}%`}
      aria-label={`Ưu đãi sinh nhật, giảm ${percent} phần trăm`}
      role="img"
    >
      🎂
    </span>
  );
}
