'use client';

import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { apiClient } from '@/lib/api-client';
import { clearFreshLoginSession, isFreshLoginSession } from '@/lib/birthday-prompt-session';
import { useToast } from '@/components/ToastProvider';
import type { UserResponse } from '@/features/auth/types/auth';

const DISMISS_KEY = '188_birth_gender_prompt_dismissed';

function needsBirthOrGender(user: UserResponse | null): boolean {
  if (!user) return false;
  const dob = user.date_of_birth;
  const hasDob = typeof dob === 'string' && dob.trim().length > 0;
  const g = user.gender;
  const hasGender = g === 'male' || g === 'female' || g === 'other';
  return !hasDob || !hasGender;
}

function normalizeUserFromApi(raw: Record<string, unknown>): UserResponse {
  const prev = raw as unknown as UserResponse;
  let date_of_birth = prev.date_of_birth;
  if (date_of_birth != null && typeof date_of_birth !== 'string') {
    date_of_birth = String(date_of_birth).slice(0, 10);
  }
  const g = prev.gender;
  const gender =
    g === 'male' || g === 'female' || g === 'other' ? g : undefined;
  return {
    ...prev,
    date_of_birth: date_of_birth as string | undefined,
    gender,
  };
}

/** Popup sau đăng nhập: nhập ngày sinh + giới tính để nhận ưu đãi / gợi ý phù hợp. */
export default function BirthGenderSalePromptModal() {
  const { pushToast } = useToast();
  const { isAuthenticated, isLoading, user, updateUser } = useAuth();
  const pathname = usePathname();
  const titleId = useId();
  const descId = useId();
  const dateRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [dob, setDob] = useState('');
  const [gender, setGender] = useState<'male' | 'female' | 'other' | ''>('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDefer = useCallback(() => {
    try {
      sessionStorage.setItem(DISMISS_KEY, '1');
    } catch {
      /* */
    }
    clearFreshLoginSession();
    setOpen(false);
  }, []);

  const tryOpen = useCallback(() => {
    if (typeof window === 'undefined') return;
    if (pathname?.startsWith('/auth/')) return;
    if (!isAuthenticated || !user || isLoading) return;
    if (!isFreshLoginSession()) return;
    if (sessionStorage.getItem(DISMISS_KEY) === '1') {
      clearFreshLoginSession();
      return;
    }
    if (!needsBirthOrGender(user)) {
      clearFreshLoginSession();
      return;
    }
    const u = user;
    if (u.date_of_birth && typeof u.date_of_birth === 'string') {
      setDob(u.date_of_birth.slice(0, 10));
    } else {
      setDob('');
    }
    setGender(
      u.gender === 'male' || u.gender === 'female' || u.gender === 'other' ? u.gender : ''
    );
    setError(null);
    setOpen(true);
  }, [isAuthenticated, user, isLoading, pathname]);

  useEffect(() => {
    tryOpen();
  }, [tryOpen]);

  useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(() => dateRef.current?.focus(), 100);
    return () => window.clearTimeout(t);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleDefer();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, handleDefer]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!dob.trim()) {
      setError('Vui lòng chọn ngày sinh.');
      return;
    }
    if (!gender) {
      setError('Vui lòng chọn giới tính.');
      return;
    }
    setSaving(true);
    try {
      const updated = await apiClient.updateProfile({
        date_of_birth: dob.trim(),
        gender,
      });
      const normalized = normalizeUserFromApi(updated as Record<string, unknown>);
      updateUser({
        date_of_birth: normalized.date_of_birth,
        gender: (normalized.gender ?? gender) as UserResponse['gender'],
      });
      clearFreshLoginSession();
      setOpen(false);
      pushToast({
        title: 'Đã lưu thông tin',
        description: 'Chúng tôi sẽ gửi ưu đãi phù hợp dịp sinh nhật của bạn.',
        variant: 'success',
        durationMs: 4000,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Không lưu được. Vui lòng thử lại.';
      setError(msg);
      pushToast({ title: 'Không lưu được', description: msg, variant: 'error', durationMs: 4500 });
    } finally {
      setSaving(false);
    }
  };

  if (!open) return null;

  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="fixed inset-0 z-[200] flex items-end sm:items-center justify-center p-0 sm:p-4">
      <button
        type="button"
        className="absolute inset-0 bg-black/45"
        aria-label="Đóng"
        onClick={handleDefer}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        className="relative w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl bg-white shadow-xl border border-gray-100 max-h-[90vh] overflow-y-auto"
      >
        <div className="p-4 sm:p-5">
          <h2 id={titleId} className="text-lg font-bold text-gray-900">
            Nhận ưu đãi sinh nhật
          </h2>
          <p id={descId} className="mt-1 text-sm text-gray-600">
            Cập nhật ngày sinh và giới tính để 188.COM.VN gửi chương trình sale và gợi ý phù hợp dịp sinh nhật của
            bạn.
          </p>

          <form onSubmit={handleSubmit} className="mt-4 space-y-3">
            <div>
              <label htmlFor="sale-prompt-dob" className="block text-xs font-medium text-gray-700 mb-1">
                Ngày sinh
              </label>
              <input
                ref={dateRef}
                id="sale-prompt-dob"
                type="date"
                max={today}
                value={dob}
                onChange={(e) => setDob(e.target.value)}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-[#ea580c]/30 focus:border-[#ea580c]"
                required
              />
            </div>
            <div>
              <span className="block text-xs font-medium text-gray-700 mb-1.5">Giới tính</span>
              <div className="flex flex-wrap gap-2">
                {(
                  [
                    { v: 'male' as const, label: 'Nam' },
                    { v: 'female' as const, label: 'Nữ' },
                    { v: 'other' as const, label: 'Khác' },
                  ] as const
                ).map(({ v, label }) => (
                  <button
                    key={v}
                    type="button"
                    onClick={() => setGender(v)}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                      gender === v
                        ? 'bg-[#ea580c] text-white border-[#ea580c]'
                        : 'bg-white text-gray-700 border-gray-200 hover:border-[#ea580c]/50'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {error && (
              <p className="text-sm text-red-600" role="alert">
                {error}
              </p>
            )}

            <div className="flex flex-col-reverse sm:flex-row gap-2 pt-1">
              <button
                type="button"
                onClick={handleDefer}
                className="w-full sm:flex-1 py-2.5 rounded-lg border border-gray-200 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Để sau
              </button>
              <button
                type="submit"
                disabled={saving}
                className="w-full sm:flex-1 py-2.5 rounded-lg bg-[#ea580c] text-white text-sm font-medium hover:bg-orange-600 disabled:opacity-50"
              >
                {saving ? 'Đang lưu…' : 'Lưu thông tin'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
