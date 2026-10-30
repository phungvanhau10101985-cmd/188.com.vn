'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  adminHolidayThemeAPI,
  type HolidayOccasionAdmin,
  type HolidayThemeAdminState,
} from '@/lib/admin-api';
import { getStorefrontOrigin } from '@/lib/admin-origin';
import { isHolidayThemeId } from '@/lib/holiday-themes';
import {
  clearHolidayAdminPreview,
  formatPreviewRemaining,
  readHolidayAdminPreview,
  startHolidayAdminPreview,
} from '@/lib/holiday-preview';

type Draft = {
  start_day: string;
  start_month: string;
  end_day: string;
  end_month: string;
  lead_days: string;
  after_days: string;
  sale_percent: string;
};

function draftFrom(row: HolidayOccasionAdmin): Draft {
  return {
    start_day: String(row.start_day),
    start_month: String(row.start_month),
    end_day: String(row.end_day),
    end_month: String(row.end_month),
    lead_days: String(row.lead_days),
    after_days: String(row.after_days),
    sale_percent: String(row.sale_percent),
  };
}

export default function AdminHolidayThemePage() {
  const [state, setState] = useState<HolidayThemeAdminState | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [previewCode, setPreviewCode] = useState<string | null>(null);
  const [previewLeft, setPreviewLeft] = useState(0);

  const apply = useCallback((data: HolidayThemeAdminState) => {
    setState(data);
    setDrafts(Object.fromEntries((data.occasions ?? []).map((row) => [row.code, draftFrom(row)])));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      apply(await adminHolidayThemeAPI.get());
    } catch (e) {
      setError((e as Error)?.message || 'Không tải được giao diện ngày lễ');
    } finally {
      setLoading(false);
    }
  }, [apply]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const sync = () => {
      const preview = readHolidayAdminPreview();
      setPreviewCode(preview?.code ?? null);
      setPreviewLeft(preview ? preview.expiresAt - Date.now() : 0);
    };
    sync();
    const timer = window.setInterval(sync, 1000);
    window.addEventListener('storage', sync);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('storage', sync);
    };
  }, []);

  const togglePreview = (code: string, name: string) => {
    if (!isHolidayThemeId(code)) return;
    if (previewCode === code) {
      clearHolidayAdminPreview();
      setPreviewCode(null);
      setPreviewLeft(0);
      setNotice(`Đã tắt xem trước ${name}.`);
      return;
    }
    const started = startHolidayAdminPreview(code);
    if (!started) {
      setNotice('Cần đăng nhập quản trị thì bản xem trước mới hiện.');
      return;
    }
    setPreviewCode(code);
    setPreviewLeft(started.expiresAt - Date.now());
    const opened = window.open(`${getStorefrontOrigin()}/`, '_blank', 'noopener');
    setNotice(
      opened
        ? `${name} đang hiện trên cửa hàng trong 10 phút. Chỉ trình duyệt đang đăng nhập admin thấy.`
        : `Đã bật ${name} trong 10 phút. Mở trang cửa hàng để xem. Khách không thấy bản này.`,
    );
  };

  const patchDraft = (code: string, patch: Partial<Draft>) => {
    setDrafts((prev) => ({ ...prev, [code]: { ...prev[code], ...patch } }));
  };

  const save = async (row: HolidayOccasionAdmin, extra?: { enabled: boolean }) => {
    const draft = drafts[row.code];
    if (!draft || savingId) return;
    const startDay = Number(draft.start_day);
    const startMonth = Number(draft.start_month);
    const endDay = Number(draft.end_day);
    const endMonth = Number(draft.end_month);
    const lead = Number(draft.lead_days);
    const after = Number(draft.after_days);
    const pct = Number(draft.sale_percent);
    if (![startDay, startMonth, endDay, endMonth, lead, after].every((n) => Number.isInteger(n))) {
      setError('Ngày, tháng và số ngày phải là số nguyên.');
      return;
    }
    if (!Number.isFinite(pct) || pct < 0 || pct > 50) {
      setError('% sale phải từ 0 đến 50.');
      return;
    }
    setSavingId(row.code);
    setNotice(null);
    setError(null);
    try {
      const saved = await adminHolidayThemeAPI.update({
        code: row.code,
        enabled: extra?.enabled ?? row.enabled,
        start_day: startDay,
        start_month: startMonth,
        end_day: endDay,
        end_month: endMonth,
        lead_days: lead,
        after_days: after,
        sale_percent: pct,
      });
      apply(saved);
      setNotice(`Đã lưu ${row.name}.`);
    } catch (e) {
      setError((e as Error)?.message || 'Không lưu được');
    } finally {
      setSavingId(null);
    }
  };

  return (
    <div className="mx-auto max-w-4xl p-4 sm:p-6">
      <h1 className="text-xl font-bold text-gray-900">Giao diện ngày lễ</h1>
      <p className="mt-1 text-sm text-gray-600">
        Mỗi dịp chỉ lưu ngày và tháng, dùng lại mọi năm. Âm lịch tự đổi sang ngày dương của năm đó.
        Nếu Tết bật quá dài và đè lên ngày Ông Táo, đúng ngày Ông Táo sẽ hiện giao diện Ông Táo, hết
        ngày đó thì quay lại Tết.
      </p>
      {state?.schedule_note ? (
        <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-950">{state.schedule_note}</p>
      ) : null}
      {error ? (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}{' '}
          <button type="button" onClick={load} className="font-medium underline">
            Thử lại
          </button>
        </div>
      ) : null}
      {notice ? (
        <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {notice}
        </div>
      ) : null}
      {loading && !state ? (
        <p className="mt-6 text-sm text-gray-500">Đang tải…</p>
      ) : (
        <ul className="mt-6 space-y-4">
          {(state?.occasions ?? []).map((row) => {
            const draft = drafts[row.code];
            const busy = savingId === row.code;
            const previewOn = previewCode === row.code;
            return (
              <li key={row.code} className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="text-base font-semibold text-gray-900">
                      {row.name}
                      {row.showing_today ? (
                        <span className="ml-2 text-xs font-medium text-[#9f1239]">Đang hiện hôm nay</span>
                      ) : null}
                    </p>
                    <p className="text-xs text-gray-500">
                      {row.calendar_label} · {row.summary}
                    </p>
                    <p className="mt-1 text-xs text-gray-600">
                      {row.solar_label}. Ô năm tự đổi theo năm của dịp lễ, không lưu số năm.
                    </p>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={previewOn}
                      aria-label={previewOn ? `Tắt xem trước ${row.name}` : `Xem trước ${row.name} trong 10 phút`}
                      onClick={() => togglePreview(row.code, row.name)}
                      className="mt-2 inline-flex items-center gap-2 text-sm text-[#9f1239]"
                    >
                      <span className={`relative h-6 w-11 rounded-full ${previewOn ? 'bg-[#b4233a]' : 'bg-gray-300'}`}>
                        <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow ${previewOn ? 'left-5' : 'left-0.5'}`} />
                      </span>
                      {previewOn ? `Đang xem trước · còn ${formatPreviewRemaining(previewLeft)}` : 'Xem trước 10 phút'}
                    </button>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={row.enabled}
                    aria-label={row.enabled ? `Tắt ${row.name}` : `Bật ${row.name}`}
                    disabled={busy}
                    onClick={() => save(row, { enabled: !row.enabled })}
                    className={`relative h-7 w-12 shrink-0 rounded-full ${row.enabled ? 'bg-[#b4233a]' : 'bg-gray-300'}`}
                  >
                    <span className={`absolute top-0.5 h-6 w-6 rounded-full bg-white shadow ${row.enabled ? 'left-5' : 'left-0.5'}`} />
                  </button>
                </div>
                {draft ? (
                  <div className="mt-4 grid gap-3 sm:grid-cols-3">
                    <label className="text-xs text-gray-600">
                      Ngày bắt đầu
                      <input className="mt-1 w-full rounded-lg border px-2 py-1.5 text-sm" value={draft.start_day} onChange={(e) => patchDraft(row.code, { start_day: e.target.value })} />
                    </label>
                    <label className="text-xs text-gray-600">
                      Tháng bắt đầu
                      <input className="mt-1 w-full rounded-lg border px-2 py-1.5 text-sm" value={draft.start_month} onChange={(e) => patchDraft(row.code, { start_month: e.target.value })} />
                    </label>
                    <label className="text-xs text-gray-600">
                      Năm
                      <input className="mt-1 w-full rounded-lg border bg-gray-50 px-2 py-1.5 text-sm text-gray-700" value={row.start_year ?? ''} readOnly aria-readonly="true" />
                    </label>
                    <label className="text-xs text-gray-600">
                      Ngày kết thúc
                      <input className="mt-1 w-full rounded-lg border px-2 py-1.5 text-sm" value={draft.end_day} onChange={(e) => patchDraft(row.code, { end_day: e.target.value })} />
                    </label>
                    <label className="text-xs text-gray-600">
                      Tháng kết thúc
                      <input className="mt-1 w-full rounded-lg border px-2 py-1.5 text-sm" value={draft.end_month} onChange={(e) => patchDraft(row.code, { end_month: e.target.value })} />
                    </label>
                    <label className="text-xs text-gray-600">
                      Năm
                      <input className="mt-1 w-full rounded-lg border bg-gray-50 px-2 py-1.5 text-sm text-gray-700" value={row.end_year ?? ''} readOnly aria-readonly="true" />
                    </label>
                    <label className="text-xs text-gray-600">
                      Số ngày bật trước
                      <input className="mt-1 w-full rounded-lg border px-2 py-1.5 text-sm" value={draft.lead_days} onChange={(e) => patchDraft(row.code, { lead_days: e.target.value })} />
                    </label>
                    <label className="text-xs text-gray-600">
                      Số ngày giữ sau lễ
                      <input className="mt-1 w-full rounded-lg border px-2 py-1.5 text-sm" value={draft.after_days} onChange={(e) => patchDraft(row.code, { after_days: e.target.value })} />
                    </label>
                    <label className="text-xs text-gray-600">
                      % sale
                      <input className="mt-1 w-full rounded-lg border px-2 py-1.5 text-sm" value={draft.sale_percent} onChange={(e) => patchDraft(row.code, { sale_percent: e.target.value })} />
                    </label>
                    <div className="flex items-end">
                      <button type="button" disabled={busy} onClick={() => save(row)} className="rounded-lg bg-[#9f1239] px-3 py-2 text-sm font-medium text-white disabled:opacity-60">
                        {busy ? 'Đang lưu…' : 'Lưu'}
                      </button>
                    </div>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
