'use client';

/**
 * Tích xanh: chỉ khách có account và đã mua đủ điều kiện mới được gửi trả lời (reply_user_*_id).
 */
export default function VerifiedPurchaserBadge({
  compact = false,
}: {
  /** Chỉ icon + tooltip — gọn trong dòng có tên + ngày */
  compact?: boolean;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 text-sky-600 ${compact ? 'text-[11px] font-semibold leading-none' : 'text-xs font-medium'} whitespace-nowrap`}
      title="Người dùng xác nhận đã mua hàng tại 188.com.vn"
      role="img"
      aria-label="Đã mua hàng tại 188.com.vn"
    >
      <svg
        className="h-4 w-4 shrink-0 -translate-y-[0.5px]"
        viewBox="0 0 24 24"
        aria-hidden
      >
        <circle cx="12" cy="12" r="10.5" fill="#0284c7" />
        <path
          d="M7.75 12.25 10.4 14.85 15.95 9.05"
          fill="none"
          stroke="#fff"
          strokeWidth="2.1"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {!compact && (
        <>
          Đã mua tại 188.com.vn
        </>
      )}
    </span>
  );
}
