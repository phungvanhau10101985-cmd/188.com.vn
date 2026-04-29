// frontend/features/auth/hooks/useAuth.tsx - FIXED VERSION
'use client';

import { useState, useEffect, createContext, useContext, ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import { UserResponse, AuthState, Token } from '../types/auth';
import { authAPI } from '../api/auth-api';
import { getLoginRedirectFromUrl } from '@/lib/auth-redirect';
import { markFreshLoginSession } from '@/lib/birthday-prompt-session';

interface AuthContextType extends AuthState {
  /** Gửi kèm deviceId để coi trình duyệt này là thiết bị đã xác thực (cùng logic đăng nhập bằng mã email) */
  loginWithGoogle: (idToken: string, deviceId?: string) => Promise<void>;
  /** Đăng nhập/đăng ký bằng mã gửi tới email; JWT dài hạn theo cấu hình backend */
  loginWithEmailOtp: (email: string, code: string, deviceId?: string) => Promise<void>;
  /** Lưu phiên sau khi API trả về access_token (OTP hoặc thiết bị tin cậy). `nextPath` ưu tiên hơn ?redirect= trên URL. */
  setSessionFromToken: (result: Token, nextPath?: string | null) => void;
  /** JWT chỉ trong cookie httpOnly; chỉ lưu user ở client */
  setSessionFromEmailAuth: (user: UserResponse, nextPath?: string) => void;
  logout: () => void;
  /** Xoá phiên hiện tại và mở trang đăng nhập (để đăng nhập tài khoản khác). `returnPath`: đường dẫn sau khi đăng nhập lại. */
  switchAccount: (returnPath: string) => void;
  updateUser: (userData: Partial<UserResponse>) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authState, setAuthState] = useState<AuthState>({
    user: null,
    token: null,
    isAuthenticated: false,
    isLoading: true
  });

  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    const userRaw = localStorage.getItem('user');

    if (userRaw) {
      try {
        setAuthState({
          user: JSON.parse(userRaw),
          token: token,
          isAuthenticated: true,
          isLoading: false,
        });
        return;
      } catch {
        localStorage.removeItem('user');
      }
    }
    setAuthState((prev) => ({ ...prev, isLoading: false }));
  }, []);

  const mergeGuestBehavior = async (): Promise<void> => {
    try {
      const { apiClient } = await import('@/lib/api-client');
      await apiClient.mergeGuestBehaviorSession();
    } catch {
      /* ignore */
    }
  };

  const applyTokenSession = async (result: Token, nextPath?: string | null) => {
    localStorage.setItem('access_token', result.access_token);
    localStorage.setItem('user', JSON.stringify(result.user));
    setAuthState({
      user: result.user,
      token: result.access_token,
      isAuthenticated: true,
      isLoading: false
    });
    await mergeGuestBehavior();
    markFreshLoginSession();
    const fromApi =
      nextPath && nextPath.startsWith('/') && !nextPath.startsWith('//') ? nextPath : null;
    router.push(fromApi ?? getLoginRedirectFromUrl());
  };

  const setSessionFromEmailAuth = async (user: UserResponse, nextPath?: string) => {
    localStorage.removeItem('access_token');
    localStorage.setItem('user', JSON.stringify(user));
    setAuthState({
      user,
      token: null,
      isAuthenticated: true,
      isLoading: false,
    });
    await mergeGuestBehavior();
    markFreshLoginSession();
    const dest =
      nextPath && nextPath.startsWith('/') && !nextPath.startsWith('//')
        ? nextPath
        : getLoginRedirectFromUrl();
    router.push(dest);
  };

  const loginWithGoogle = async (idToken: string, deviceId?: string) => {
    try {
      const result = await authAPI.googleLogin(idToken, deviceId);
      await applyTokenSession(result);
    } catch (error: any) {
      throw new Error(error.message || 'Đăng nhập Gmail thất bại');
    }
  };

  const loginWithEmailOtp = async (email: string, code: string, deviceId?: string) => {
    try {
      const result = await authAPI.verifyEmailOtp(email, code, deviceId);
      await applyTokenSession(result);
    } catch (error: any) {
      throw new Error(error.message || 'Xác nhận mã email thất bại');
    }
  };

  const logout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
    // Cookie JWT httpOnly chỉ backend mới xoá được; phiên client được xoá ở đây.

    setAuthState({
      user: null,
      token: null,
      isAuthenticated: false,
      isLoading: false
    });

    router.push('/');
  };

  const switchAccount = (returnPath: string) => {
    const safe =
      returnPath.startsWith('/') && !returnPath.startsWith('//') ? returnPath : '/account';
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
    setAuthState({
      user: null,
      token: null,
      isAuthenticated: false,
      isLoading: false,
    });
    router.push(
      '/auth/login?redirect=' + encodeURIComponent(safe) + '&switch=1'
    );
  };

  const updateUser = (userData: Partial<UserResponse>) => {
    if (authState.user) {
      const updatedUser = { ...authState.user, ...userData };
      setAuthState(prev => ({ ...prev, user: updatedUser }));
      localStorage.setItem('user', JSON.stringify(updatedUser));
    }
  };

  const value: AuthContextType = {
    ...authState,
    loginWithGoogle,
    loginWithEmailOtp,
    setSessionFromToken: (result: Token, nextPath?: string | null) =>
      applyTokenSession(result, nextPath),
    setSessionFromEmailAuth,
    logout,
    switchAccount,
    updateUser
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}