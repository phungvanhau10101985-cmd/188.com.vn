const STORAGE_TOKEN = '188_admin_step_up_token';
const STORAGE_UNTIL = '188_admin_step_up_until';

export function getAdminStepUpToken(): string | null {
  if (typeof window === 'undefined') return null;
  const until = Number(sessionStorage.getItem(STORAGE_UNTIL) || 0);
  if (until <= Date.now()) {
    clearAdminStepUp();
    return null;
  }
  return sessionStorage.getItem(STORAGE_TOKEN);
}

export function setAdminStepUp(token: string, expiresInMinutes: number): void {
  if (typeof window === 'undefined') return;
  sessionStorage.setItem(STORAGE_TOKEN, token);
  sessionStorage.setItem(STORAGE_UNTIL, String(Date.now() + expiresInMinutes * 60_000));
}

export function clearAdminStepUp(): void {
  if (typeof window === 'undefined') return;
  sessionStorage.removeItem(STORAGE_TOKEN);
  sessionStorage.removeItem(STORAGE_UNTIL);
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
