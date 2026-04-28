/** Gắn cờ sau đăng nhập để hiện popup nhắc ngày sinh / giới tính (ưu đãi sinh nhật). */

export const BIRTH_PROMPT_FRESH_LOGIN = '188_fresh_login_after_auth';

const DISMISS_KEY = '188_birth_gender_prompt_dismissed';

export function markFreshLoginSession(): void {
  if (typeof sessionStorage === 'undefined') return;
  try {
    sessionStorage.removeItem(DISMISS_KEY);
    sessionStorage.setItem(BIRTH_PROMPT_FRESH_LOGIN, '1');
  } catch {
    /* quota / private mode */
  }
}

export function clearFreshLoginSession(): void {
  if (typeof sessionStorage === 'undefined') return;
  sessionStorage.removeItem(BIRTH_PROMPT_FRESH_LOGIN);
}

export function isFreshLoginSession(): boolean {
  if (typeof sessionStorage === 'undefined') return false;
  return sessionStorage.getItem(BIRTH_PROMPT_FRESH_LOGIN) === '1';
}
