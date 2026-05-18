export const BIRTHDAY_DISCOUNT_PERCENT = 10;
export const BIRTHDAY_OFFER_DAYS_BEFORE_MIN = 1;
export const BIRTHDAY_OFFER_DAYS_BEFORE_MAX = 7;

export interface BirthdayDiscountState {
  active: boolean;
  percent: number;
  daysUntil: number | null;
  nextBirthdayLabel: string | null;
  isTestMode?: boolean;
}

export const BIRTHDAY_PROMO_TEST_STORAGE_KEY = '188_admin_test_birthday_promo_enabled';

export function setBirthdayPromoTestMode(enabled: boolean): void {
  if (typeof window === 'undefined') return;
  try {
    if (enabled) localStorage.setItem(BIRTHDAY_PROMO_TEST_STORAGE_KEY, '1');
    else localStorage.removeItem(BIRTHDAY_PROMO_TEST_STORAGE_KEY);
    window.dispatchEvent(new Event('188-birthday-promo-test-mode-changed'));
  } catch {
    /* noop */
  }
}

export function isBirthdayPromoTestModeEnabled(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return localStorage.getItem(BIRTHDAY_PROMO_TEST_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

function parseDateOnly(value?: string | null): Date | null {
  if (!value) return null;
  const parts = value.slice(0, 10).split('-').map((p) => Number(p));
  if (parts.length !== 3 || parts.some((n) => !Number.isFinite(n))) return null;
  const [year, month, day] = parts;
  const date = new Date(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
    return null;
  }
  return date;
}

function formatDateOnly(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function startOfToday(): Date {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

function nextBirthdayFor(dob: Date, today: Date): Date {
  let year = today.getFullYear();
  while (true) {
    const candidate = new Date(year, dob.getMonth(), dob.getDate());
    if (candidate.getMonth() === dob.getMonth() && candidate.getDate() === dob.getDate() && candidate >= today) {
      return candidate;
    }
    if (dob.getMonth() === 1 && dob.getDate() === 29) {
      const leapFallback = new Date(year, 1, 28);
      if (leapFallback >= today) return leapFallback;
    }
    year += 1;
  }
}

export function getBirthdayDiscountState(dateOfBirth?: string | null): BirthdayDiscountState {
  const dob = parseDateOnly(dateOfBirth);
  if (!dob) {
    return { active: false, percent: 0, daysUntil: null, nextBirthdayLabel: null };
  }

  const today = startOfToday();
  const nextBirthday = nextBirthdayFor(dob, today);
  const daysUntil = Math.round((nextBirthday.getTime() - today.getTime()) / 86_400_000);
  const minDays = Math.min(BIRTHDAY_OFFER_DAYS_BEFORE_MIN, BIRTHDAY_OFFER_DAYS_BEFORE_MAX);
  const maxDays = Math.max(BIRTHDAY_OFFER_DAYS_BEFORE_MIN, BIRTHDAY_OFFER_DAYS_BEFORE_MAX);
  const active = daysUntil === 0 || (daysUntil >= minDays && daysUntil <= maxDays);

  return {
    active,
    percent: active ? BIRTHDAY_DISCOUNT_PERCENT : 0,
    daysUntil,
    nextBirthdayLabel: formatDateOnly(nextBirthday),
  };
}

export function birthdayDiscountStateFromBackend(input?: {
  active?: boolean;
  percent?: number | null;
  days_until?: number | null;
  next_birthday?: string | null;
} | null): BirthdayDiscountState | null {
  if (input == null) return null;
  const shared = {
    daysUntil: input.days_until ?? null,
    nextBirthdayLabel: input.next_birthday ?? null,
  };
  if (input.active !== true) {
    return { active: false, percent: 0, ...shared };
  }
  const percent = Math.min(100, Math.max(0, Math.floor(Number(input.percent ?? 0))));
  if (percent <= 0) {
    return { active: false, percent: 0, ...shared };
  }
  return {
    active: true,
    percent,
    ...shared,
  };
}

export function applyBirthdayDiscount(price: number, percent = BIRTHDAY_DISCOUNT_PERCENT): number {
  const safePrice = Number.isFinite(price) ? Math.max(0, price) : 0;
  const safePercent = Math.min(100, Math.max(0, Math.floor(percent)));
  return Math.max(0, safePrice * (1 - safePercent / 100));
}
