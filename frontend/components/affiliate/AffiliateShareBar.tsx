'use client';

import { useState } from 'react';
import { useAffiliatePageShare } from '@/lib/use-affiliate-page-share';
import VnSocialShareSheet from '@/components/affiliate/VnSocialShareSheet';
import { tryNativeShare } from '@/lib/vn-social-share';
import { trackEvent } from '@/lib/analytics';

interface AffiliateShareBarProps {
  shareTitle?: string;
  className?: string;
}

/** Dòng mỏng: Copy / Chia sẻ link giới thiệu trang hiện tại — chỉ hiện với affiliate đã duyệt. */
export default function AffiliateShareBar({ shareTitle, className = '' }: AffiliateShareBarProps) {
  const [shareOpen, setShareOpen] = useState(false);
  const { isApproved, isLoading, shareUrl, copyShareUrl } = useAffiliatePageShare({
    shareTitle,
  });

  if (isLoading || !isApproved) return null;

  return (
    <>
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
        <span className="text-gray-300" aria-hidden>
          ·
        </span>
        <button
          type="button"
          onClick={() => {
            void tryNativeShare(shareUrl, shareTitle).then((usedNative) => {
              if (!usedNative) setShareOpen(true);
            });
          }}
          className="font-semibold text-[#ea580c] underline-offset-2 hover:underline"
        >
          Chia sẻ
        </button>
      </div>
      <VnSocialShareSheet
        open={shareOpen}
        onClose={() => setShareOpen(false)}
        url={shareUrl}
        title={shareTitle}
      />
    </>
  );
}

interface ProductShareIconButtonProps {
  shareTitle?: string;
  className?: string;
  productId?: string | number;
}

/** Cặp nút Copy link + Chia sẻ — hàng badge mobile PDP. */
export function ProductShareActionButtons({
  shareTitle,
  className = '',
  productId,
}: ProductShareIconButtonProps) {
  const [shareOpen, setShareOpen] = useState(false);
  const { shareUrl, copyShareUrl, isApproved } = useAffiliatePageShare({ shareTitle });

  const handleCopy = () => {
    void copyShareUrl().then((ok) => {
      if (!ok) return;
      trackEvent('share_product', {
        method: isApproved ? 'copy_affiliate_link' : 'copy_link',
        ...(productId ? { product_id: productId } : {}),
      });
    });
  };

  const handleShare = () => {
    trackEvent('share_product', {
      method: isApproved ? 'open_affiliate_share' : 'open_share',
      ...(productId ? { product_id: productId } : {}),
    });
    void tryNativeShare(shareUrl, shareTitle).then((usedNative) => {
      if (!usedNative) setShareOpen(true);
    });
  };

  return (
    <>
      <div className={`flex shrink-0 items-center gap-1.5 ${className}`}>
        <button
          type="button"
          onClick={handleCopy}
          className="inline-flex items-center gap-1 rounded-full border border-gray-200 bg-white px-2.5 py-0.5 text-[11px] font-semibold text-gray-700 active:bg-gray-50"
          aria-label={isApproved ? 'Copy link giới thiệu' : 'Copy link sản phẩm'}
        >
          <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"
            />
          </svg>
          Copy link
        </button>
        <button
          type="button"
          onClick={handleShare}
          className="inline-flex items-center gap-1 rounded-full border border-orange-200 bg-orange-50/80 px-2.5 py-0.5 text-[11px] font-semibold text-orange-700 active:bg-orange-100"
          aria-label={isApproved ? 'Chia sẻ link giới thiệu' : 'Chia sẻ sản phẩm'}
        >
          <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z"
            />
          </svg>
          Chia sẻ
        </button>
      </div>
      <VnSocialShareSheet
        open={shareOpen}
        onClose={() => setShareOpen(false)}
        url={shareUrl}
        title={shareTitle}
      />
    </>
  );
}

/** Nút tròn chia sẻ trên ảnh sản phẩm — affiliate: link có ref; khách thường: link trang hiện tại. */
export function ProductShareIconButton({ shareTitle, className = '' }: ProductShareIconButtonProps) {
  const [shareOpen, setShareOpen] = useState(false);
  const { shareUrl, isApproved } = useAffiliatePageShare({ shareTitle });

  return (
    <>
      <button
        type="button"
        onClick={() => {
          void tryNativeShare(shareUrl, shareTitle).then((usedNative) => {
            if (!usedNative) setShareOpen(true);
          });
        }}
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
      <VnSocialShareSheet
        open={shareOpen}
        onClose={() => setShareOpen(false)}
        url={shareUrl}
        title={shareTitle}
      />
    </>
  );
}
