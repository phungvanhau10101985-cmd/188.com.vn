const STORAGE_TOKEN = '188_admin_step_up_token';
const STORAGE_UNTIL = '188_admin_step_up_until';
const STORAGE_ADMIN_ID = '188_admin_step_up_admin_id';

function readAdminToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('admin_token');
}

/** Decode admin id từ JWT (chỉ để khớp phiên step-up, không verify chữ ký). */
export function decodeAdminIdFromToken(token: string | null): number | null {
  if (!token) return null;
  try {
    const part = token.split('.')[1];
    if (!part) return null;
    const json = JSON.parse(atob(part.replace(/-/g, '+').replace(/_/g, '/'))) as { sub?: unknown };
    const id = Number.parseInt(String(json.sub ?? ''), 10);
    return Number.isFinite(id) ? id : null;
  } catch {
    return null;
  }
}

export function getCurrentAdminId(): number | null {
  return decodeAdminIdFromToken(readAdminToken());
}

export function getAdminStepUpToken(): string | null {
  if (typeof window === 'undefined') return null;
  const until = Number(sessionStorage.getItem(STORAGE_UNTIL) || 0);
  if (until <= Date.now()) {
    clearAdminStepUp();
    return null;
  }
  const token = sessionStorage.getItem(STORAGE_TOKEN);
  if (!token) return null;

  const boundAdminId = sessionStorage.getItem(STORAGE_ADMIN_ID);
  const currentAdminId = getCurrentAdminId();
  if (!boundAdminId || currentAdminId === null || String(currentAdminId) !== boundAdminId) {
    clearAdminStepUp();
    return null;
  }
  return token;
}

export function setAdminStepUp(token: string, expiresInMinutes: number, adminId?: number | null): void {
  if (typeof window === 'undefined') return;
  const resolvedAdminId = adminId ?? getCurrentAdminId();
  if (resolvedAdminId === null) {
    clearAdminStepUp();
    return;
  }
  sessionStorage.setItem(STORAGE_TOKEN, token);
  sessionStorage.setItem(STORAGE_UNTIL, String(Date.now() + expiresInMinutes * 60_000));
  sessionStorage.setItem(STORAGE_ADMIN_ID, String(resolvedAdminId));
}

export function clearAdminStepUp(): void {
  if (typeof window === 'undefined') return;
  sessionStorage.removeItem(STORAGE_TOKEN);
  sessionStorage.removeItem(STORAGE_UNTIL);
  sessionStorage.removeItem(STORAGE_ADMIN_ID);
}

export function hasRecentAdminStepUp(): boolean {
  return Boolean(getAdminStepUpToken());
}

export class AdminStepUpRequiredError extends Error {
  readonly code = 'admin_step_up_required';

  constructor(message = 'Cần xác minh OTP quản trị để tiếp tục.') {
    super(message);
    this.name = 'AdminStepUpRequiredError';
  }
}

export type AdminStepUpRetryFn<T> = () => Promise<T>;

let stepUpPromptHandler: (<T>(retry: AdminStepUpRetryFn<T>) => Promise<T>) | null = null;

export function registerAdminStepUpPromptHandler(
  handler: <T>(retry: AdminStepUpRetryFn<T>) => Promise<T>,
): void {
  stepUpPromptHandler = handler;
}

export function unregisterAdminStepUpPromptHandler(): void {
  stepUpPromptHandler = null;
}

export async function promptAdminStepUpAndRetry<T>(retry: AdminStepUpRetryFn<T>): Promise<T> {
  if (hasRecentAdminStepUp()) {
    return retry();
  }
  if (!stepUpPromptHandler) {
    throw new AdminStepUpRequiredError();
  }
  return stepUpPromptHandler(retry);
}

export function adminStepUpHeaders(): Record<string, string> {
  const token = getAdminStepUpToken();
  return token ? { 'X-Admin-Step-Up': token } : {};
}

export function isAdminStepUpRequiredDetail(detail: unknown): boolean {
  if (!detail || typeof detail !== 'object') return false;
  const code = (detail as { code?: string }).code;
  return code === 'admin_step_up_required';
}

/** Gọi khi đổi phiên admin (login / Quản trị web) để tránh dùng OTP của admin khác. */
export function resetAdminStepUpForNewSession(): void {
  clearAdminStepUp();
}
