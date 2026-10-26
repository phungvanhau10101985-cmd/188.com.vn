'use client';

import { useEffect, useId, useRef, useState } from 'react';
import {
  BANK_PAY_APPS,
  BANK_PAY_APPS_PREVIEW,
  bankPayAppIconUrl,
  buildBankQrOpenUrl,
  detectBankPayPlatform,
  vietQrBeneficiaryBin,
  type BankPayPlatform,
} from '@/lib/vietqr-bank-deeplink';

type Props = {
  open: boolean;
  onClose: () => void;
  qrImageUrl: string;
  amount: number;
  amountLabel: string;
  accountNumber: string;
  beneficiaryBank: string;
  transferContent: string;
  onOpenApp?: (appId: string) => void;
};

export default function DepositBankPaySheet({
  open,
  onClose,
  qrImageUrl,
  amount,
  amountLabel,
  accountNumber,
  beneficiaryBank,
  transferContent,
  onOpenApp,
}: Props) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const [showAll, setShowAll] = useState(false);
  const [platform] = useState<BankPayPlatform>(() =>
    typeof navigator === 'undefined' ? 'other' : detectBankPayPlatform(navigator.userAgent)
  );
  const bankBin = vietQrBeneficiaryBin(beneficiaryBank);

  useEffect(() => {
    if (!open) {
      setShowAll(false);
      return;
    }
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCloseRef.current();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);

  if (!open) return null;

  const apps = showAll ? BANK_PAY_APPS : BANK_PAY_APPS.slice(0, BANK_PAY_APPS_PREVIEW);

  return (
    <div
      className="fixed inset-0 z-[130] flex items-end justify-center bg-black/50 sm:items-center sm:p-4"
      role="presentation"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="flex max-h-[92vh] w-full max-w-md flex-col overflow-hidden rounded-t-2xl bg-white shadow-xl sm:rounded-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="shrink-0 px-4 pb-3 pt-2">
          <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-gray-300" aria-hidden />
          <div className="flex items-start gap-3">
            <h2 id={titleId} className="flex-1 text-[17px] font-bold leading-snug text-gray-900">
              Đã tìm thấy mã QR – Chọn phương thức thanh toán
            </h2>
            <button
              ref={closeRef}
              type="button"
              onClick={onClose}
              aria-label="Đóng"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-gray-500 hover:bg-gray-100"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5" aria-hidden>
                <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
              </svg>
            </button>
          </div>
          <p className="mt-1 text-sm text-gray-600">
            Cọc <span className="font-semibold text-gray-900">{amountLabel}</span>
            {transferContent ? (
              <>
                {' '}
                · nội dung <span className="font-mono font-semibold text-gray-900">{transferContent}</span>
              </>
            ) : null}
          </p>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-5">
          <div className="mb-4 flex flex-col items-center">
            <div className="rounded-xl border border-gray-200 bg-white p-2 shadow-sm">
              <img
                src={qrImageUrl}
                alt="Mã QR chuyển khoản đặt cọc"
                data-allow-png
                width={168}
                height={168}
                className="h-40 w-40 object-contain"
              />
            </div>
            <p className="mt-2 max-w-[280px] text-center text-xs leading-snug text-gray-500">
              Bấm Mở để app nhận đúng mã QR này: số tiền và nội dung đã điền, chỉ cần đăng nhập rồi xác nhận.
            </p>
          </div>

          <p className="mb-2 text-sm font-semibold text-gray-900">Mở ứng dụng</p>
          {bankBin ? (
            <ul className="divide-y divide-gray-100">
              {apps.map((app) => {
                const href = buildBankQrOpenUrl({
                  appId: app.id,
                  accountNumber,
                  beneficiaryBank,
                  amount,
                  transferContent,
                  platform,
                });
                return (
                  <li key={app.id} className="flex items-center gap-3 py-2.5">
                    <img
                      src={bankPayAppIconUrl(app.id)}
                      alt=""
                      width={40}
                      height={40}
                      className="h-10 w-10 shrink-0 rounded-full bg-gray-100 object-cover"
                    />
                    <span className="min-w-0 flex-1 truncate text-[15px] font-medium text-gray-900">{app.label}</span>
                    {href ? (
                      <a
                        href={href}
                        onClick={() => onOpenApp?.(app.id)}
                        className="inline-flex min-w-[4.5rem] items-center justify-center rounded-lg bg-gray-100 px-3 py-2 text-sm font-semibold text-gray-800 hover:bg-gray-200"
                      >
                        Mở
                      </a>
                    ) : (
                      <span className="text-xs text-gray-400">Không mở được</span>
                    )}
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-950">
              Chưa gắn được app cho ngân hàng nhận tiền. Quét mã QR phía trên để chuyển khoản.
            </p>
          )}

          {bankBin && BANK_PAY_APPS.length > BANK_PAY_APPS_PREVIEW ? (
            <button
              type="button"
              onClick={() => setShowAll((value) => !value)}
              className="mt-2 w-full py-2 text-sm font-semibold text-orange-700"
            >
              {showAll ? 'Thu gọn' : 'Xem thêm ngân hàng'}
            </button>
          ) : null}

          <p className="mt-3 text-[11px] leading-snug text-gray-500">
            Nút Mở gửi mã QR sang app, không chỉ mở trang chủ ngân hàng. Vietcombank, Agribank và MoMo không nhận link
            này — hãy quét mã QR phía trên. Kiểm tra số tiền và nội dung trước khi xác nhận.
          </p>
        </div>
      </div>
    </div>
  );
}
