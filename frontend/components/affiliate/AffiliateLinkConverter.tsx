'use client';

import { useMemo, useState } from 'react';
import { appendReferralToUrl } from '@/lib/affiliate-ref';
import { useToast } from '@/components/ToastProvider';
import VnSocialShareSheet from '@/components/affiliate/VnSocialShareSheet';

interface AffiliateLinkConverterProps {
  referralCode: string;
}

export default function AffiliateLinkConverter({ referralCode }: AffiliateLinkConverterProps) {
  const { pushToast } = useToast();
  const [inputUrl, setInputUrl] = useState('');
  const [copied, setCopied] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);

  const affiliateUrl = useMemo(() => {
    const raw = inputUrl.trim();
    if (!raw) return '';
    return appendReferralToUrl(raw, referralCode);
  }, [inputUrl, referralCode]);

  const copyConverted = async () => {
    if (!affiliateUrl) return;
    try {
      await navigator.clipboard.writeText(affiliateUrl);
      setCopied(true);
      pushToast({ title: 'Đã copy link giới thiệu', variant: 'success', durationMs: 2000 });
      setTimeout(() => setCopied(false), 2000);
    } catch {
      pushToast({ title: 'Không copy được link', variant: 'error' });
    }
  };

  return (
    <>
      <div className="rounded-xl border border-orange-100 bg-orange-50/40 p-4 space-y-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">Tạo link giới thiệu từ link bất kỳ</h3>
          <p className="text-xs text-gray-600 mt-1">
            Dán link sản phẩm, danh mục hoặc trang bất kỳ — hệ thống tự thêm mã <strong>{referralCode}</strong>.
          </p>
        </div>
        <input
          type="url"
          inputMode="url"
          value={inputUrl}
          onChange={(e) => setInputUrl(e.target.value)}
          placeholder="https://188.com.vn/products/..."
          className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm bg-white"
        />
        {affiliateUrl ? (
          <div className="space-y-2">
            <input
              readOnly
              value={affiliateUrl}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-xs bg-gray-50 text-gray-700"
            />
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void copyConverted()}
                className="rounded-lg bg-[#ea580c] text-white px-4 py-2 text-sm font-semibold hover:bg-[#c2410c]"
              >
                {copied ? 'Đã copy' : 'Copy link'}
              </button>
              <button
                type="button"
                onClick={() => setShareOpen(true)}
                className="rounded-lg border border-[#ea580c] text-[#ea580c] px-4 py-2 text-sm font-semibold hover:bg-orange-50"
              >
                Chia sẻ
              </button>
            </div>
          </div>
        ) : null}
      </div>
      <VnSocialShareSheet
        open={shareOpen}
        onClose={() => setShareOpen(false)}
        url={affiliateUrl}
        title="188.com.vn"
      />
    </>
  );
}
