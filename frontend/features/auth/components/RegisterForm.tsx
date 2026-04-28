// frontend/features/auth/components/RegisterForm.tsx - HOÀN CHỈNH (ĐÃ FIX MÀU SẮC)
'use client';

import { useState } from 'react';
import Link from 'next/link';
import GoogleLoginButton from './GoogleLoginButton';
import EmailOtpPanel from './EmailOtpPanel';
import { useAuth } from '../hooks/useAuth';
import { getOrCreateDeviceId } from '@/lib/auth-device-id';

export default function RegisterForm() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const { loginWithGoogle } = useAuth();

  const handleGoogleCredential = async (idToken: string) => {
    setLoading(true);
    setError('');
    try {
      await loginWithGoogle(idToken, getOrCreateDeviceId());
    } catch (err: any) {
      setError(err.message || 'Đăng ký Gmail thất bại');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md mx-auto">
      <div className="bg-white rounded-2xl shadow border border-gray-200 p-6">
        <div className="text-center mb-4">
          <h2 className="text-xl font-bold text-gray-900">Đăng ký</h2>
          <p className="text-sm text-gray-500 mt-0.5">Gmail hoặc mã gửi tới email</p>
        </div>

        {error && (
          <div className="mb-4 bg-red-50 border border-red-200 rounded-lg p-3 flex items-center gap-2">
            <svg className="h-4 w-4 text-red-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        <div className="space-y-4">
          <GoogleLoginButton
            onCredential={handleGoogleCredential}
            onError={(msg) => setError(msg)}
          />
          {loading && (
            <div className="text-center text-sm text-gray-500">Đang xử lý...</div>
          )}
          <EmailOtpPanel />
        </div>

        <p className="mt-4 text-center text-sm text-gray-500">
          Đã có tài khoản? <Link href="/auth/login" className="text-blue-600 font-medium hover:underline">Đăng nhập</Link>
        </p>
      </div>
    </div>
  );
}