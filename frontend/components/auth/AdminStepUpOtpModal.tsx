'use client';

import { useCallback, useEffect, useState } from 'react';
import { adminStepUpAPI } from '@/lib/admin-api';
import { setAdminStepUp } from '@/lib/admin-step-up';

type Props = {
  title?: string;
  description?: string;
  onClose: () => void;
  onVerified: () => void | Promise<void>;
};

export default function AdminStepUpOtpModal({
  title = 'Xác minh OTP quản trị',
  description = 'Thao tác xóa hoặc import dữ liệu hàng loạt cần mã OTP gửi tới email quản trị.',
  onClose,
  onVerified,
}: Props) {
  const [challengeId, setChallengeId] = useState<string | null>(null);
  const [otp, setOtp] = useState('');
  const [error, setError] = useState('');
  const [sending, setSending] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [resendIn, setResendIn] = useState(30);

  const sendCode = useCallback(async () => {
    setSending(true);
    setError('');
    try {
      const result = await adminStepUpAPI.request();
      setChallengeId(result.challenge_id);
      setOtp('');
      setResendIn(30);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Không gửi được OTP. Vui lòng thử lại.');
    } finally {
      setSending(false);
    }
  }, []);

  useEffect(() => {
    void sendCode();
  }, [sendCode]);

  useEffect(() => {
    if (resendIn <= 0) return;
    const timer = window.setInterval(() => setResendIn((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [resendIn]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !verifying) onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose, verifying]);

  const verify = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!challengeId || otp.trim().length < 6) return;
    setVerifying(true);
    setError('');
    try {
      const result = await adminStepUpAPI.verify(challengeId, otp.trim());
      if (result.step_up_token) {
        setAdminStepUp(result.step_up_token, result.expires_in_minutes);
      }
      await onVerified();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Mã OTP không hợp lệ.');
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="admin-step-up-title"
    >
      <div className="w-full max-w-md rounded-xl bg-white p-6">
        <h2 id="admin-step-up-title" className="text-xl font-semibold text-gray-900">{title}</h2>
        <p className="mt-2 text-sm text-gray-600">{description}</p>
        <p className="mt-2 text-sm text-gray-600">
          Mã có hiệu lực khoảng 10 phút; các thao tác tiếp theo trong phiên không cần nhập lại.
        </p>

        {error ? (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        ) : null}

        <form onSubmit={verify} className="mt-5 space-y-4">
          <div>
            <label htmlFor="admin-step-up-otp" className="block text-sm font-medium text-gray-700">
              Mã OTP
            </label>
            <input
              id="admin-step-up-otp"
              value={otp}
              onChange={(event) => setOtp(event.target.value.replace(/\D/g, '').slice(0, 8))}
              inputMode="numeric"
              autoComplete="one-time-code"
              autoFocus
              disabled={sending || verifying}
              className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 tracking-[0.3em] focus:border-orange-500 focus:outline-none focus:ring-2 focus:ring-orange-200"
              placeholder="000000"
            />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <button
              type="button"
              onClick={() => void sendCode()}
              disabled={sending || verifying || resendIn > 0}
              className="text-sm font-medium text-orange-700 disabled:text-gray-400"
            >
              {sending ? 'Đang gửi…' : resendIn > 0 ? `Gửi lại sau ${resendIn}s` : 'Gửi lại mã'}
            </button>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={onClose}
                disabled={verifying}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700"
              >
                Hủy
              </button>
              <button
                type="submit"
                disabled={sending || verifying || !challengeId || otp.length < 6}
                className="rounded-lg bg-orange-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
              >
                {verifying ? 'Đang xác minh…' : 'Xác minh'}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
