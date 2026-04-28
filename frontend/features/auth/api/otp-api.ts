// frontend/features/auth/api/otp-api.ts - HOÀN CHỈNH
import { getApiBaseUrl, ngrokFetchHeaders } from '@/lib/api-base';
import { OTPRequest, OTPVerify } from '../types/auth';

export interface OTPResponse {
  message: string;
  phone: string;
  provider: string;
  fallback_used: boolean;
  simulated?: boolean;
}

export interface ProviderStatus {
  current_provider: string;
  zalo_configured: boolean;
  firebase_configured: boolean;
  fallback_enabled: boolean;
  otp_expire_minutes: number;
  otp_length: number;
}

class APIError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'APIError';
  }
}

const handleResponse = async (response: Response) => {
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new APIError(response.status, errorData.detail || `HTTP error! status: ${response.status}`);
  }
  return response.json();
};

export const otpAPI = {
  // Send OTP with provider fallback
  sendOTP: async (otpRequest: OTPRequest): Promise<OTPResponse> => {
    const response = await fetch(`${getApiBaseUrl()}/otp/send-otp`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(otpRequest),
    });
    return handleResponse(response);
  },

  // Enhanced OTP verification
  verifyOTPEnhanced: async (otpVerify: OTPVerify): Promise<{ 
    message: string; 
    verified: boolean; 
    phone: string;
    provider: string;
  }> => {
    const response = await fetch(`${getApiBaseUrl()}/otp/verify-otp-enhanced`, {
      method: 'POST',
      headers: {
        ...ngrokFetchHeaders(),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(otpVerify),
    });
    return handleResponse(response);
  },

  // Get OTP provider status
  getProviderStatus: async (): Promise<ProviderStatus> => {
    const response = await fetch(`${getApiBaseUrl()}/otp/provider-status`, {
      headers: { ...ngrokFetchHeaders() },
    });
    return handleResponse(response);
  },

  // Update fallback settings
  updateFallbackSettings: async (enabled: boolean): Promise<{ message: string; fallback_enabled: boolean }> => {
    const response = await fetch(`${getApiBaseUrl()}/otp/fallback-settings?enabled=${enabled}`, {
      method: 'PUT',
      headers: { ...ngrokFetchHeaders() },
    });
    return handleResponse(response);
  }
};

export default otpAPI;
