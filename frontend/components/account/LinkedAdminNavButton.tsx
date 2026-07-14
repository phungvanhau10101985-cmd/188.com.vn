'use client';

import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { ApiRequestError, apiClient } from '@/lib/api-client';
import { defaultAdminHome, setStoredAdminModules } from '@/lib/admin-role';
import { useToast } from '@/components/ToastProvider';
import StepUpOtpModal, {
  clearRecentStepUp,
  hasRecentStepUp,
} from '@/components/auth/StepUpOtpModal';

type Props = {
  /** sidebar: trong nav trái | banner: khối nổi phía trên nội dung (mobile / đầu trang) */
  variant?: 'sidebar' | 'banner';
};

export default function LinkedAdminNavButton({ variant = 'sidebar' }: Props) {
  const { user } = useAuth();
  const router = useRouter();
  const { pushToast } = useToast();
  const [busy, setBusy] = useState(false);
  const [showStepUp, setShowStepUp] = useState(false);

  const completeOpenAdmin = useCallback(async () => {
    setBusy(true);
    try {
      const data = await apiClient.exchangeLinkedAdminSession();
      if (typeof window !== 'undefined') {
        localStorage.setItem('admin_token', data.access_token);
        localStorage.setItem('admin_role', data.role || '');
        setStoredAdminModules(data.modules ?? undefined);
      }
      router.push(defaultAdminHome());
      setShowStepUp(false);
    } catch (err: unknown) {
      if (err instanceof ApiRequestError && err.code === 'step_up_required') {
        clearRecentStepUp('admin_elevation');
        setShowStepUp(true);
        return;
      }
      const msg = err instanceof Error ? err.message : 'Không lấy được phiên quản trị.';
      pushToast({ title: 'Không vào được quản trị', description: msg, variant: 'error', durationMs: 3500 });
    } finally {
      setBusy(false);
    }
  }, [pushToast, router]);

  const openAdmin = useCallback(async () => {
    if (!hasRecentStepUp('admin_elevation')) {
      setShowStepUp(true);
      return;
    }
    await completeOpenAdmin();
  }, [completeOpenAdmin]);

  if (!user?.has_linked_admin) return null;

  const roleHint =
    user.linked_admin_role || user.linked_admin_username
      ? [user.linked_admin_role, user.linked_admin_username ? `@${user.linked_admin_username}` : '']
          .filter(Boolean)
          .join(' ')
      : null;

  const btn = (
    <button
      type="button"
      disabled={busy}
      onClick={() => void openAdmin()}
      className={
        variant === 'banner'
          ? 'inline-flex min-h-[44px] shrink-0 items-center justify-center rounded-lg bg-[#ea580c] px-4 py-2 text-sm font-semibold text-white hover:bg-[#c2410c] disabled:opacity-60 transition-colors'
          : 'flex w-full items-center gap-3 border-l-4 border-transparent px-4 py-3 text-left font-medium text-[#ea580c] transition-colors hover:bg-orange-50 disabled:opacity-60'
      }
    >
      {variant === 'sidebar' ? (
        <>
          <span className="w-6 text-center">⚙️</span>
          <span>Quản trị web</span>
          <span className="ml-auto text-gray-400">›</span>
        </>
      ) : busy ? (
        'Đang mở…'
      ) : (
        'Vào quản trị'
      )}
    </button>
  );

  const stepUpModal = showStepUp ? (
    <StepUpOtpModal
      purpose="admin_elevation"
      title="Xác minh trước khi vào quản trị"
      description="Khu vực quản trị có quyền thay đổi dữ liệu cửa hàng nên cần OTP gần đây."
      onClose={() => setShowStepUp(false)}
      onVerified={completeOpenAdmin}
    />
  ) : null;

  if (variant === 'banner') {
    return (
      <>
        <div className="rounded-xl border border-orange-200 bg-orange-50 px-4 py-3 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-gray-900">Quản trị cửa hàng</p>
              <p className="mt-0.5 text-xs text-gray-600">
                Tài khoản của bạn được gán quyền quản trị.{roleHint ? ` (${roleHint})` : ''}
              </p>
            </div>
            {btn}
          </div>
        </div>
        {stepUpModal}
      </>
    );
  }

  return (
    <>
      {btn}
      {stepUpModal}
    </>
  );
}
