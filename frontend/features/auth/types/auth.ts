// fix_auth_types.ts
// Copy nội dung này vào: frontend/features/auth/types/auth.ts

export interface UserBase {
  email?: string;
  phone?: string;
  full_name?: string;
  date_of_birth?: string;
  gender?: 'male' | 'female' | 'other';
  address?: string;
}

export interface UserCreate extends UserBase {
  // KHÔNG password field
}

export interface UserLogin {
  phone?: string;
  password?: string;
  date_of_birth?: string;
}

export interface UserResponse extends UserBase {
  id: number;
  avatar?: string;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  updated_at?: string;
  last_login?: string;
  /** Backend: có admin_users.linked_user_id → vào admin qua menu */
  has_linked_admin?: boolean;
  linked_admin_role?: string | null;
  linked_admin_username?: string | null;
  /** Quyền mục khi có admin liên kết (granular hoặc preset). */
  linked_admin_modules?: string[] | null;
}

export interface Token {
  access_token: string;
  token_type: string;
  user: UserResponse;
}

export interface AuthState {
  user: UserResponse | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

export interface OTPRequest {
  phone: string;
  provider?: string;
  channel?: string;
}

export interface OTPVerify {
  phone: string;
  otp_code: string;
  provider?: string;
}
