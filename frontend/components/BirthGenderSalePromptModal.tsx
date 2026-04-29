'use client';

import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { apiClient } from '@/lib/api-client';
import { clearFreshLoginSession, isFreshLoginSession } from '@/lib/birthday-prompt-session';
import { useToast } from '@/components/ToastProvider';
import type { UserResponse } from '@/features/auth/types/auth';

const DISMISS_KEY = '188_birth_gender_prompt_dismissed';

const MONTH_OPTIONS = Array.from({ length: 12 }, (_, i) => {
  const monthNum = i + 1;
  const value = String(monthNum).padStart(2, '0');
  return { value, label: `Tháng ${monthNum}` };
});

function daysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate();
}

function isValidCalendarDate(year: number, month: number, day: number): boolean {
  if (month < 1 || month > 12 || day < 1) return false;
  const max = daysInMonth(year, month);
  if (day > max) return false;
  const dt = new Date(year, month - 1, day);
  return dt.getFullYear() === year && dt.getMonth() === month - 1 && dt.getDate() === day;
}

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
  const firstDobRef = useRef<HTMLSelectElement>(null);
  const [open, setOpen] = useState(false);
  /** Giá trị select: "" hoặc "01".."31" / "01".."12" / năm đủ 4 chữ số */
  const [dobDay, setDobDay] = useState('');
  const [dobMonth, setDobMonth] = useState('');
  const [dobYear, setDobYear] = useState('');
  const [gender, setGender] = useState<'male' | 'female' | ''>('');
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
      const ymd = u.date_of_birth.slice(0, 10);
      const p = ymd.split('-');
      if (p.length === 3) {
        setDobYear(p[0]);
        setDobMonth(p[1]);
        setDobDay(p[2]);
      } else {
        setDobYear('');
        setDobMonth('');
        setDobDay('');
      }
    } else {
      setDobYear('');
      setDobMonth('');
      setDobDay('');
    }
    setGender(u.gender === 'male' || u.gender === 'female' ? u.gender : '');
    setError(null);
    setOpen(true);
  }, [isAuthenticated, user, isLoading, pathname]);

  useEffect(() => {
    tryOpen();
  }, [tryOpen]);

  useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(() => firstDobRef.current?.focus(), 100);
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

  /** Khi đổi tháng/năm, thu ngày nếu không còn hợp lệ (vd. 31 → tháng 2). */
  useEffect(() => {
    if (!dobYear || !dobMonth || !dobDay) return;
    const y = parseInt(dobYear, 10);
    const m = parseInt(dobMonth, 10);
    const max = daysInMonth(y, m);
    const d = parseInt(dobDay, 10);
    if (d > max) setDobDay(String(max).padStart(2, '0'));
  }, [dobYear, dobMonth, dobDay]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!dobYear || !dobMonth || !dobDay) {
      setError('Vui lòng chọn đủ ngày, tháng và năm sinh.');
      return;
    }
    const y = parseInt(dobYear, 10);
    const m = parseInt(dobMonth, 10);
    const d = parseInt(dobDay, 10);
    if (!isValidCalendarDate(y, m, d)) {
      setError('Ngày sinh không hợp lệ (kiểm tra ngày/tháng/năm).');
      return;
    }
    const dobIso = `${dobYear}-${dobMonth}-${dobDay}`;
    const dobDate = new Date(y, m - 1, d);
    const endToday = new Date();
    endToday.setHours(23, 59, 59, 999);
    if (dobDate > endToday) {
      setError('Ngày sinh không được sau hôm nay.');
      return;
    }
    if (!gender) {
      setError('Vui lòng chọn giới tính.');
      return;
    }
    setSaving(true);
    try {
      const updated = await apiClient.updateProfile({
        date_of_birth: dobIso,
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

  const currentYear = new Date().getFullYear();
  const minYear = currentYear - 100;
  const yearOptions: number[] = [];
  for (let y = currentYear; y >= minYear; y -= 1) yearOptions.push(y);

  const maxDays =
    dobYear && dobMonth
      ? daysInMonth(parseInt(dobYear, 10), parseInt(dobMonth, 10))
      : 31;

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
            <fieldset className="space-y-1.5">
              <legend className="block text-xs font-medium text-gray-700 mb-1">Ngày sinh</legend>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label htmlFor="sale-prompt-dob-day" className="sr-only">
                    Ngày
                  </label>
                  <select
                    ref={firstDobRef}
                    id="sale-prompt-dob-day"
                    value={dobDay}
                    onChange={(e) => setDobDay(e.target.value)}
                    className="w-full rounded-lg border border-gray-200 px-2 py-2 text-sm text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-[#ea580c]/30 focus:border-[#ea580c]"
                  >
                    <option value="">Ngày</option>
                    {Array.from({ length: maxDays }, (_, i) => {
                      const dayNum = i + 1;
                      const val = String(dayNum).padStart(2, '0');
                      return (
                        <option key={val} value={val}>
                          {dayNum}
                        </option>
                      );
                    })}
                  </select>
                </div>
                <div>
                  <label htmlFor="sale-prompt-dob-month" className="sr-only">
                    Tháng
                  </label>
                  <select
                    id="sale-prompt-dob-month"
                    value={dobMonth}
                    onChange={(e) => {
                      setDobMonth(e.target.value);
                    }}
                    className="w-full rounded-lg border border-gray-200 px-2 py-2 text-sm text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-[#ea580c]/30 focus:border-[#ea580c]"
                  >
                    <option value="">Tháng</option>
                    {MONTH_OPTIONS.map(({ value, label }) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="sale-prompt-dob-year" className="sr-only">
                    Năm
                  </label>
                  <select
                    id="sale-prompt-dob-year"
                    value={dobYear}
                    onChange={(e) => setDobYear(e.target.value)}
                    className="w-full rounded-lg border border-gray-200 px-2 py-2 text-sm text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-[#ea580c]/30 focus:border-[#ea580c]"
                  >
                    <option value="">Năm</option>
                    {yearOptions.map((y) => (
                      <option key={y} value={String(y)}>
                        {y}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </fieldset>
            <div>
              <span className="block text-xs font-medium text-gray-700 mb-1.5">Giới tính</span>
              <div className="flex flex-wrap gap-2">
                {(
                  [
                    { v: 'male' as const, label: 'Nam' },
                    { v: 'female' as const, label: 'Nữ' },
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
