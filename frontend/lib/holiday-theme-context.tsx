'use client';

import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import {
  fetchPublicHolidayTheme,
  formatHolidayYear,
  type HolidayThemeId,
  type PublicHolidayTheme,
} from '@/lib/holiday-theme';
import { isHolidayThemeId } from '@/lib/holiday-themes';
import {
  clearHolidayAdminPreview,
  readHolidayAdminPreview,
  startHolidayAdminPreview,
  type HolidayAdminPreview,
} from '@/lib/holiday-preview';

const HolidayThemeContext = createContext<HolidayThemeId | null>(null);
const HolidayYearContext = createContext('');
const HolidayPreviewContext = createContext<{ active: boolean; remainingMs: number; clear: () => void }>({
  active: false,
  remainingMs: 0,
  clear: () => {},
});

export function HolidayThemeProvider({
  initialSnapshot,
  children,
}: {
  initialSnapshot: PublicHolidayTheme | null;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [remote, setRemote] = useState<HolidayThemeId | null>(initialSnapshot?.theme ?? null);
  const [remoteYear, setRemoteYear] = useState<number | null>(initialSnapshot?.year ?? null);
  const [remoteYearEnd, setRemoteYearEnd] = useState<number | null>(initialSnapshot?.yearEnd ?? null);
  const [years, setYears] = useState<Record<string, number>>(initialSnapshot?.years ?? {});
  const [storedPreview, setStoredPreview] = useState<HolidayThemeId | null>(null);
  const [expiresAt, setExpiresAt] = useState(0);
  const [dismissed, setDismissed] = useState(false);
  const [now, setNow] = useState(0);

  const param = searchParams.get('preview_holiday');

  const applyStored = useCallback((preview: HolidayAdminPreview | null) => {
    setStoredPreview(preview?.code ?? null);
    setExpiresAt(preview?.expiresAt ?? 0);
  }, []);

  useLayoutEffect(() => {
    setNow(Date.now());
    if (param === 'off' || param === '0') {
      clearHolidayAdminPreview();
      applyStored(null);
      setDismissed(true);
      return;
    }
    if (isHolidayThemeId(param)) {
      const existing = readHolidayAdminPreview();
      applyStored(existing?.code === param ? existing : startHolidayAdminPreview(param));
      setDismissed(false);
      return;
    }
    applyStored(readHolidayAdminPreview());
  }, [applyStored, param]);

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key && event.key !== '188-holiday-admin-preview' && event.key !== 'admin_token') return;
      applyStored(readHolidayAdminPreview());
      setDismissed(false);
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, [applyStored]);

  useEffect(() => {
    if (!storedPreview) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [storedPreview]);

  useEffect(() => {
    if (!storedPreview || expiresAt <= 0 || now < expiresAt) return;
    clearHolidayAdminPreview();
    applyStored(null);
  }, [applyStored, expiresAt, now, storedPreview]);

  useEffect(() => {
    let cancel = false;
    fetchPublicHolidayTheme().then((next) => {
      if (cancel || next === undefined) return;
      setRemote(next.theme);
      setRemoteYear(next.year);
      setRemoteYearEnd(next.yearEnd);
      setYears(next.years);
    });
    return () => {
      cancel = true;
    };
  }, [pathname]);

  const clearPreview = useCallback(() => {
    clearHolidayAdminPreview();
    applyStored(null);
    setDismissed(true);
    if (!searchParams.has('preview_holiday')) return;
    const params = new URLSearchParams(searchParams.toString());
    params.delete('preview_holiday');
    const q = params.toString();
    router.replace(q ? `${pathname}?${q}` : pathname || '/', { scroll: false });
  }, [applyStored, pathname, router, searchParams]);

  const isAdmin = Boolean(pathname?.startsWith('/admin'));
  const previewId = !isAdmin && !dismissed ? storedPreview : null;
  const theme: HolidayThemeId | null = isAdmin ? null : previewId ?? remote;
  const showPreviewChrome = Boolean(previewId);
  const remainingMs = previewId ? Math.max(0, expiresAt - now) : 0;
  const yearStart = theme && theme === remote ? remoteYear : theme ? (years[theme] ?? null) : null;
  const yearEnd = theme && theme === remote ? remoteYearEnd : yearStart;
  const yearLabel = formatHolidayYear(yearStart, yearEnd);

  return (
    <HolidayThemeContext.Provider value={theme}>
      <HolidayYearContext.Provider value={yearLabel}>
        <HolidayPreviewContext.Provider value={{ active: showPreviewChrome, remainingMs, clear: clearPreview }}>
          {children}
        </HolidayPreviewContext.Provider>
      </HolidayYearContext.Provider>
    </HolidayThemeContext.Provider>
  );
}

export function useHolidayTheme(): HolidayThemeId | null {
  return useContext(HolidayThemeContext);
}

export function useHolidayYearLabel(): string {
  return useContext(HolidayYearContext);
}

export function useHolidayThemePreview(): { active: boolean; remainingMs: number; clear: () => void } {
  return useContext(HolidayPreviewContext);
}
