'use client';

import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import {
  adminAdSpendAPI,
  type AdSpendPlatformReport,
  type AdSpendReport,
  type AdSpendSettingsView,
} from '@/lib/admin-api';
import { AdSpendProfitSection } from './profit-section';

type RangeKey = '7' | '30' | 'month' | 'prev';

function isoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function rangeFor(key: RangeKey): { from: string; to: string } {
  const today = new Date();
  const to = isoDate(today);
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

function PlatformCard({
  title,
  report,
}: {
  title: string;
  report: AdSpendPlatformReport;
}) {
  let body = 'Chưa cấu hình';
  if (report.configured && report.ok) body = formatMoney(report.spend, report.currency);
  if (report.configured && !report.ok) body = 'Không đọc được';
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-sm text-slate-500">{title}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-900">{body}</p>
      {report.configured && report.ok ? (
        <p className="mt-1 text-xs text-slate-500">
          {formatCount(report.clicks)} lượt nhấn · {formatCount(report.impressions)} lượt hiển thị
          {report.currency ? ` · ${report.currency}` : ''}
        </p>
      ) : null}
    </div>
  );
}

export default function AdminAdSpendPage() {
  const initial = rangeFor('30');
  const [settings, setSettings] = useState<AdSpendSettingsView | null>(null);
  const [report, setReport] = useState<AdSpendReport | null>(null);
  const [dateFrom, setDateFrom] = useState(initial.from);
  const [dateTo, setDateTo] = useState(initial.to);
  const [loadingSettings, setLoadingSettings] = useState(true);
  const [loadingReport, setLoadingReport] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [profitRefreshKey, setProfitRefreshKey] = useState(0);

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
    setLoadingReport(true);
    setError(null);
    try {
      const data = await adminAdSpendAPI.getReport(from, to);
      setReport(data);
    } catch (err) {
      setError((err as Error)?.message || 'Không tải được chi phí quảng cáo.');
    } finally {
      setLoadingReport(false);
    }
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
    void loadReport(dateFrom, dateTo);
    // Chỉ tải lần đầu khi đã có khóa. Đổi ngày do nút «Xem chi phí».
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings?.google_configured, settings?.facebook_configured]);

  const dailyRows = useMemo(() => {
    if (!report) return [];
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
  }, [report]);

  const onPreset = (key: RangeKey) => {
    const next = rangeFor(key);
    setDateFrom(next.from);
    setDateTo(next.to);
    setProfitRefreshKey((value) => value + 1);
    void loadReport(next.from, next.to);
  };

  const onSubmitRange = (e: FormEvent) => {
    e.preventDefault();
    setProfitRefreshKey((value) => value + 1);
    void loadReport(dateFrom, dateTo);
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
        await loadReport(dateFrom, dateTo);
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

  return (
    <div className="mx-auto max-w-6xl p-4 sm:p-6">
      <h1 className="text-xl font-bold text-slate-900">Chi phí quảng cáo</h1>
      <p className="mt-1 max-w-3xl text-sm text-slate-600">
        Đọc số tiền đã chi trên Google Ads và Facebook Ads, rồi đối chiếu lợi nhuận với đơn đã cọc.
      </p>

      {error ? (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}{' '}
          <button type="button" className="font-medium underline" onClick={() => void loadReport(dateFrom, dateTo)}>
            Thử lại
          </button>
        </div>
      ) : null}
      {toast ? (
        <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {toast}
        </div>
      ) : null}

      <form onSubmit={onSubmitRange} className="mt-5 flex flex-wrap items-end gap-3">
        <div className="flex flex-wrap gap-2">
          {(
            [
              ['7', '7 ngày'],
              ['30', '30 ngày'],
              ['month', 'Tháng này'],
              ['prev', 'Tháng trước'],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => onPreset(key)}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
            >
              {label}
            </button>
          ))}
        </div>
        <label className="text-sm text-slate-700">
          Từ
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="mt-1 block rounded-lg border border-slate-300 px-3 py-2"
          />
        </label>
        <label className="text-sm text-slate-700">
          Đến
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="mt-1 block rounded-lg border border-slate-300 px-3 py-2"
          />
        </label>
        <button
          type="submit"
          disabled={loadingReport || loadingSettings}
          className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-60"
        >
          {loadingReport ? 'Đang đọc…' : 'Xem chi phí'}
        </button>
      </form>

      {loadingSettings ? <p className="mt-6 text-sm text-slate-500">Đang tải cấu hình…</p> : null}

      {report ? (
        <div className="mt-6 space-y-6">
          <div className="grid gap-3 sm:grid-cols-3">
            <PlatformCard title="Google Ads" report={report.google} />
            <PlatformCard title="Facebook Ads" report={report.facebook} />
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <p className="text-sm text-slate-500">Tổng</p>
              <p className="mt-1 text-2xl font-semibold text-slate-900">
                {report.total_status === 'ok' && report.total_spend != null
                  ? formatMoney(report.total_spend, report.total_currency)
                  : report.total_status === 'mixed_currency'
                    ? 'Khác tiền tệ'
                    : '—'}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                {report.date_from} → {report.date_to}
                {report.total_status === 'mixed_currency'
                  ? ' · Google và Facebook không cùng đơn vị tiền, xem từng cột.'
                  : ''}
              </p>
            </div>
          </div>

          {report.google.partial || report.facebook.partial ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              Kỳ này có nhiều dòng hơn mức đã tải. Rút ngắn khoảng ngày để xem đủ chi phí.
            </div>
          ) : null}
          {report.google.configured && !report.google.ok && report.google.error ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              Google Ads: {report.google.error}
            </div>
          ) : null}
          {report.facebook.configured && !report.facebook.ok && report.facebook.error ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              Facebook Ads: {report.facebook.error}
            </div>
          ) : null}

          <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <h2 className="border-b border-slate-100 px-4 py-3 text-sm font-semibold text-slate-800">Theo ngày</h2>
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
                    </tr>
                  </thead>
                  <tbody>
                    {dailyRows.map((row) => (
                      <tr key={row.date} className="border-t border-slate-100">
                        <td className="px-4 py-2 text-slate-800">{row.date}</td>
                        <td className="px-4 py-2">
                          {row.google != null ? formatMoney(row.google, report.google.currency) : '—'}
                        </td>
                        <td className="px-4 py-2">
                          {row.facebook != null ? formatMoney(row.facebook, report.facebook.currency) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <div className="grid gap-4 lg:grid-cols-2">
            <CampaignTable title="Chiến dịch Google" report={report.google} />
            <CampaignTable title="Chiến dịch Facebook" report={report.facebook} />
          </div>
        </div>
      ) : null}

      <AdSpendProfitSection
        dateFrom={dateFrom}
        dateTo={dateTo}
        refreshKey={profitRefreshKey}
        adSpend={
          report && report.total_status === 'ok' && (report.total_currency || '').toUpperCase() === 'VND'
            ? report.total_spend
            : null
        }
        adSpendState={
          loadingReport
            ? 'loading'
            : report && report.total_status === 'ok' && (report.total_currency || '').toUpperCase() === 'VND'
              ? 'ready'
              : 'unavailable'
        }
      />

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
