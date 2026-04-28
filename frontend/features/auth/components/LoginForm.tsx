// frontend/features/auth/components/LoginForm.tsx - ĐÃ SỬA
'use client';

import { useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import GoogleLoginButton from './GoogleLoginButton';
import EmailOtpPanel from './EmailOtpPanel';
import { getOrCreateDeviceId } from '@/lib/auth-device-id';

export default function LoginForm() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const { loginWithGoogle } = useAuth();

  const handleGoogleCredential = async (idToken: string) => {
    setLoading(true);
    setError('');
    try {
      const deviceId = getOrCreateDeviceId();
      await loginWithGoogle(idToken, deviceId);
    } catch (err: any) {
      setError(err.message || 'Đăng nhập Gmail thất bại');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md mx-auto">
      <div className="bg-white rounded-2xl shadow-lg border border-gray-200 p-8">
        <div className="text-center mb-8">
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Đăng Nhập</h2>
          <p className="text-gray-600">Chào mừng trở lại 188.com.vn</p>
          <p className="text-gray-500 text-sm mt-1">Đăng nhập bằng Gmail hoặc mã gửi tới email</p>
        </div>
        
        {error && (
          <div className="mb-6 bg-red-50 border border-red-200 rounded-xl p-4">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3">
                <p className="text-sm text-red-700">{error}</p>
              </div>
            </div>
          </div>
        )}

        <div className="space-y-4">
          <GoogleLoginButton
            onCredential={handleGoogleCredential}
            onError={(msg) => setError(msg)}
          />
          {loading && (
            <div className="text-center text-sm text-gray-500">Đang đăng nhập...</div>
          )}
          <EmailOtpPanel />
        </div>
      </div>
    </div>
  );
}