'use client';

import { useCallback, useEffect } from 'react';
import { useToast } from '@/components/ToastProvider';
import {
  shareViaVnPlatform,
  VN_SHARE_PLATFORMS,
  type VnSharePlatform,
} from '@/lib/vn-social-share';

interface VnSocialShareSheetProps {
  open: boolean;
  onClose: () => void;
  url: string;
  title?: string;
}

function PlatformIcon({ id }: { id: VnSharePlatform }) {
  switch (id) {
    case 'facebook':
      return (
        <svg className="h-7 w-7" viewBox="0 0 24 24" fill="#fff" aria-hidden>
          <path d="M24 12.073C24 5.405 18.627 0 12 0S0 5.405 0 12.073C0 18.1 4.388 23.094 10.125 24v-8.437H7.078v-3.49h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.49h-2.796V24C19.612 23.094 24 18.1 24 12.073z" />
        </svg>
      );
    case 'zalo':
      return (
        <svg className="h-7 w-7" viewBox="0 0 48 48" fill="none" aria-hidden>
          <path
            fill="#fff"
            d="M24.1 8.5c-8.6 0-15.6 5.7-15.6 12.8 0 4 2.2 7.6 5.7 10l-.9 6.6 7.2-3.8c1.1.2 2.3.3 3.6.3 8.6 0 15.6-5.7 15.6-12.8S32.7 8.5 24.1 8.5z"
          />
          <path
            fill="#0068FF"
            d="M17.2 16.2h13.2v2.8H22.4l7.9 6.6h-3.7l-6.6-5.4v5.4h-2.8V16.2z"
          />
        </svg>
      );
    case 'messenger':
      return (
        <svg className="h-7 w-7" viewBox="0 0 24 24" fill="#fff" aria-hidden>
          <path d="M12 2C6.36 2 2 6.13 2 11.7c0 2.91 1.19 5.44 3.14 7.17V22l3.45-1.89c1.09.3 2.24.46 3.41.46 5.64 0 10-4.13 10-9.87C22 6.13 17.64 2 12 2zm1.01 13.28-2.61-2.78-5.01 2.78 5.5-5.84 2.67 2.76 4.95-2.75-5.5 5.83z" />
        </svg>
      );
    case 'tiktok':
      return (
        <svg className="h-7 w-7" viewBox="0 0 24 24" fill="#fff" aria-hidden>
          <path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-2.88 2.5 2.89 2.89 0 0 1-2.89-2.89 2.89 2.89 0 0 1 2.89-2.89c.28 0 .54.04.79.1V9.01a6.27 6.27 0 0 0-.79-.05 6.34 6.34 0 0 0-6.34 6.34 6.34 6.34 0 0 0 6.34 6.34 6.34 6.34 0 0 0 6.33-6.34V8.69a8.18 8.18 0 0 0 4.78 1.52V6.76a4.85 4.85 0 0 1-1.01-.07z" />
        </svg>
      );
    case 'copy':
      return (
        <svg className="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="#1f2937" strokeWidth={2} aria-hidden>
          <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
        </svg>
      );
    default:
      return null;
  }
}

export default function VnSocialShareSheet({ open, onClose, url, title }: VnSocialShareSheetProps) {
  const { pushToast } = useToast();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const handleShare = useCallback(
    async (platform: VnSharePlatform) => {
      await shareViaVnPlatform(platform, url, title, pushToast);
      onClose();
    },
    [onClose, pushToast, title, url],
  );

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[120] flex items-end justify-center bg-black/45 p-0 sm:items-center sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="vn-share-title"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-t-2xl bg-white shadow-2xl sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-gray-100 px-4 py-4">
          <div className="min-w-0">
            <h2 id="vn-share-title" className="text-base font-bold text-gray-900">
              Chia sẻ link
            </h2>
            {title ? (
              <p className="mt-1 line-clamp-2 text-xs text-gray-600">{title}</p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-gray-500 hover:bg-gray-100"
            aria-label="Đóng"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="grid grid-cols-3 gap-4 px-4 py-5 sm:grid-cols-5 sm:gap-3">
          {VN_SHARE_PLATFORMS.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => void handleShare(p.id)}
              className="flex flex-col items-center gap-2 rounded-xl p-1 active:scale-95 transition-transform"
            >
              <span
                className="flex h-14 w-14 items-center justify-center rounded-2xl shadow-sm"
                style={{ background: p.bg, color: p.color }}
              >
                <PlatformIcon id={p.id} />
              </span>
              <span className="text-center text-[11px] font-medium leading-tight text-gray-800">
                {p.label}
                {p.hint ? <span className="block text-[10px] font-normal text-gray-500">{p.hint}</span> : null}
              </span>
            </button>
          ))}
        </div>

        <div className="border-t border-gray-100 px-4 py-3">
          <p className="break-all text-[11px] text-gray-500">{url}</p>
        </div>
      </div>
    </div>
  );
}
