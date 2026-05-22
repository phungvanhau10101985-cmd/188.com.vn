'use client';

import { useAffiliatePageShare } from '@/lib/use-affiliate-page-share';

interface AffiliateShareBarProps {
  shareTitle?: string;
  className?: string;
}

/** Dòng mỏng: Copy / Chia sẻ link giới thiệu trang hiện tại — chỉ hiện với affiliate đã duyệt. */
export default function AffiliateShareBar({ shareTitle, className = '' }: AffiliateShareBarProps) {
  const { isApproved, isLoading, canNativeShare, copyShareUrl, nativeShare } = useAffiliatePageShare({
    shareTitle,
  });

  if (isLoading || !isApproved) return null;

  return (
    <div
      className={`flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-orange-100 bg-orange-50/80 px-3 py-2 text-xs text-gray-700 ${className}`}
    >
      <span className="font-medium text-[#ea580c]">Link giới thiệu trang này</span>
      <span className="hidden sm:inline text-gray-300" aria-hidden>
        ·
      </span>
      <button
        type="button"
        onClick={() => void copyShareUrl()}
        className="font-semibold text-gray-800 underline-offset-2 hover:text-[#ea580c] hover:underline"
      >
        Copy
      </button>
      {canNativeShare ? (
        <>
          <span className="text-gray-300" aria-hidden>
            ·
          </span>
          <button
            type="button"
            onClick={() => void nativeShare()}
            className="font-semibold text-[#ea580c] underline-offset-2 hover:underline"
          >
            Chia sẻ
          </button>
        </>
      ) : null}
    </div>
  );
}

interface ProductShareIconButtonProps {
  shareTitle?: string;
  className?: string;
}

/** Nút tròn chia sẻ trên ảnh sản phẩm — affiliate: link có ref; khách thường: link trang hiện tại. */
export function ProductShareIconButton({ shareTitle, className = '' }: ProductShareIconButtonProps) {
  const { canNativeShare, nativeShare, copyShareUrl, isApproved } = useAffiliatePageShare({ shareTitle });

  const handleClick = () => {
    if (canNativeShare) void nativeShare();
    else void copyShareUrl();
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      className={`w-8 h-8 rounded-full bg-white/80 flex items-center justify-center shadow-sm hover:bg-white ${className}`}
      aria-label={isApproved ? 'Chia sẻ link giới thiệu' : 'Chia sẻ sản phẩm'}
      title={isApproved ? 'Chia sẻ link giới thiệu' : 'Chia sẻ'}
    >
      <svg className="w-4 h-4 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z"
        />
      </svg>
    </button>
  );
}
