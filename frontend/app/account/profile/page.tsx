'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { apiClient } from '@/lib/api-client';
import { useToast } from '@/components/ToastProvider';
import type { UserResponse } from '@/features/auth/types/auth';

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

function dobInputValue(user: UserResponse | null): string {
  const d = user?.date_of_birth;
  if (!d || typeof d !== 'string') return '';
  return d.slice(0, 10);
}

export default function AccountProfilePage() {
  const { user, updateUser } = useAuth();
  const { pushToast } = useToast();
  const [fullName, setFullName] = useState('');
  const [gender, setGender] = useState<'male' | 'female' | 'other' | ''>('');
  const [dob, setDob] = useState('');
  const [address, setAddress] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!user) return;
    setFullName(user.full_name ?? '');
    const g = user.gender;
    setGender(g === 'male' || g === 'female' || g === 'other' ? g : '');
    setDob(dobInputValue(user));
    setAddress(user.address ?? '');
  }, [user]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload: Record<string, unknown> = {
        full_name: fullName.trim(),
        address: address.trim() || undefined,
      };
      if (gender) payload.gender = gender;
      if (dob) payload.date_of_birth = dob;

      const updated = await apiClient.updateProfile(payload);
      const normalized = normalizeUserFromApi(updated as Record<string, unknown>);
      updateUser(normalized);
      pushToast({
        title: 'Đã lưu hồ sơ',
        variant: 'success',
        durationMs: 2500,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Không lưu được. Vui lòng thử lại.';
      pushToast({ title: 'Không lưu được', description: msg, variant: 'error', durationMs: 4000 });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-xl mx-auto">
      <div className="mb-4 flex items-center gap-3 md:hidden">
        <Link href="/account" className="text-sm text-blue-600 font-medium">
          ← Tài khoản
        </Link>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4 md:p-6">
        <h1 className="text-lg md:text-xl font-bold text-gray-900 mb-1">Chỉnh sửa hồ sơ</h1>
        <p className="text-sm text-gray-500 mb-6">
          Email đăng nhập không đổi tại đây. Cập nhật họ tên, ngày sinh và địa chỉ liên hệ.
        </p>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label htmlFor="profile-email" className="block text-sm font-medium text-gray-700 mb-1">
              Email
            </label>
            <input
              id="profile-email"
              type="email"
              readOnly
              value={user?.email ?? ''}
              className="w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-gray-600 text-sm cursor-not-allowed"
            />
          </div>

          <div>
            <label htmlFor="profile-phone" className="block text-sm font-medium text-gray-700 mb-1">
              Số điện thoại
            </label>
            <input
              id="profile-phone"
              type="text"
              readOnly
              value={user?.phone ?? ''}
              placeholder="Chưa có"
              className="w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-gray-600 text-sm cursor-not-allowed"
            />
            <p className="mt-1 text-xs text-gray-400">Số điện thoại không chỉnh qua trang này.</p>
          </div>

          <div>
            <label htmlFor="profile-name" className="block text-sm font-medium text-gray-700 mb-1">
              Họ và tên
            </label>
            <input
              id="profile-name"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-gray-900 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
              autoComplete="name"
            />
          </div>

          <div>
            <label htmlFor="profile-gender" className="block text-sm font-medium text-gray-700 mb-1">
              Giới tính
            </label>
            <select
              id="profile-gender"
              value={gender}
              onChange={(e) =>
                setGender(e.target.value as 'male' | 'female' | 'other' | '')
              }
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-gray-900 text-sm bg-white focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
            >
              <option value="">— Chọn —</option>
              <option value="male">Nam</option>
              <option value="female">Nữ</option>
              <option value="other">Khác</option>
            </select>
          </div>

          <div>
            <label htmlFor="profile-dob" className="block text-sm font-medium text-gray-700 mb-1">
              Ngày sinh
            </label>
            <input
              id="profile-dob"
              type="date"
              value={dob}
              onChange={(e) => setDob(e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-gray-900 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
            />
          </div>

          <div>
            <label htmlFor="profile-address" className="block text-sm font-medium text-gray-700 mb-1">
              Địa chỉ liên hệ
            </label>
            <textarea
              id="profile-address"
              rows={3}
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-gray-900 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none resize-y"
              placeholder="Số nhà, đường, phường/xã…"
            />
          </div>

          <div className="flex flex-col sm:flex-row gap-3 pt-2">
            <button
              type="submit"
              disabled={loading}
              className="inline-flex justify-center rounded-xl bg-[#ea580c] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#c2410c] disabled:opacity-60 transition-colors"
            >
              {loading ? 'Đang lưu…' : 'Lưu thay đổi'}
            </button>
            <Link
              href="/account"
              className="inline-flex justify-center rounded-xl border border-gray-200 px-5 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
            >
              Hủy
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
