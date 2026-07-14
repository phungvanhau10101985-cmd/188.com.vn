'use client';

import { useCallback, useEffect, useState } from 'react';
import { apiClient } from '@/lib/api-client';

export type StepUpPurpose = 'sensitive_action' | 'admin_elevation';

const STORAGE_PREFIX = '188_step_up_until_';

export function hasRecentStepUp(purpose: StepUpPurpose): boolean {
  if (typeof window === 'undefined') return false;
  return Number(sessionStorage.getItem(`${STORAGE_PREFIX}${purpose}`) || 0) > Date.now();
}

export function clearRecentStepUp(purpose: StepUpPurpose): void {
  if (typeof window !== 'undefined') {
    sessionStorage.removeItem(`${STORAGE_PREFIX}${purpose}`);
  }
}

type Props = {
  purpose: StepUpPurpose;
  title: string;
  description: string;
  onVerified: () => void | Promise<void>;
  onClose: () => void;
};

export default function StepUpOtpModal({
  purpose,
  title,
  description,
  onVerified,
  onClose,
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
      const result = await apiClient.requestStepUp(purpose);
      setChallengeId(result.challenge_id);
      setOtp('');
      setResendIn(30);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Không gửi được OTP. Vui lòng thử lại.');
    } finally {
      setSending(false);
    }
  }, [purpose]);

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
      const result = await apiClient.verifyStepUp(challengeId, otp.trim());
      sessionStorage.setItem(
        `${STORAGE_PREFIX}${purpose}`,
        String(Date.now() + result.expires_in_minutes * 60_000),
      );
      await onVerified();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Mã OTP không hợp lệ.');
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="step-up-title"
    >
      <div className="w-full max-w-md rounded-xl bg-white p-6">
        <h2 id="step-up-title" className="text-xl font-semibold text-gray-900">{title}</h2>
        <p className="mt-2 text-sm text-gray-600">{description}</p>
        <p className="mt-2 text-sm text-gray-600">Mã xác minh được gửi tới email tài khoản và có hiệu lực 10 phút.</p>

        {error ? (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        ) : null}

        <form onSubmit={verify} className="mt-5 space-y-4">
          <div>
            <label htmlFor="step-up-otp" className="block text-sm font-medium text-gray-700">Mã OTP</label>
            <input
              id="step-up-otp"
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
