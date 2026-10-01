'use client';

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  adminAdSpendAPI,
  type AdSpendDay,
  type AdSpendPlatformReport,
  type AdSpendReport,
  type AdSpendSettingsView,
} from '@/lib/admin-api';
import { AdSpendProfitSection, type AdSpendProfitSummary } from './profit-section';

type RangeKey = 'today' | 'yesterday' | 'week' | 'prevWeek' | '7' | '30' | 'month' | 'prev';

const PRESETS: { key: RangeKey; label: string }[] = [
  { key: 'today', label: 'Hôm nay' },
  { key: 'yesterday', label: 'Hôm qua' },
  { key: 'week', label: 'Tuần này' },
  { key: 'prevWeek', label: 'Tuần trước' },
  { key: '7', label: '7 ngày' },
  { key: '30', label: '30 ngày' },
  { key: 'month', label: 'Tháng này' },
  { key: 'prev', label: 'Tháng trước' },
];

const WEEKDAYS = ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7'];

function isoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function startOfWeek(d: Date): Date {
  const copy = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const weekday = copy.getDay();
  const diff = weekday === 0 ? 6 : weekday - 1;
  copy.setDate(copy.getDate() - diff);
  return copy;
}

function rangeFor(key: RangeKey): { from: string; to: string } {
  const today = new Date();
  const to = isoDate(today);
  if (key === 'today') return { from: to, to };
  if (key === 'yesterday') {
    const day = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1);
    const yesterday = isoDate(day);
    return { from: yesterday, to: yesterday };
  }
  if (key === 'week') return { from: isoDate(startOfWeek(today)), to };
  if (key === 'prevWeek') {
    const start = startOfWeek(today);
    start.setDate(start.getDate() - 7);
    const end = new Date(start.getFullYear(), start.getMonth(), start.getDate() + 6);
    return { from: isoDate(start), to: isoDate(end) };
  }
  if (key === '7') {
    const start = new Date(today);
    start.setDate(start.getDate() - 6);
    return { from: isoDate(start), to };
  }
  if (key === '30') {
    const start = new Date(today);
    start.setDate(start.getDate() - 29);
    return { from: isoDate(start), to };
  }
  if (key === 'prev') {
    const start = new Date(today.getFullYear(), today.getMonth() - 1, 1);
    const end = new Date(today.getFullYear(), today.getMonth(), 0);
    return { from: isoDate(start), to: isoDate(end) };
  }
  return { from: isoDate(new Date(today.getFullYear(), today.getMonth(), 1)), to };
}

function matchPreset(from: string, to: string): RangeKey | null {
  for (const preset of PRESETS) {
    const range = rangeFor(preset.key);
    if (range.from === from && range.to === to) return preset.key;
  }
  return null;
}

function formatViDate(iso: string): string {
  const [year, month, day] = iso.split('-');
  if (!year || !month || !day) return iso;
  return `${day}/${month}/${year}`;
}

function eachDate(from: string, to: string): string[] {
  if (!from || !to || from > to) return [];
  const out: string[] = [];
  const cursor = new Date(`${from}T00:00:00`);
  const end = new Date(`${to}T00:00:00`);
  while (cursor <= end && out.length < 62) {
    out.push(isoDate(cursor));
    cursor.setDate(cursor.getDate() + 1);
  }
  return out;
}

function dayParts(iso: string): { week: string; day: string; short: string } {
  const date = new Date(`${iso}T00:00:00`);
  return {
    week: WEEKDAYS[date.getDay()] || '',
    day: String(date.getDate()),
    short: `${date.getDate()}/${date.getMonth() + 1}`,
  };
}

function sumDaily(days: AdSpendDay[], from: string, to: string) {
  let spend = 0;
  let clicks = 0;
  let impressions = 0;
  for (const row of days) {
    if (row.date >= from && row.date <= to) {
      spend += row.spend;
      clicks += row.clicks;
      impressions += row.impressions;
    }
  }
  return { spend, clicks, impressions };
}

function formatMoney(amount: number, currency: string | null): string {
  const code = (currency || '').toUpperCase();
  if (code === 'VND') {
    return new Intl.NumberFormat('vi-VN', {
      style: 'currency',
      currency: 'VND',
      maximumFractionDigits: 0,
    }).format(Math.round(amount));
  }
  if (code) {
    try {
      return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: code }).format(amount);
    } catch {
      return `${amount.toLocaleString('vi-VN')} ${code}`;
    }
  }
  return amount.toLocaleString('vi-VN');
}

function formatCount(n: number): string {
  return new Intl.NumberFormat('vi-VN').format(n || 0);
}

function sourceLabel(source: string): string {
  if (source === 'database') return 'Đang dùng khóa đã lưu trên quản trị.';
  if (source === 'environment') return 'Đang dùng biến môi trường trên server.';
  if (source === 'mixed') return 'Một phần khóa lấy từ quản trị, phần còn lại từ biến môi trường.';
  return 'Chưa đủ khóa để đọc chi phí.';
}

type Slice = {
  amount: number | null;
  clicks: number;
  impressions: number;
  currency: string | null;
  configured: boolean;
  ok: boolean;
};

function platformSlice(report: AdSpendPlatformReport, from: string, to: string, full: boolean): Slice {
  if (!report.configured || !report.ok) {
    return {
      amount: null,
      clicks: 0,
      impressions: 0,
      currency: report.currency,
      configured: report.configured,
      ok: report.ok,
    };
  }
  if (full) {
    return {
      amount: report.spend,
      clicks: report.clicks,
      impressions: report.impressions,
      currency: report.currency,
      configured: true,
      ok: true,
    };
  }
  const summed = sumDaily(report.daily, from, to);
  return {
    amount: summed.spend,
    clicks: summed.clicks,
    impressions: summed.impressions,
    currency: report.currency,
    configured: true,
    ok: true,
  };
}

function sameSummary(prev: AdSpendProfitSummary, next: AdSpendProfitSummary): boolean {
  return (
    prev.dateFrom === next.dateFrom &&
    prev.dateTo === next.dateTo &&
    prev.loading === next.loading &&
    prev.orderCount === next.orderCount &&
    prev.revenue === next.revenue &&
    prev.revenueCny === next.revenueCny &&
    prev.cost === next.cost &&
    prev.missing === next.missing &&
    prev.gross === next.gross &&
    prev.profit === next.profit
  );
}

function platformText(slice: Slice | null | undefined, loading: boolean): string {
  if (loading) return 'Đang đọc…';
  if (!slice) return '—';
  if (!slice.configured) return 'Chưa cấu hình';
  if (!slice.ok || slice.amount == null) return 'Không đọc được';
  return formatMoney(slice.amount, slice.currency);
}

function platformHint(slice: Slice | null | undefined): string | undefined {
  if (!slice?.ok || slice.amount == null) return undefined;
  return `${formatCount(slice.clicks)} lượt nhấn · ${formatCount(slice.impressions)} lượt hiển thị`;
}

function dayTotal(google: number | undefined, facebook: number | undefined, source: AdSpendReport): string {
  if (google == null && facebook == null) return '—';
  const googleCurrency = source.google.currency;
  const facebookCurrency = source.facebook.currency;
  if (google != null && facebook != null && googleCurrency && facebookCurrency && googleCurrency !== facebookCurrency) {
    return '—';
  }
  return formatMoney((google ?? 0) + (facebook ?? 0), google != null ? googleCurrency : facebookCurrency);
}

export default function AdminAdSpendPage() {
  const initial = rangeFor('30');
  const [settings, setSettings] = useState<AdSpendSettingsView | null>(null);
  const [report, setReport] = useState<AdSpendReport | null>(null);
  const [periodFrom, setPeriodFrom] = useState(initial.from);
  const [periodTo, setPeriodTo] = useState(initial.to);
  const [focusFrom, setFocusFrom] = useState(initial.from);
  const [focusTo, setFocusTo] = useState(initial.to);
  const [draftFrom, setDraftFrom] = useState(initial.from);
  const [draftTo, setDraftTo] = useState(initial.to);
  const [loadingSettings, setLoadingSettings] = useState(true);
  const [loadingReport, setLoadingReport] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [profitRefreshKey, setProfitRefreshKey] = useState(0);
  const [chosenPreset, setChosenPreset] = useState<RangeKey | null>('30');
  const [profitSummary, setProfitSummary] = useState<AdSpendProfitSummary | null>(null);
  const reportSeq = useRef(0);
  const periodRef = useRef({ from: initial.from, to: initial.to });
  const selectedChipRef = useRef<HTMLButtonElement | null>(null);
  periodRef.current = { from: periodFrom, to: periodTo };

  const [googleCustomerId, setGoogleCustomerId] = useState('');
  const [googleLoginCustomerId, setGoogleLoginCustomerId] = useState('');
  const [googleDeveloperToken, setGoogleDeveloperToken] = useState('');
  const [googleClientId, setGoogleClientId] = useState('');
  const [googleClientSecret, setGoogleClientSecret] = useState('');
  const [googleRefreshToken, setGoogleRefreshToken] = useState('');
  const [clearGoogle, setClearGoogle] = useState(false);
  const [metaAccountId, setMetaAccountId] = useState('');
  const [metaToken, setMetaToken] = useState('');
  const [clearMeta, setClearMeta] = useState(false);

  const applySettingsForm = (data: AdSpendSettingsView) => {
    setGoogleCustomerId(data.google_customer_id || '');
    setGoogleLoginCustomerId(data.google_login_customer_id || '');
    setMetaAccountId(data.meta_ad_account_id || '');
    setGoogleDeveloperToken('');
    setGoogleClientId('');
    setGoogleClientSecret('');
    setGoogleRefreshToken('');
    setMetaToken('');
    setClearGoogle(false);
    setClearMeta(false);
  };

  const loadReport = useCallback(async (from: string, to: string) => {
    const seq = ++reportSeq.current;
    setLoadingReport(true);
    setError(null);
    try {
      const data = await adminAdSpendAPI.getReport(from, to);
      if (seq !== reportSeq.current) return;
      setReport(data);
    } catch (err) {
      if (seq !== reportSeq.current) return;
      setError((err as Error)?.message || 'Không tải được chi phí quảng cáo.');
    } finally {
      if (seq === reportSeq.current) setLoadingReport(false);
    }
  }, []);

  const onProfitSummary = useCallback((next: AdSpendProfitSummary) => {
    setProfitSummary((prev) => (prev && sameSummary(prev, next) ? prev : next));
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoadingSettings(true);
      try {
        const data = await adminAdSpendAPI.getSettings();
        if (cancelled) return;
        setSettings(data);
        applySettingsForm(data);
        if (!data.google_configured && !data.facebook_configured) setShowSettings(true);
      } catch (err) {
        if (!cancelled) setError((err as Error)?.message || 'Không tải được cấu hình.');
      } finally {
        if (!cancelled) setLoadingSettings(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!settings) return;
    if (!settings.google_configured && !settings.facebook_configured) return;
    void loadReport(periodRef.current.from, periodRef.current.to);
    // Chỉ tải lần đầu khi đã có khóa. Đổi kỳ do nút chọn ngày.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings?.google_configured, settings?.facebook_configured]);

  const dailyRows = useMemo(() => {
    if (!report || report.date_from !== periodFrom || report.date_to !== periodTo) return [];
    const map = new Map<string, { google?: number; facebook?: number }>();
    for (const row of report.google.daily) {
      map.set(row.date, { ...(map.get(row.date) || {}), google: row.spend });
    }
    for (const row of report.facebook.daily) {
      map.set(row.date, { ...(map.get(row.date) || {}), facebook: row.spend });
    }
    return [...map.entries()]
      .sort((a, b) => (a[0] < b[0] ? 1 : -1))
      .map(([date, values]) => ({ date, ...values }));
  }, [report, periodFrom, periodTo]);

  const applyPeriod = (from: string, to: string, preset: RangeKey | null) => {
    setChosenPreset(preset);
    setDraftFrom(from);
    setDraftTo(to);
    setPeriodFrom(from);
    setPeriodTo(to);
    setFocusFrom(from);
    setFocusTo(to);
    setProfitRefreshKey((value) => value + 1);
    void loadReport(from, to);
  };

  const onPreset = (key: RangeKey) => {
    const next = rangeFor(key);
    applyPeriod(next.from, next.to, key);
  };

  const onSubmitRange = (e: FormEvent) => {
    e.preventDefault();
    if (!draftFrom || !draftTo || draftFrom > draftTo) {
      setError('Chọn ngày bắt đầu trước hoặc bằng ngày kết thúc.');
      return;
    }
    applyPeriod(draftFrom, draftTo, matchPreset(draftFrom, draftTo));
  };

  const showWholePeriod = () => {
    if (focusFrom === periodFrom && focusTo === periodTo) return;
    setFocusFrom(periodFrom);
    setFocusTo(periodTo);
    setProfitRefreshKey((value) => value + 1);
  };

  const focusDay = (iso: string) => {
    const already = focusFrom === iso && focusTo === iso;
    const nextFrom = already ? periodFrom : iso;
    const nextTo = already ? periodTo : iso;
    if (nextFrom === focusFrom && nextTo === focusTo) return;
    setFocusFrom(nextFrom);
    setFocusTo(nextTo);
    setProfitRefreshKey((value) => value + 1);
  };

  const onSave = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const saved = await adminAdSpendAPI.updateSettings({
        google_customer_id: googleCustomerId,
        google_login_customer_id: googleLoginCustomerId,
        meta_ad_account_id: metaAccountId,
        ...(googleDeveloperToken.trim() ? { google_developer_token: googleDeveloperToken.trim() } : {}),
        ...(googleClientId.trim() ? { google_client_id: googleClientId.trim() } : {}),
        ...(googleClientSecret.trim() ? { google_client_secret: googleClientSecret.trim() } : {}),
        ...(googleRefreshToken.trim() ? { google_refresh_token: googleRefreshToken.trim() } : {}),
        ...(metaToken.trim() ? { meta_access_token: metaToken.trim() } : {}),
        ...(clearGoogle ? { clear_google_secrets: true } : {}),
        ...(clearMeta ? { clear_meta_secrets: true } : {}),
      });
      setSettings(saved);
      applySettingsForm(saved);
      setToast('Đã lưu khóa đọc chi phí quảng cáo.');
      setTimeout(() => setToast(null), 4000);
      if (saved.google_configured || saved.facebook_configured) {
        await loadReport(periodFrom, periodTo);
      } else {
        setReport(null);
      }
    } catch (err) {
      setError((err as Error)?.message || 'Không lưu được cấu hình.');
    } finally {
      setSaving(false);
    }
  };

  const secretHint = (set: boolean) =>
    set ? 'Đã lưu — để trống nếu không đổi' : 'Chưa có';

  const activePreset = chosenPreset;
  const dayFocused = focusFrom === focusTo && (focusFrom !== periodFrom || focusTo !== periodTo);
  const highlightDate = focusFrom === focusTo ? focusFrom : null;
  const periodDays = useMemo(() => eachDate(periodFrom, periodTo), [periodFrom, periodTo]);
  const spanMonths = periodFrom.slice(0, 7) !== periodTo.slice(0, 7);
  const periodReport = report && report.date_from === periodFrom && report.date_to === periodTo ? report : null;
  const adsConfigured = Boolean(settings?.google_configured || settings?.facebook_configured);
  const spendLoading = loadingReport || (adsConfigured && !periodReport && !error);
  const focusSpend = useMemo(() => {
    if (!periodReport) return null;
    const full = focusFrom === periodReport.date_from && focusTo === periodReport.date_to;
    const google = platformSlice(periodReport.google, focusFrom, focusTo, full);
    const facebook = platformSlice(periodReport.facebook, focusFrom, focusTo, full);
    let total: number | null = null;
    let currency: string | null = null;
    let status: AdSpendReport['total_status'] = 'incomplete';
    if (full) {
      total = periodReport.total_status === 'ok' ? periodReport.total_spend : null;
      currency = periodReport.total_currency;
      status = periodReport.total_status;
    } else if (google.ok && facebook.ok && google.amount != null && facebook.amount != null) {
      if (google.currency && facebook.currency && google.currency !== facebook.currency) {
        status = 'mixed_currency';
      } else {
        currency = google.currency || facebook.currency;
        total = google.amount + facebook.amount;
        status = 'ok';
      }
    } else if (google.ok && google.amount != null && !periodReport.facebook.configured) {
      total = google.amount;
      currency = google.currency;
      status = 'ok';
    } else if (facebook.ok && facebook.amount != null && !periodReport.google.configured) {
      total = facebook.amount;
      currency = facebook.currency;
      status = 'ok';
    }
    return { google, facebook, total, currency, status };
  }, [periodReport, focusFrom, focusTo]);
  const profitForFocus =
    profitSummary && profitSummary.dateFrom === focusFrom && profitSummary.dateTo === focusTo ? profitSummary : null;
  const profitLoading = !profitForFocus || profitForFocus.loading;
  const focusTotalVnd =
    focusSpend && focusSpend.status === 'ok' && (focusSpend.currency || '').toUpperCase() === 'VND' ? focusSpend.total : null;
  const adSpendState: 'loading' | 'ready' | 'unavailable' =
    !settings || loadingSettings ? 'loading' : !adsConfigured ? 'unavailable' : spendLoading ? 'loading' : focusTotalVnd != null ? 'ready' : 'unavailable';
  const presetLabel = PRESETS.find((item) => item.key === activePreset)?.label ?? null;
  const focusCaption = focusFrom === focusTo ? formatViDate(focusFrom) : `${formatViDate(focusFrom)} → ${formatViDate(focusTo)}`;
  const viewingLabel = dayFocused ? focusCaption : presetLabel ? `${presetLabel} · ${focusCaption}` : focusCaption;
  const totalText = spendLoading
    ? 'Đang đọc…'
    : !focusSpend
      ? '—'
      : focusSpend.status === 'mixed_currency'
        ? 'Khác tiền tệ'
        : focusSpend.status === 'ok' && focusSpend.total != null
          ? formatMoney(focusSpend.total, focusSpend.currency)
          : '—';
  const profitText = profitLoading
    ? 'Đang tính…'
    : profitForFocus?.profit == null
      ? '—'
      : formatMoney(profitForFocus.profit, 'VND');
  const profitNegative = !profitLoading && (profitForFocus?.profit ?? 0) < 0 && profitForFocus?.profit != null;
  const profitHint = profitLoading
    ? 'Đơn đã cọc trong kỳ đang chọn'
    : profitForFocus?.missing
      ? `${profitForFocus.missing} đơn còn thiếu giá nhập`
      : profitForFocus?.gross != null
        ? `${profitForFocus.orderCount} đơn · lãi trước quảng cáo ${formatMoney(profitForFocus.gross, 'VND')}`
        : `${profitForFocus?.orderCount ?? 0} đơn`;

  useEffect(() => {
    selectedChipRef.current?.scrollIntoView({ inline: 'center', block: 'nearest' });
  }, [focusFrom, focusTo, periodFrom, periodTo]);

  const presetClass = (key: RangeKey) => {
    const selected = activePreset === key;
    if (selected && !dayFocused) return 'border-[#ea580c] bg-[#ea580c] font-semibold text-white shadow-sm';
    if (selected) return 'border-[#ea580c] bg-orange-50 font-semibold text-[#ea580c]';
    return 'border-slate-200 bg-white text-slate-700 hover:border-orange-200 hover:bg-orange-50 hover:text-[#ea580c]';
  };
  const chipClass = (active: boolean) =>
    active
      ? 'border-[#ea580c] bg-[#ea580c] font-bold text-white shadow-sm'
      : 'border-slate-200 bg-white text-slate-700 hover:border-orange-200 hover:bg-orange-50 hover:text-[#ea580c]';

  return (
    <div className="mx-auto max-w-6xl p-4 sm:p-6">
      <h1 className="text-xl font-bold text-slate-900">Chi phí quảng cáo</h1>
      <p className="mt-1 max-w-3xl text-sm text-slate-600">
        Chọn hôm nay, tuần hoặc tháng. Chi phí quảng cáo và lợi nhuận của kỳ đó hiện ngay bên dưới, màu cam. Bảng chi
        tiết nằm phía dưới.
      </p>

      {error ? (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}{' '}
          <button type="button" className="font-medium underline" onClick={() => void loadReport(periodFrom, periodTo)}>
            Thử lại
          </button>
        </div>
      ) : null}
      {toast ? (
        <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {toast}
        </div>
      ) : null}

      <form onSubmit={onSubmitRange} className="mt-4 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm sm:p-4">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Chọn nhanh khoảng ngày">
          {PRESETS.map((preset) => (
            <button
              key={preset.key}
              type="button"
              aria-pressed={activePreset === preset.key}
              onClick={() => onPreset(preset.key)}
              className={`rounded-full border px-3 py-1.5 text-sm transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ea580c] ${presetClass(preset.key)}`}
            >
              {preset.label}
            </button>
          ))}
        </div>
        {periodDays.length > 1 ? (
          <div className="mt-3">
            <p className="text-xs font-medium text-slate-500">Từng ngày — bấm để xem số của ngày đó</p>
            <div className="mt-2 flex gap-1.5 overflow-x-auto pb-1">
              <button
                type="button"
                ref={dayFocused ? undefined : selectedChipRef}
                aria-pressed={!dayFocused}
                onClick={showWholePeriod}
                className={`shrink-0 rounded-xl border px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ea580c] ${chipClass(!dayFocused)}`}
              >
                Cả kỳ
              </button>
              {periodDays.map((iso) => {
                const parts = dayParts(iso);
                const active = focusFrom === iso && focusTo === iso;
                return (
                  <button
                    key={iso}
                    type="button"
                    ref={active ? selectedChipRef : undefined}
                    aria-pressed={active}
                    onClick={() => focusDay(iso)}
                    className={`flex min-w-[3.1rem] shrink-0 flex-col items-center rounded-xl border px-2 py-1.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ea580c] ${chipClass(active)}`}
                  >
                    <span className={`text-[10px] font-medium ${active ? 'text-orange-100' : 'text-slate-400'}`}>
                      {parts.week}
                    </span>
                    <span className="text-sm leading-tight">{spanMonths ? parts.short : parts.day}</span>
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}
        <div className="mt-3 flex flex-wrap items-end gap-3 border-t border-slate-100 pt-3">
          <label className="text-sm text-slate-700">
            Từ
            <input
              type="date"
              value={draftFrom}
              onChange={(e) => setDraftFrom(e.target.value)}
              className="mt-1 block rounded-lg border border-slate-300 px-3 py-2 focus:border-[#ea580c] focus:outline-none focus:ring-2 focus:ring-[#ea580c]/30"
            />
          </label>
          <label className="text-sm text-slate-700">
            Đến
            <input
              type="date"
              value={draftTo}
              onChange={(e) => setDraftTo(e.target.value)}
              className="mt-1 block rounded-lg border border-slate-300 px-3 py-2 focus:border-[#ea580c] focus:outline-none focus:ring-2 focus:ring-[#ea580c]/30"
            />
          </label>
          <button
            type="submit"
            disabled={loadingReport || loadingSettings}
            className="rounded-lg bg-[#ea580c] px-4 py-2 text-sm font-semibold text-white hover:bg-[#c2410c] disabled:opacity-60"
          >
            {loadingReport ? 'Đang đọc…' : 'Xem kỳ này'}
          </button>
        </div>
      </form>

      {loadingSettings ? <p className="mt-4 text-sm text-slate-500">Đang tải cấu hình…</p> : null}

      <section className="mt-4 overflow-hidden rounded-2xl border border-orange-200 bg-white shadow-sm" aria-label="Tổng quan kỳ đang chọn">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-orange-100 bg-orange-50 px-4 py-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-[#ea580c]">Đang xem</p>
            <p className="text-base font-bold text-slate-900">{viewingLabel}</p>
          </div>
          {dayFocused ? (
            <button
              type="button"
              onClick={showWholePeriod}
              className="rounded-lg border border-[#ea580c] bg-white px-3 py-1.5 text-sm font-semibold text-[#ea580c] hover:bg-orange-50"
            >
              Xem cả kỳ
            </button>
          ) : null}
        </div>
        <div className="grid gap-px bg-orange-100 sm:grid-cols-2">
          <HeroStat
            label="Chi phí quảng cáo"
            value={totalText}
            hint={
              focusSpend?.status === 'mixed_currency'
                ? 'Google và Facebook không cùng đơn vị tiền'
                : 'Google + Facebook'
            }
          />
          <HeroStat label="Lợi nhuận" value={profitText} hint={profitHint} negative={profitNegative} />
        </div>
        <div className="grid grid-cols-2 gap-px border-t border-orange-100 bg-orange-100 lg:grid-cols-4">
          <MiniStat label="Google Ads" value={platformText(focusSpend?.google, spendLoading)} hint={platformHint(focusSpend?.google)} />
          <MiniStat
            label="Facebook Ads"
            value={platformText(focusSpend?.facebook, spendLoading)}
            hint={platformHint(focusSpend?.facebook)}
          />
          <MiniStat
            label="Doanh thu đã cọc"
            value={profitLoading ? 'Đang tính…' : formatMoney(profitForFocus?.revenue ?? 0, 'VND')}
            hint={profitLoading ? undefined : `${profitForFocus?.orderCount ?? 0} đơn`}
          />
          <MiniStat
            label="Giá vốn"
            value={
              profitLoading ? 'Đang tính…' : profitForFocus?.cost == null ? '—' : formatMoney(profitForFocus.cost, 'VND')
            }
            hint={profitForFocus?.missing ? 'Còn đơn thiếu giá nhập' : 'Giá hàng và ship'}
          />
        </div>
      </section>

      {periodReport ? (
        <div className="mt-4 space-y-3">

          {periodReport.google.partial || periodReport.facebook.partial ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              Kỳ này có nhiều dòng hơn mức đã tải. Rút ngắn khoảng ngày để xem đủ chi phí.
            </div>
          ) : null}
          {periodReport.google.configured && !periodReport.google.ok && periodReport.google.error ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              Google Ads: {periodReport.google.error}
            </div>
          ) : null}
          {periodReport.facebook.configured && !periodReport.facebook.ok && periodReport.facebook.error ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              Facebook Ads: {periodReport.facebook.error}
            </div>
          ) : null}

          <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-100 px-4 py-3">
              <h2 className="text-sm font-semibold text-slate-800">Chi tiết theo ngày</h2>
              <p className="mt-0.5 text-xs text-slate-500">
                Bấm một dòng để đưa chi phí và lợi nhuận của ngày đó lên trên. Dòng đang chọn màu cam.
              </p>
            </div>
            {dailyRows.length === 0 ? (
              <p className="px-4 py-6 text-sm text-slate-500">Không có chi phí trong khoảng này.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-slate-50 text-left text-slate-500">
                    <tr>
                      <th className="px-4 py-2 font-medium">Ngày</th>
                      <th className="px-4 py-2 font-medium">Google</th>
                      <th className="px-4 py-2 font-medium">Facebook</th>
                      <th className="px-4 py-2 font-medium">Tổng</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dailyRows.map((row) => {
                      const selected = highlightDate === row.date;
                      const moneyClass = selected ? 'font-bold text-[#ea580c]' : 'text-slate-800';
                      const parts = dayParts(row.date);
                      return (
                        <tr
                          key={row.date}
                          role="button"
                          tabIndex={0}
                          aria-pressed={selected}
                          onClick={() => focusDay(row.date)}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault();
                              focusDay(row.date);
                            }
                          }}
                          className={`cursor-pointer border-t border-slate-100 ${selected ? 'bg-orange-50' : 'hover:bg-orange-50/60'}`}
                        >
                          <td className={`px-4 py-2 whitespace-nowrap ${selected ? 'font-bold text-[#ea580c]' : 'text-slate-800'}`}>
                            {parts.week} {formatViDate(row.date)}
                          </td>
                          <td className={`px-4 py-2 whitespace-nowrap ${moneyClass}`}>
                            {row.google != null ? formatMoney(row.google, periodReport.google.currency) : '—'}
                          </td>
                          <td className={`px-4 py-2 whitespace-nowrap ${moneyClass}`}>
                            {row.facebook != null ? formatMoney(row.facebook, periodReport.facebook.currency) : '—'}
                          </td>
                          <td className={`px-4 py-2 whitespace-nowrap ${moneyClass}`}>
                            {dayTotal(row.google, row.facebook, periodReport)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {dayFocused ? (
            <p className="text-xs text-slate-500">
              Chiến dịch bên dưới là cả kỳ {formatViDate(periodFrom)} → {formatViDate(periodTo)}. Số màu cam phía trên là
              ngày {formatViDate(focusFrom)}.
            </p>
          ) : null}
          <div className="grid gap-4 lg:grid-cols-2">
            <CampaignTable title="Chiến dịch Google" report={periodReport.google} />
            <CampaignTable title="Chiến dịch Facebook" report={periodReport.facebook} />
          </div>
        </div>
      ) : spendLoading ? (
        <p className="mt-4 text-sm text-slate-500">Đang đọc chi tiết chi phí…</p>
      ) : null}

      <div className="mt-6">
        <AdSpendProfitSection
          dateFrom={focusFrom}
          dateTo={focusTo}
          refreshKey={profitRefreshKey}
          adSpend={focusTotalVnd}
          adSpendState={adSpendState}
          onSummaryChange={onProfitSummary}
        />
      </div>

      <section className="mt-8 rounded-xl border border-slate-200 bg-white shadow-sm">
        <button
          type="button"
          className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-semibold text-slate-800"
          aria-expanded={showSettings}
          onClick={() => setShowSettings((v) => !v)}
        >
          Khóa kết nối
          <span className="text-slate-400">{showSettings ? 'Thu gọn' : 'Mở'}</span>
        </button>
        {showSettings && settings ? (
          <form onSubmit={onSave} className="space-y-6 border-t border-slate-100 px-4 py-4">
            <div>
              <h3 className="text-sm font-semibold text-slate-900">Google Ads</h3>
              <p className="mt-1 text-xs text-slate-500">{sourceLabel(settings.google_credential_source)}</p>
              {settings.google_service_account_email ? (
                <p className="mt-2 text-xs text-emerald-700">
                  Đang đọc bằng tài khoản dịch vụ <code>{settings.google_service_account_email}</code>. API version{' '}
                  {settings.google_ads_api_version}. Khóa nằm trên máy chủ, không lưu trong form này.
                </p>
              ) : (
                <p className="mt-2 text-xs text-slate-500">
                  Cách đang dùng: file tài khoản dịch vụ trên máy chủ (biến môi trường), quyền đọc Google Ads. OAuth bên
                  dưới chỉ là phương án dự phòng. API version {settings.google_ads_api_version}.
                </p>
              )}
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <Field label="Customer ID" value={googleCustomerId} onChange={setGoogleCustomerId} />
                <Field
                  label="ID tài khoản quản lý (MCC, nếu có)"
                  value={googleLoginCustomerId}
                  onChange={setGoogleLoginCustomerId}
                />
                <Field
                  label="Developer token"
                  value={googleDeveloperToken}
                  onChange={setGoogleDeveloperToken}
                  secret
                  placeholder={secretHint(settings.google_developer_token_set)}
                />
                <Field
                  label="OAuth client ID"
                  value={googleClientId}
                  onChange={setGoogleClientId}
                  placeholder={secretHint(settings.google_client_id_set)}
                />
                <Field
                  label="OAuth client secret"
                  value={googleClientSecret}
                  onChange={setGoogleClientSecret}
                  secret
                  placeholder={secretHint(settings.google_client_secret_set)}
                />
                <Field
                  label="Refresh token"
                  value={googleRefreshToken}
                  onChange={setGoogleRefreshToken}
                  secret
                  placeholder={secretHint(settings.google_refresh_token_set)}
                />
              </div>
              <label className="mt-3 flex items-center gap-2 text-sm text-slate-700">
                <input type="checkbox" checked={clearGoogle} onChange={(e) => setClearGoogle(e.target.checked)} />
                Xóa khóa Google đã lưu trên quản trị
              </label>
            </div>

            <div>
              <h3 className="text-sm font-semibold text-slate-900">Facebook Ads</h3>
              <p className="mt-1 text-xs text-slate-500">{sourceLabel(settings.meta_credential_source)}</p>
              <p className="mt-2 text-xs text-slate-500">
                Token hệ thống trong Business Manager, quyền <code>ads_read</code>. ID tài khoản quảng cáo là dãy số
                (bỏ <code>act_</code> cũng được). Graph version hiện dùng {settings.meta_graph_api_version}.
              </p>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <Field label="Ad account ID" value={metaAccountId} onChange={setMetaAccountId} />
                <Field
                  label="Access token"
                  value={metaToken}
                  onChange={setMetaToken}
                  secret
                  placeholder={secretHint(settings.meta_access_token_set)}
                />
              </div>
              <label className="mt-3 flex items-center gap-2 text-sm text-slate-700">
                <input type="checkbox" checked={clearMeta} onChange={(e) => setClearMeta(e.target.checked)} />
                Xóa token Facebook đã lưu trên quản trị
              </label>
            </div>

            <button
              type="submit"
              disabled={saving}
              className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-60"
            >
              {saving ? 'Đang lưu…' : 'Lưu khóa'}
            </button>
          </form>
        ) : null}
      </section>
    </div>
  );
}

function HeroStat({
  label,
  value,
  hint,
  negative,
}: {
  label: string;
  value: string;
  hint: string;
  negative?: boolean;
}) {
  return (
    <div className="bg-white px-4 py-4">
      <p className="text-sm text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-bold tabular-nums sm:text-3xl ${negative ? 'text-red-600' : 'text-[#ea580c]'}`}>
        {value}
      </p>
      <p className="mt-1 text-xs text-slate-500">{hint}</p>
    </div>
  );
}

function MiniStat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="bg-white px-4 py-3">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 text-base font-bold tabular-nums text-[#ea580c]">{value}</p>
      {hint ? <p className="mt-0.5 text-[11px] text-slate-400">{hint}</p> : null}
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  secret,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  secret?: boolean;
  placeholder?: string;
}) {
  return (
    <label className="block text-sm text-slate-700">
      {label}
      <input
        type={secret ? 'password' : 'text'}
        autoComplete="new-password"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
      />
    </label>
  );
}

function CampaignTable({ title, report }: { title: string; report: AdSpendPlatformReport }) {
  return (
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <h2 className="border-b border-slate-100 px-4 py-3 text-sm font-semibold text-slate-800">{title}</h2>
      {!report.configured ? (
        <p className="px-4 py-6 text-sm text-slate-500">Chưa cấu hình.</p>
      ) : report.campaigns.length === 0 ? (
        <p className="px-4 py-6 text-sm text-slate-500">Không có chiến dịch phát sinh chi phí.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-left text-slate-500">
              <tr>
                <th className="px-4 py-2 font-medium">Chiến dịch</th>
                <th className="px-4 py-2 font-medium">Chi phí</th>
                <th className="px-4 py-2 font-medium">Nhấn</th>
              </tr>
            </thead>
            <tbody>
              {report.campaigns.map((row) => (
                <tr key={row.id} className="border-t border-slate-100">
                  <td className="px-4 py-2 text-slate-800">{row.name}</td>
                  <td className="px-4 py-2 whitespace-nowrap">{formatMoney(row.spend, report.currency)}</td>
                  <td className="px-4 py-2">{formatCount(row.clicks)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
