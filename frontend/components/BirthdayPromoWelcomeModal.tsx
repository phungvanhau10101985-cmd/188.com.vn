'use client';

import Link from 'next/link';
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import { useBirthdayDiscount } from '@/lib/use-birthday-discount';

/**
 * Popup chào CMSN toàn site khi khách đang trong chương trình SN / test SN.
 * Không che trang đăng nhập và admin. Đóng = ghi localStorage (theo mốc nextBirthday + %).
 */
export default function BirthdayPromoWelcomeModal() {
  const pathname = usePathname();
  const birthday = useBirthdayDiscount();
  const titleId = useId();
  const descId = useId();
  const closeBtnRef = useRef<HTMLButtonElement>(null);

  const storageKey = useMemo(
    () =>
      `188_birthday_promo_welcome_modal_${birthday.nextBirthdayLabel || 'na'}_${birthday.percent}`,
    [birthday.nextBirthdayLabel, birthday.percent]
  );

  /** null = chưa đọc storage (tránh flash khi hydrate) */
  const [dismissed, setDismissed] = useState<boolean | null>(null);

  useEffect(() => {
    if (!birthday.active) {
      setDismissed(null);
      return;
    }
    try {
      setDismissed(localStorage.getItem(storageKey) === '1');
    } catch {
      setDismissed(false);
    }
  }, [birthday.active, storageKey]);

  const dismiss = useCallback(() => {
    setDismissed(true);
    try {
      localStorage.setItem(storageKey, '1');
    } catch {
      /* noop */
    }
  }, [storageKey]);

  const open =
    birthday.active &&
    dismissed === false &&
    !pathname?.startsWith('/auth') &&
    !pathname?.startsWith('/admin');

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') dismiss();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, dismiss]);

  useEffect(() => {
    if (!open) return;
    closeBtnRef.current?.focus();
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[195] flex items-center justify-center p-4 sm:p-6"
      role="presentation"
    >
      <button
        type="button"
        className="absolute inset-0 bg-black/55 backdrop-blur-[2px]"
        aria-label="Đóng lớp nền popup sinh nhật"
        onClick={dismiss}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        className="relative z-[1] w-full max-w-lg rounded-3xl border border-pink-200/90 bg-gradient-to-br from-pink-50 via-orange-50 to-amber-50 p-6 shadow-2xl sm:max-w-xl sm:p-10"
      >
        <button
          ref={closeBtnRef}
          type="button"
          onClick={dismiss}
          className="absolute right-3 top-3 flex h-11 w-11 items-center justify-center rounded-full bg-white/90 text-gray-600 shadow-md ring-1 ring-black/5 hover:bg-white hover:text-gray-900 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-offset-2 sm:right-4 sm:top-4"
          aria-label="Đóng thông báo chúc mừng sinh nhật"
        >
          <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        <div className="flex flex-col items-center text-center">
          <div
            className="mb-4 flex h-20 w-20 items-center justify-center rounded-full bg-pink-600 text-4xl text-white shadow-lg sm:h-24 sm:w-24 sm:text-5xl"
            aria-hidden
          >
            🎂
          </div>
          <p id={titleId} className="text-2xl font-extrabold tracking-tight text-gray-900 sm:text-3xl">
            Chúc mừng sinh nhật!
          </p>
          <span className="mt-3 inline-flex rounded-full bg-pink-600 px-4 py-1.5 text-sm font-bold text-white shadow-sm">
            Ưu đãi đang bật −{birthday.percent}%
          </span>
          <p id={descId} className="mt-4 max-w-md text-sm leading-relaxed text-gray-700 sm:text-base">
            Giá trên website đã được giảm trực tiếp theo chương trình sinh nhật và áp dụng khi thanh toán,
            không cần nhập mã.
            {birthday.nextBirthdayLabel ? (
              <span className="mt-2 block font-medium text-gray-800">
                Ngày sinh nhật sắp tới: {birthday.nextBirthdayLabel}
              </span>
            ) : null}
          </p>
        </div>

        <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:justify-center">
          <Link
            href="/cart"
            className="inline-flex min-h-[48px] flex-1 items-center justify-center rounded-full bg-[#ea580c] px-6 py-3 text-center text-sm font-semibold text-white shadow-md hover:bg-[#c2410c] sm:flex-none sm:min-w-[11rem]"
            onClick={dismiss}
          >
            Xem giỏ & thanh toán
          </Link>
          <button
            type="button"
            onClick={dismiss}
            className="inline-flex min-h-[48px] flex-1 items-center justify-center rounded-full border border-gray-300 bg-white px-6 py-3 text-sm font-semibold text-gray-800 hover:bg-gray-50 sm:flex-none sm:min-w-[10rem]"
          >
            Tiếp tục mua sắm
          </button>
        </div>
      </div>
    </div>
  );
}
