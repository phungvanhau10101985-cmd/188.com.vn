'use client';

/**
 * Khiên xanh + “Đã mua hàng”: đánh giá (user_id); hỏi đáp — reply_user_* hoặc QA import buyer
 * (`qaSlotShowsVerifiedPurchaserBadge`, `reviewShowsVerifiedPurchaserBadge`).
 */
export default function VerifiedPurchaserBadge({
  compact = false,
}: {
  /** Gọn cho dòng cạnh tên (vẫn hiện đủ “Đã mua hàng”) */
  compact?: boolean;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 shrink-0 ${compact ? 'gap-0.5' : 'gap-1.5'}`}
      title="Đã xác nhận mua hàng tại 188.com.vn"
      role="img"
      aria-label="Đã mua hàng tại 188.com.vn"
    >
      <svg
        className={`shrink-0 ${compact ? 'h-3.5 w-3.5' : 'h-[18px] w-[18px]'}`}
        viewBox="0 0 24 24"
        aria-hidden
      >
        <path
          fill="#16a34a"
          d="M12 2 4 5v6.09c0 5.05 3.41 9.76 8.05 11.01.13.04.26.06.4.06.14 0 .27-.02.4-.06 4.64-1.25 8.05-5.96 8.05-11.01V5l-8-3z"
        />
        <path
          fill="#22c55e"
          d="M12 3.54 5.5 6.02v4.78c0 4.14 2.86 8.18 6.5 9.85 3.64-1.67 6.5-5.71 6.5-9.85V6.02L12 3.54z"
        />
        <path
          fill="none"
          stroke="#fff"
          strokeWidth="1.85"
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M9.2 11.9 11.4 14.1 15.9 8.6"
        />
      </svg>
      <span
        className={`font-semibold text-green-700 leading-tight whitespace-nowrap ${
          compact ? 'text-[10px]' : 'text-xs'
        }`}
      >
        Đã mua hàng
      </span>
    </span>
  );
}
