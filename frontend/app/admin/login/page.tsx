'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { adminLogin, adminLoginVerifyOtp, type AdminLoginResponse } from '@/lib/admin-api';
import { defaultAdminHome, setStoredAdminModules } from '@/lib/admin-role';
import { getApiBaseUrl, ngrokFetchHeaders } from '@/lib/api-base';

function safeAdminRedirect(value: string | null): string {
  const path = (value || '').trim();
  if (!path.startsWith('/') || path.startsWith('//') || !path.startsWith('/admin')) {
    return defaultAdminHome();
  }
  return path.slice(0, 512);
}

export default function AdminLoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [otp, setOtp] = useState('');
  const [challengeId, setChallengeId] = useState<string | null>(null);
  const [rememberDevice, setRememberDevice] = useState(true);
  const [step, setStep] = useState<'password' | 'otp'>('password');
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [loading, setLoading] = useState(false);
  const [resendIn, setResendIn] = useState(0);
  const [setupHint, setSetupHint] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${getApiBaseUrl()}/admin/check-setup`, { headers: ngrokFetchHeaders() })
      .then((response) => response.json())
      .then((data: { admin_exists?: boolean; hint?: string }) => {
        if (data.admin_exists === false && data.hint) setSetupHint(data.hint);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (resendIn <= 0) return;
    const timer = window.setInterval(() => setResendIn((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [resendIn]);

  const finishLogin = (data: AdminLoginResponse) => {
    if (!data.access_token) throw new Error('Phản hồi đăng nhập không có token.');
    localStorage.setItem('admin_token', data.access_token);
    localStorage.setItem('admin_role', data.role || '');
    setStoredAdminModules(data.modules ?? undefined);
    router.push(safeAdminRedirect(searchParams.get('redirect')));
  };

  const submitPassword = async (event?: React.FormEvent) => {
    event?.preventDefault();
    setError('');
    setInfo('');
    setLoading(true);
    try {
      const data = await adminLogin(username, password);
      if (data.otp_required && data.challenge_id) {
        setChallengeId(data.challenge_id);
        setStep('otp');
        setInfo(data.message || 'Đã gửi OTP tới email quản trị.');
        setResendIn(30);
        setOtp('');
        return;
      }
      finishLogin(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Đăng nhập thất bại');
    } finally {
      setLoading(false);
    }
  };

  const submitOtp = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!challengeId) return;
    setError('');
    setLoading(true);
    try {
      const data = await adminLoginVerifyOtp(challengeId, otp, rememberDevice);
      finishLogin(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Mã OTP không hợp lệ');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-white rounded-xl shadow-lg p-8">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-gray-900">188 Admin</h1>
          <p className="text-gray-500 mt-1">
            {step === 'password' ? 'Đăng nhập quản trị' : 'Xác minh thiết bị mới'}
          </p>
        </div>

        {setupHint ? (
          <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
            Chưa có tài khoản admin. {setupHint}
          </div>
        ) : null}
        {info ? (
          <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-700">{info}</div>
        ) : null}
        {error ? (
          <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}{' '}
            <button type="button" onClick={() => setError('')} className="font-medium underline">Đóng</button>
          </div>
        ) : null}

        {step === 'password' ? (
          <form onSubmit={submitPassword} className="space-y-4">
            <div>
              <label htmlFor="admin-username" className="block text-sm font-medium text-gray-700 mb-1">Tên đăng nhập</label>
              <input
                id="admin-username"
                type="text"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-blue-500 focus:ring-2 focus:ring-blue-200"
                required
                autoComplete="username"
              />
            </div>
            <div>
              <label htmlFor="admin-password" className="block text-sm font-medium text-gray-700 mb-1">Mật khẩu</label>
              <input
                id="admin-password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-blue-500 focus:ring-2 focus:ring-blue-200"
                required
                autoComplete="current-password"
              />
            </div>
            <button type="submit" disabled={loading} className="w-full rounded-xl bg-orange-600 py-3 font-medium text-white hover:bg-orange-700 disabled:opacity-60">
              {loading ? 'Đang kiểm tra…' : 'Tiếp tục'}
            </button>
          </form>
        ) : (
          <form onSubmit={submitOtp} className="space-y-4">
            <div>
              <label htmlFor="admin-otp" className="block text-sm font-medium text-gray-700 mb-1">Mã OTP</label>
              <input
                id="admin-otp"
                value={otp}
                onChange={(event) => setOtp(event.target.value.replace(/\D/g, '').slice(0, 8))}
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-center text-lg tracking-[0.35em] focus:border-orange-500 focus:ring-2 focus:ring-orange-200"
                required
              />
            </div>
            <label className="flex items-start gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={rememberDevice}
                onChange={(event) => setRememberDevice(event.target.checked)}
                className="mt-0.5"
              />
              Tin cậy thiết bị quản trị này trong 30 ngày
            </label>
            <button type="submit" disabled={loading || otp.length < 6} className="w-full rounded-xl bg-orange-600 py-3 font-medium text-white hover:bg-orange-700 disabled:opacity-60">
              {loading ? 'Đang xác minh…' : 'Xác minh và đăng nhập'}
            </button>
            <div className="flex items-center justify-between text-sm">
              <button type="button" onClick={() => setStep('password')} className="text-gray-600 underline">Quay lại</button>
              <button
                type="button"
                disabled={loading || resendIn > 0}
                onClick={() => void submitPassword()}
                className="font-medium text-orange-700 disabled:text-gray-400"
              >
                {resendIn > 0 ? `Gửi lại sau ${resendIn}s` : 'Gửi lại OTP'}
              </button>
            </div>
          </form>
        )}

        <p className="mt-6 text-center text-sm text-gray-500">
          <Link href="/" className="text-blue-600 hover:underline">Về trang chủ</Link>
        </p>
      </div>
    </div>
  );
}
