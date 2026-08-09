'use client';

import { useState } from 'react';
import { apiClient } from '@/lib/api-client';
import { markGuestGenderHintAnswered } from '@/lib/guest-gender-hint';
import { trackEvent } from '@/lib/analytics';

type Gender = 'male' | 'female';

/**
 * Chip chọn nhanh giới tính cho khách CHƯA đăng nhập — không cần tài khoản — để nhận gợi ý
 * theo cohort giống user đã đăng nhập ngay trong khối «CÓ THỂ BẠN THÍCH».
 */
export default function GuestGenderHintPrompt({
  onAnswered,
}: {
  onAnswered: () => void;
}) {
  const [submitting, setSubmitting] = useState<Gender | null>(null);
  const [error, setError] = useState(false);

  const choose = async (gender: Gender) => {
    if (submitting) return;
    setSubmitting(gender);
    setError(false);
    try {
      await apiClient.setGuestProfileHint({ gender });
      markGuestGenderHintAnswered();
      trackEvent('guest_gender_hint_submit', { gender });
      onAnswered();
    } catch {
      setError(true);
    } finally {
      setSubmitting(null);
    }
  };

  return (
    <div className="inline-flex flex-wrap items-center gap-1.5" role="group" aria-label="Chọn giới tính để cá nhân hoá gợi ý">
      <span className="text-[11px] font-medium text-orange-800/90">Bạn là</span>
      <button
        type="button"
        onClick={() => choose('female')}
        disabled={submitting != null}
        className="min-h-[26px] rounded-full border border-orange-200 bg-white px-2.5 text-[11px] font-semibold text-[#ea580c] transition-colors hover:bg-orange-100 disabled:opacity-60"
      >
        {submitting === 'female' ? '…' : 'Nữ'}
      </button>
      <button
        type="button"
        onClick={() => choose('male')}
        disabled={submitting != null}
        className="min-h-[26px] rounded-full border border-orange-200 bg-white px-2.5 text-[11px] font-semibold text-[#ea580c] transition-colors hover:bg-orange-100 disabled:opacity-60"
      >
        {submitting === 'male' ? '…' : 'Nam'}
      </button>
      {error ? <span className="text-[10px] text-red-600">Lỗi, thử lại</span> : null}
    </div>
  );
}
