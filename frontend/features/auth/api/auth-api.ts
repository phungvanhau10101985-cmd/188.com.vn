// frontend/features/auth/api/auth-api.ts - FIXED VERSION

import { getApiBaseUrl, ngrokFetchHeaders } from '@/lib/api-base';
import { 
  UserCreate, 
  UserLogin, 
  UserResponse, 
  Token,
} from '../types/auth';

const withCreds = (init: RequestInit = {}): RequestInit => ({
  ...init,
  credentials: 'include',
});

/** Headers JSON + bỏ qua trang cảnh báo ngrok khi cần */
const jsonHeaders = (extra: Record<string, string> = {}): Record<string, string> => ({
  ...ngrokFetchHeaders(),
  'Content-Type': 'application/json',
  ...extra,
});

class APIError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'APIError';
  }
}

const handleResponse = async (response: Response) => {
  console.log(`🔍 Auth API Response: ${response.status}`);
  
  if (!response.ok) {
    const errorText = await response.text();
    console.error(`❌ Auth API Error ${response.status}:`, errorText);
    
    let errorData;
    try {
      errorData = JSON.parse(errorText);
    } catch {
      errorData = { detail: errorText || `HTTP error! status: ${response.status}` };
    }
    
    const d = errorData.detail;
    const detailMsg = Array.isArray(d)
      ? d.map((x: { msg?: string }) => x?.msg).filter(Boolean).join(' ') || String(response.status)
      : (typeof d === 'string' ? d : d != null ? String(d) : `HTTP error! status: ${response.status}`);
    throw new APIError(response.status, detailMsg);
  }
  
  const data = await response.json();
  console.log('✅ Auth API Success:', data);
  return data;
};

export const authAPI = {
  // Google OAuth login
  googleLogin: async (idToken: string, deviceId?: string): Promise<Token> => {
    const payload: { id_token: string; device_id?: string } = { id_token: idToken };
    if (deviceId && deviceId.length >= 8) {
      payload.device_id = deviceId;
    }
    const response = await fetch(`${getApiBaseUrl()}/auth/google`, {
      ...withCreds(),
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify(payload),
    });
    return handleResponse(response);
  },

  sendEmailOtp: async (email: string): Promise<{ message: string; email: string }> => {
    const response = await fetch(`${getApiBaseUrl()}/auth/send-email-otp`, {
      ...withCreds(),
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify({ email: email.trim() }),
    });
    return handleResponse(response);
  },

  tryTrustedDevice: async (
    email: string,
    deviceId: string
  ): Promise<{
    ok: boolean;
    require_otp: boolean;
    access_token?: string;
    token_type?: string;
    user?: UserResponse;
  }> => {
    const response = await fetch(`${getApiBaseUrl()}/auth/try-trusted-device`, {
      ...withCreds(),
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify({ email: email.trim(), device_id: deviceId }),
    });
    return handleResponse(response);
  },

  verifyEmailOtp: async (email: string, code: string, deviceId?: string): Promise<Token> => {
    const payload: { email: string; code: string; device_id?: string } = {
      email: email.trim(),
      code: code.trim(),
    };
    if (deviceId && deviceId.length >= 8) {
      payload.device_id = deviceId;
    }
    const response = await fetch(`${getApiBaseUrl()}/auth/verify-email-otp`, {
      ...withCreds(),
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify(payload),
    });
    return handleResponse(response);
  },

  /** Luồng mới: OTP + magic link + cookie httpOnly */
  emailAuthRequest: async (body: {
    email: string;
    next?: string;
    remember_device: boolean;
    browser_id: string;
  }): Promise<{
    auto_signed_in: boolean;
    next?: string;
    message?: string;
    user?: UserResponse;
    access_token?: string;
    token_type?: string;
  }> => {
    const response = await fetch(`${getApiBaseUrl()}/auth/email/request`, {
      ...withCreds(),
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify({
        email: body.email.trim(),
        next: body.next ?? '/',
        remember_device: body.remember_device,
        browser_id: body.browser_id,
      }),
    });
    return handleResponse(response);
  },

  emailAuthVerifyOtp: async (body: {
    email: string;
    otp: string;
    remember_device: boolean;
    browser_id: string;
    next?: string;
  }): Promise<{
    auto_signed_in: boolean;
    next?: string;
    user?: UserResponse;
    access_token?: string;
    token_type?: string;
  }> => {
    const response = await fetch(`${getApiBaseUrl()}/auth/email/verify-otp`, {
      ...withCreds(),
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify({
        email: body.email.trim(),
        otp: body.otp.trim(),
        remember_device: body.remember_device,
        browser_id: body.browser_id,
        next: body.next ?? '/',
      }),
    });
    return handleResponse(response);
  },

  // Gửi OTP đăng ký (Zalo ưu tiên, fallback Firebase)
  sendRegisterOtp: async (phone: string): Promise<{ message: string; phone: string; provider: string; fallback_used?: boolean }> => {
    const response = await fetch(`${getApiBaseUrl()}/auth/send-register-otp`, {
      ...withCreds(),
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify({ phone: phone.trim() }),
    });
    return handleResponse(response);
  },

  // Đăng ký tài khoản (bắt buộc có otp_code)
  register: async (userData: UserCreate & { otp_code?: string }): Promise<UserResponse> => {
    console.log('🔐 Register:', userData);
    
    const response = await fetch(`${getApiBaseUrl()}/auth/register`, {
      ...withCreds(),
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify(userData),
    });
    return handleResponse(response);
  },

  // Đăng nhập - ĐƠN GIẢN HÓA
  login: async (credentials: UserLogin): Promise<Token> => {
    console.log('🔐 Login attempt:', credentials);
    
    // Đảm bảo có date_of_birth
    if (!credentials.date_of_birth) {
      throw new Error('Vui lòng nhập ngày sinh');
    }

    const payload = {
      phone: credentials.phone,
      date_of_birth: credentials.date_of_birth
    };

    console.log('📤 Login payload:', payload);

    const response = await fetch(`${getApiBaseUrl()}/auth/login`, {
      ...withCreds(),
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify(payload),
    });

    const result = await handleResponse(response);
    
    // Lưu token vào localStorage
    if (result.access_token && typeof window !== 'undefined') {
      localStorage.setItem('access_token', result.access_token);
      console.log('💾 Token saved to localStorage');
    }
    
    return result;
  },

  // Gửi OTP quên ngày sinh (Zalo ưu tiên, fallback Firebase)
  sendForgotDobOtp: async (phone: string): Promise<{ message: string; phone: string; provider: string; fallback_used?: boolean }> => {
    const response = await fetch(`${getApiBaseUrl()}/auth/send-forgot-dob-otp`, {
      ...withCreds(),
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify({ phone: phone.trim() }),
    });
    return handleResponse(response);
  },

  // Lấy lại ngày sinh (quên ngày sinh) - BẮT BUỘC có OTP (gửi qua sendForgotDobOtp trước)
  getDateOfBirth: async (phone: string, otpCode: string): Promise<{ phone: string, date_of_birth: string, full_name: string }> => {
    const response = await fetch(`${getApiBaseUrl()}/auth/forgot-date-of-birth`, {
      ...withCreds(),
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify({ phone: phone.trim(), otp_code: otpCode.trim() }),
    });
    return handleResponse(response);
  },

  // Lấy thông tin user
  getProfile: async (): Promise<UserResponse> => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    
    if (!token) {
      throw new Error('No authentication token');
    }

    console.log('👤 Getting profile with token:', token.substring(0, 50) + '...');

    const response = await fetch(`${getApiBaseUrl()}/auth/me`, {
      ...withCreds(),
      headers: jsonHeaders({
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      }),
    });
    return handleResponse(response);
  },

  // Cập nhật thông tin user
  updateProfile: async (userData: any): Promise<UserResponse> => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    
    if (!token) {
      throw new Error('No authentication token');
    }

    console.log('✏️ Updating profile:', userData);

    const response = await fetch(`${getApiBaseUrl()}/auth/me`, {
      ...withCreds(),
      method: 'PUT',
      headers: jsonHeaders({
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      }),
      body: JSON.stringify(userData),
    });
    return handleResponse(response);
  },

  // Kiểm tra token
  checkAuth: async (): Promise<boolean> => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    
    if (!token) {
      console.log('🔒 No token found');
      return false;
    }

    try {
      await authAPI.getProfile();
      console.log('✅ Token is valid');
      return true;
    } catch (error) {
      console.log('❌ Token invalid:', error);
      // Xóa token nếu invalid
      if (typeof window !== 'undefined') {
        localStorage.removeItem('access_token');
      }
      return false;
    }
  },

  // Đăng xuất
  logout: (): void => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('access_token');
      localStorage.removeItem('user');
      console.log('👋 Logged out');
    }
  }
};