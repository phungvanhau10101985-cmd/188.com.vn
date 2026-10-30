'use client';

import { HolidayMark } from '@/components/holiday/HolidayMarks';
import { useHolidayTheme, useHolidayThemePreview, useHolidayYearLabel } from '@/lib/holiday-theme-context';
import { formatPreviewRemaining } from '@/lib/holiday-preview';
import { HOLIDAY_LOOKS, type HolidayLook } from '@/lib/holiday-themes';

function useLook(): HolidayLook | null {
  const theme = useHolidayTheme();
  return theme ? HOLIDAY_LOOKS[theme] : null;
}

function withYear(title: string, year: string): string {
  return year ? `${title} ${year}` : title;
}

function SideMark({ look, kind, tone = 'light' }: { look: HolidayLook; kind: 'left' | 'right'; tone?: 'light' | 'dark' }) {
  return (
    <span className={kind === 'right' ? '-scale-x-100' : undefined}>
      <HolidayMark look={look} tone={tone} />
    </span>
  );
}

export function TetPreviewBar() {
  const preview = useHolidayThemePreview();
  const look = useLook();
  if (!preview.active || !look) return null;
  return (
    <div className="px-3 py-1.5 text-center text-[12px]" style={{ background: look.dark, color: look.goldSoft }}>
      {look.preview} Chỉ admin thấy, còn {formatPreviewRemaining(preview.remainingMs)}. Khách không thấy bản xem thử này.{' '}
      <button type="button" onClick={preview.clear} className="font-semibold text-white underline">
        Tắt xem trước
      </button>
    </div>
  );
}

export function TetArrivalRibbon() {
  const look = useLook();
  const year = useHolidayYearLabel();
  if (!look) return null;
  return (
    <div className="relative border-b" role="status" style={{ borderColor: look.gold, background: look.paper, color: look.ink }}>
      <div className="mx-auto flex max-w-7xl items-center justify-center gap-2 px-3 py-1.5 sm:gap-3 sm:py-2">
        <SideMark look={look} kind="left" />
        <p className="min-w-0 text-center text-[13px] leading-snug sm:text-sm">
          <span className="font-semibold tracking-wide">{withYear(look.ribbonTitle, year)}</span>
          <span className="mx-1.5" style={{ color: look.gold }} aria-hidden>
            ·
          </span>
          <span>{look.ribbonBody}</span>
        </p>
        <SideMark look={look} kind="right" />
      </div>
    </div>
  );
}

export function TetHomeWelcome() {
  const look = useLook();
  const year = useHolidayYearLabel();
  if (!look) return null;
  return (
    <section
      aria-label={withYear(look.welcomeTitle, year)}
      className="relative mb-5 overflow-hidden rounded-2xl border px-4 py-5 text-white sm:px-8 sm:py-6"
      style={{ borderColor: look.gold, background: `linear-gradient(135deg, ${look.dark}, ${look.strong} 55%, ${look.deep})` }}
    >
      <div className="relative mx-auto max-w-xl px-10 text-center sm:px-16">
        <div className="mb-2 flex justify-center">
          <HolidayMark look={look} tone="dark" className="h-12 w-12" />
        </div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.22em]" style={{ color: look.goldSoft }}>
          {look.kicker}
        </p>
        <p className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">{withYear(look.welcomeTitle, year)}</p>
        <p className="mt-2 text-sm leading-relaxed text-white/90">{look.welcomeBody}</p>
      </div>
    </section>
  );
}

export function TetProductNote() {
  const look = useLook();
  const year = useHolidayYearLabel();
  if (!look) return null;
  return (
    <div className="mb-3 flex items-center gap-3 rounded-xl border px-3 py-2.5 shadow-sm" style={{ borderColor: look.gold, background: look.paper }}>
      <SideMark look={look} kind="left" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold" style={{ color: look.ink }}>{withYear(look.productTitle, year)}</p>
        <p className="text-xs leading-relaxed" style={{ color: look.ink }}>{look.productBody}</p>
      </div>
      <SideMark look={look} kind="right" />
    </div>
  );
}

export function TetCartNote() {
  const look = useLook();
  const year = useHolidayYearLabel();
  if (!look) return null;
  return (
    <div className="mb-3 flex items-center gap-3 rounded-xl border px-3 py-2.5 shadow-sm" style={{ borderColor: look.gold, background: look.paper }}>
      <SideMark look={look} kind="left" />
      <div className="min-w-0">
        <p className="text-sm font-semibold" style={{ color: look.ink }}>{withYear(look.cartTitle, year)}</p>
        <p className="text-xs leading-relaxed" style={{ color: look.ink }}>{look.cartBody}</p>
      </div>
      <SideMark look={look} kind="right" />
    </div>
  );
}

export function TetCheckoutBanner() {
  const look = useLook();
  const year = useHolidayYearLabel();
  if (!look) return null;
  return (
    <div className="flex items-center justify-center gap-2 px-3 py-2 text-center text-white" style={{ background: `linear-gradient(90deg, ${look.dark}, ${look.strong}, ${look.deep})` }}>
      <SideMark look={look} kind="left" tone="dark" />
      <p className="text-sm font-semibold tracking-wide">
        {withYear(look.checkoutTitle, year)}
        <span className="mt-0.5 block text-[11px] font-normal" style={{ color: look.goldSoft }}>
          {look.checkoutBody}
        </span>
      </p>
      <SideMark look={look} kind="right" tone="dark" />
    </div>
  );
}

export function TetThanksNote() {
  const look = useLook();
  const year = useHolidayYearLabel();
  if (!look) return null;
  return (
    <div className="mb-4 flex items-center justify-center gap-2 rounded-xl border px-3 py-2" style={{ borderColor: look.gold, background: look.paper, color: look.ink }}>
      <SideMark look={look} kind="left" />
      <p className="text-sm font-semibold">{withYear(look.thanks, year)}</p>
      <SideMark look={look} kind="right" />
    </div>
  );
}
