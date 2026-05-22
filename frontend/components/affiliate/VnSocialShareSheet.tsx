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
        <svg className="h-6 w-6" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
          <path d="M24 12.073C24 5.405 18.627 0 12 0S0 5.405 0 12.073C0 18.1 4.388 23.094 10.125 24v-8.437H7.078v-3.49h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.49h-2.796V24C19.612 23.094 24 18.1 24 12.073z" />
        </svg>
      );
    case 'zalo':
      return <span className="text-lg font-black tracking-tight">Z</span>;
    case 'messenger':
      return (
        <svg className="h-6 w-6" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
          <path d="M12 2C6.477 2 2 6.145 2 11.243c0 2.906 1.444 5.502 3.707 7.19V22l3.344-1.836c.89.245 1.83.379 2.81.379 5.523 0 10-4.145 10-9.243S17.523 2 12 2zm1.01 12.414-2.563-2.734-5.01 2.734L10.5 8.59l2.625 2.734 4.957-2.734-5.072 5.824z" />
        </svg>
      );
    case 'tiktok':
      return (
        <svg className="h-6 w-6" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
          <path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-2.88 2.5 2.89 2.89 0 0 1-2.89-2.89 2.89 2.89 0 0 1 2.89-2.89c.28 0 .54.04.79.1V9.01a6.27 6.27 0 0 0-.79-.05 6.34 6.34 0 0 0-6.34 6.34 6.34 6.34 0 0 0 6.34 6.34 6.34 6.34 0 0 0 6.33-6.34V8.69a8.18 8.18 0 0 0 4.78 1.52V6.76a4.85 4.85 0 0 1-1.01-.07z" />
        </svg>
      );
    case 'copy':
      return (
        <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden>
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
                className={`flex h-14 w-14 items-center justify-center rounded-2xl shadow-sm ${p.bgClass} ${p.textClass ?? ''}`}
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
