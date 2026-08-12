'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { setStoredAdminModules } from '@/lib/admin-role';
import { resetAdminStepUpForNewSession } from '@/lib/admin-step-up';
import { getStorefrontOrigin } from '@/lib/admin-origin';

/**
 * Nhận admin JWT từ hash (không gửi lên server) rồi ghi localStorage trên
 * admin.188.com.vn — dùng khi bấm «Quản trị web» từ 188.com.vn.
 */
export default function AdminSessionHandoffPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    try {
      const raw = window.location.hash.replace(/^#/, '');
      if (!raw) {
        setError('Thiếu phiên quản trị trong URL.');
        return;
      }
      const params = new URLSearchParams(raw);
      const accessToken = (params.get('access_token') || '').trim();
      if (!accessToken) {
        setError('Thiếu access_token.');
        return;
      }
      const role = (params.get('role') || '').trim();
      let modules: string[] | null = null;
      const modulesRaw = params.get('modules');
      if (modulesRaw) {
        try {
          const parsed = JSON.parse(modulesRaw) as unknown;
          if (Array.isArray(parsed)) {
            modules = parsed.map((x) => String(x));
          }
        } catch {
          modules = null;
        }
      }
      let next = (params.get('next') || '/admin').trim() || '/admin';
      if (!next.startsWith('/')) next = `/${next}`;
      if (!next.startsWith('/admin')) next = '/admin';

      resetAdminStepUpForNewSession();
      localStorage.setItem('admin_token', accessToken);
      localStorage.setItem('admin_role', role);
      setStoredAdminModules(modules ?? undefined);

      // Xóa token khỏi thanh địa chỉ / history
      window.history.replaceState(null, '', '/admin/auth/handoff');
      router.replace(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không nhận được phiên quản trị.');
    }
  }, [router]);

  if (error) {
    return (
      <div className="min-h-[40vh] flex flex-col items-center justify-center gap-3 px-4 text-center">
        <p className="text-sm text-red-700">{error}</p>
        <a href="/admin/login" className="text-sm font-semibold text-[#ea580c] underline">
          Đăng nhập quản trị
        </a>
        <a href={`${getStorefrontOrigin()}/`} className="text-sm text-blue-600 underline">
          Về trang chủ 188.com.vn
        </a>
      </div>
    );
  }

  return (
    <div className="min-h-[40vh] flex items-center justify-center px-4 text-sm text-gray-600">
      Đang chuyển vào quản trị…
    </div>
  );
}
