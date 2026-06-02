'use client';

import { useCallback, useEffect, useState } from 'react';
import { adminSaleCalendarAPI, type AdminSaleCalendarSettings } from '@/lib/admin-api';

const MONTH_NAMES = [
  'Tháng 1',
  'Tháng 2',
  'Tháng 3',
  'Tháng 4',
  'Tháng 5',
  'Tháng 6',
  'Tháng 7',
  'Tháng 8',
  'Tháng 9',
  'Tháng 10',
  'Tháng 11',
  'Tháng 12',
];

function todayIsoVn(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date());
}

function defaultDiscountForDate(isoDate: string): number {
  const month = Number(isoDate.slice(5, 7));
  if (!month) return 6;
  return month % 2 === 1 ? 6 : 8;
}

function addDaysIso(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T12:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function formatDateVn(isoDate: string): string {
  const [y, m, d] = isoDate.split('-');
  if (!y || !m || !d) return isoDate;
  return `${d}/${m}/${y}`;
}

function customSaleTimeline(
  saleDate: string,
  teaserDays: number,
): { teaserStart: string; phase: 'before' | 'teaser' | 'active' | 'past' } {
  const today = todayIsoVn();
  const teaserStart = addDaysIso(saleDate, -teaserDays);
  if (today < teaserStart) return { teaserStart, phase: 'before' };
  if (today > saleDate) return { teaserStart, phase: 'past' };
  if (today === saleDate) return { teaserStart, phase: 'active' };
  return { teaserStart, phase: 'teaser' };
}

type SaleCalendarSettingsPanelProps = {
  /** Nhúng trong trang Khuyến mãi — không hiện tiêu đề trang riêng. */
  embedded?: boolean;
};

export default function SaleCalendarSettingsPanel({ embedded = false }: SaleCalendarSettingsPanelProps) {
  const [data, setData] = useState<AdminSaleCalendarSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [scheduledDate, setScheduledDate] = useState('');
  const [scheduledDiscount, setScheduledDiscount] = useState('6');
  const [manualDiscount, setManualDiscount] = useState('6');
  const [warehouseEnabled, setWarehouseEnabled] = useState(true);
  const [warehouseDiscount, setWarehouseDiscount] = useState('20');

  const load = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    setError(null);
    try {
      const res = await adminSaleCalendarAPI.getSettings();
      setData(res);
      setScheduledDate(res.scheduled_sale_date ?? '');
      setScheduledDiscount(
        String(res.scheduled_discount_percent ?? defaultDiscountForDate(res.scheduled_sale_date ?? todayIsoVn())),
      );
      setManualDiscount(
        String(res.manual_discount_percent ?? defaultDiscountForDate(res.manual_sale_date ?? todayIsoVn())),
      );
      setWarehouseEnabled(res.warehouse_clearance_enabled !== false);
      setWarehouseDiscount(String(res.warehouse_clearance_discount_percent ?? 20));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không tải được cấu hình sale');
    } finally {
      if (!opts?.silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  };

  const saveTeaserDays = async (days: number) => {
    setSaving(true);
    try {
      const res = await adminSaleCalendarAPI.updateSettings({ teaser_days: days });
      setData(res);
      showToast('Đã cập nhật số ngày teaser');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Lỗi lưu');
    } finally {
      setSaving(false);
    }
  };

  const saveWarehouseClearance = async () => {
    const pct = Number(warehouseDiscount);
    if (!Number.isFinite(pct) || pct < 0 || pct > 80) {
      setError('Giảm giá kho thanh lý phải từ 0–80%.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await adminSaleCalendarAPI.updateSettings({
        warehouse_clearance_enabled: warehouseEnabled,
        warehouse_clearance_discount_percent: pct,
      });
      setData(res);
      setWarehouseEnabled(res.warehouse_clearance_enabled !== false);
      setWarehouseDiscount(String(res.warehouse_clearance_discount_percent ?? pct));
      showToast('Đã lưu cài đặt hàng kho thanh lý');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không lưu được cài đặt kho thanh lý');
    } finally {
      setSaving(false);
    }
  };

  const toggleGlobalEnabled = async () => {
    if (!data) return;
    setSaving(true);
    try {
      const res = await adminSaleCalendarAPI.updateSettings({ enabled: !data.enabled });
      setData(res);
      showToast(res.enabled ? 'Đã bật sale site-wide' : 'Đã tắt toàn bộ sale site-wide');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Lỗi lưu');
    } finally {
      setSaving(false);
    }
  };

  const startManualToday = async () => {
    const discount = Number(manualDiscount);
    if (!Number.isFinite(discount) || discount < 0 || discount > 50) {
      setError('Phần trăm giảm phải từ 0 đến 50');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await adminSaleCalendarAPI.updateSettings({
        manual_sale_date: todayIsoVn(),
        manual_discount_percent: discount,
      });
      setData(res);
      showToast('Đã bật sale hôm nay — giảm giá ngay, không teaser');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Lỗi bật sale hôm nay');
    } finally {
      setSaving(false);
    }
  };

  const stopManualToday = async () => {
    setSaving(true);
    setError(null);
    try {
      const res = await adminSaleCalendarAPI.updateSettings({ clear_manual: true });
      setData(res);
      showToast('Đã dừng sale hôm nay');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Lỗi dừng sale hôm nay');
    } finally {
      setSaving(false);
    }
  };

  const saveScheduled = async () => {
    if (!scheduledDate) {
      setError('Vui lòng chọn ngày sale');
      return;
    }
    const discount = Number(scheduledDiscount);
    if (!Number.isFinite(discount) || discount < 0 || discount > 50) {
      setError('Phần trăm giảm phải từ 0 đến 50');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await adminSaleCalendarAPI.updateSettings({
        scheduled_sale_date: scheduledDate,
        scheduled_discount_percent: discount,
      });
      setData(res);
      showToast('Đã lưu sale ngày bất kỳ');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Lỗi lưu lịch');
    } finally {
      setSaving(false);
    }
  };

  const cancelScheduled = async () => {
    setSaving(true);
    setError(null);
    try {
      const res = await adminSaleCalendarAPI.updateSettings({ clear_scheduled: true });
      setData(res);
      setScheduledDate('');
      setScheduledDiscount('6');
      showToast('Đã hủy sale ngày bất kỳ');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Lỗi hủy lịch sale');
    } finally {
      setSaving(false);
    }
  };

  const updateMonth = async (
    month: number,
    patch: { enabled?: boolean; discount_percent_override?: number | null },
  ) => {
    setSaving(true);
    try {
      await adminSaleCalendarAPI.updateMonthRule({ month, ...patch });
      await load();
      if (patch.enabled !== undefined) {
        showToast(patch.enabled ? `Đã bật sale tháng ${month}` : `Đã tắt sale tháng ${month}`);
      } else {
        showToast(`Đã cập nhật tháng ${month}`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Lỗi lưu tháng');
    } finally {
      setSaving(false);
    }
  };

  const wrapperClass = embedded
    ? 'mt-8 bg-white rounded-xl border border-gray-200 p-6 space-y-5'
    : 'space-y-6';

  if (loading) {
    return (
      <div className={embedded ? 'mt-8 flex justify-center py-8' : 'p-6 flex justify-center'}>
        <div className="animate-spin w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className={embedded ? 'mt-8' : 'p-6'}>
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          {error}{' '}
          <button type="button" onClick={() => void load()} className="underline font-medium">
            Thử lại
          </button>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const current = data.current;
  const enabledMonthCount = data.month_rules.filter((r) => r.enabled).length;
  const customTimeline = data.scheduled_sale_date
    ? customSaleTimeline(data.scheduled_sale_date, data.teaser_days)
    : null;
  const manualActiveToday = data.manual_sale_date === todayIsoVn();

  return (
    <section className={wrapperClass} aria-label="Sale ngày trùng tháng" id="site-sale">
      <div>
        {embedded ? (
          <>
            <h2 className="text-lg font-bold text-gray-900">Sale ngày trùng tháng (site-wide)</h2>
            <p className="text-sm text-gray-600 mt-1">
              Bật/tắt từng ngày {`{tháng}/{tháng}`} hoặc đặt sale một ngày bất kỳ. Cộng dồn với mã ví/sinh nhật/hạng
              — tổng giảm tối đa 15% giá gốc đơn.
            </p>
          </>
        ) : (
          <>
            <h1 className="text-2xl font-bold text-gray-900">Sale ngày trùng tháng</h1>
            <p className="text-sm text-gray-600 mt-1">
              Bật/tắt từng ngày sale hoặc đặt một ngày bất kỳ. Teaser trước ngày sale (có thể chỉnh).
            </p>
          </>
        )}
      </div>

      {error ? (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          {error}{' '}
          <button type="button" onClick={() => setError(null)} className="underline font-medium">
            Đóng
          </button>
        </div>
      ) : null}

      {toast ? (
        <div className="bg-green-50 border border-green-200 text-green-800 rounded-lg px-4 py-2 text-sm">{toast}</div>
      ) : null}

      <div className={`${embedded ? '' : 'bg-white rounded-xl border border-gray-200 '}p-5 space-y-4`.trim()}>
        {!embedded ? null : <div className="border-t border-gray-100 -mt-2 pt-4" />}

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="font-semibold text-gray-900">Sale site-wide</p>
            <p className="text-xs text-gray-500">Tắt khẩn = không banner, không giảm giá, không feed sale</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={saving}
              onClick={() => void load({ silent: true })}
              className="px-3 py-2 rounded-lg border border-gray-300 bg-white text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-60"
            >
              Làm mới trạng thái
            </button>
            <button
              type="button"
              disabled={saving}
              onClick={() => void toggleGlobalEnabled()}
              className={`px-4 py-2 rounded-lg text-sm font-medium ${
                data.enabled ? 'bg-green-600 text-white' : 'bg-gray-300 text-gray-800'
              }`}
            >
              {data.enabled ? 'Đang bật' : 'Đang tắt'}
            </button>
          </div>
        </div>

        {!data.enabled ? (
          <div className="rounded-lg bg-gray-100 border border-gray-200 px-4 py-3 text-sm text-gray-700">
            Toàn bộ sale site-wide đang tắt — bật lại nút <strong>Đang tắt</strong> để chạy lịch tháng / ngày bất kỳ.
          </div>
        ) : null}

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Ngày teaser trước sale</label>
          <select
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
            value={data.teaser_days}
            disabled={saving}
            onChange={(e) => void saveTeaserDays(Number(e.target.value))}
          >
            {[1, 2, 3, 4, 5, 7].map((d) => (
              <option key={d} value={d}>
                {d} ngày
              </option>
            ))}
          </select>
        </div>

        {current?.phase ? (
          <div className="rounded-lg bg-orange-50 border border-orange-200 px-4 py-3 text-sm">
            <p className="font-semibold text-orange-900">
              Hiện tại: {current.phase === 'teaser' ? 'Sắp sale (teaser)' : 'Đang sale'} — {current.event_label}
            </p>
            <p className="text-orange-800">Giảm {current.discount_percent}%</p>
            {current.phase === 'teaser' ? (
              <p className="text-xs text-orange-800/90 mt-1">
                Giai đoạn teaser: shop hiện banner đếm ngược — giá sản phẩm chỉ giảm vào đúng ngày sale.
              </p>
            ) : null}
          </div>
        ) : data.scheduled_sale_date && customTimeline && (customTimeline.phase === 'teaser' || customTimeline.phase === 'active') && !current?.phase ? (
          <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-800 space-y-1">
            <p className="font-semibold">Backend chưa trả trạng thái sale — thường do process cũ còn giữ port 8001.</p>
            <p>
              Chạy <code className="text-xs bg-red-100 px-1 rounded">dev-clear-start.bat</code> (không dùng uvicorn{' '}
              <code className="text-xs bg-red-100 px-1 rounded">--reload</code> trên Windows). Sau đó mở{' '}
              <code className="text-xs bg-red-100 px-1 rounded">/api/v1/sale-calendar/current</code> — phải thấy{' '}
              <strong>phase: teaser</strong>.
            </p>
          </div>
        ) : data.scheduled_sale_date && customTimeline ? (
          <div className="rounded-lg bg-gray-50 border border-gray-200 px-4 py-3 text-sm text-gray-700 space-y-1">
            {customTimeline.phase === 'before' ? (
              <>
                <p>
                  Chưa đến teaser — bắt đầu <strong>{formatDateVn(customTimeline.teaserStart)}</strong> (trước{' '}
                  {data.teaser_days} ngày).
                </p>
                <p>
                  Sale giảm giá thật: <strong>{formatDateVn(data.scheduled_sale_date)}</strong>
                  {data.scheduled_discount_percent != null ? ` (−${data.scheduled_discount_percent}%)` : ''}.
                </p>
              </>
            ) : customTimeline.phase === 'past' ? (
              <p>
                Ngày sale <strong>{formatDateVn(data.scheduled_sale_date)}</strong> đã qua — chọn ngày mới hoặc bấm{' '}
                <strong>Hủy ngày sale</strong>.
              </p>
            ) : null}
          </div>
        ) : (
          <p className="text-sm text-gray-500">
            Hiện không trong cửa sổ teaser/active.
            {enabledMonthCount === 0 && !data.scheduled_sale_date ? ' Chưa có ngày sale nào được bật.' : null}
          </p>
        )}
      </div>

      <div className="rounded-xl border border-emerald-100 bg-emerald-50/40 p-5 space-y-3">
        <div>
          <p className="font-semibold text-gray-900">Sale hôm nay (flash — không teaser)</p>
          <p className="text-xs text-gray-500 mt-1">
            Giảm giá ngay cho toàn site hôm nay ({formatDateVn(todayIsoVn())}). Ưu tiên cao hơn lịch tháng; không chờ
            teaser.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Giảm giá (%)</label>
            <input
              type="number"
              min={0}
              max={50}
              step={0.5}
              className="w-24 border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
              value={manualDiscount}
              disabled={saving || !data.enabled}
              onChange={(e) => setManualDiscount(e.target.value)}
            />
          </div>
          <button
            type="button"
            disabled={saving || !data.enabled}
            onClick={() => void startManualToday()}
            className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700 disabled:opacity-60"
          >
            Bật sale hôm nay
          </button>
          {manualActiveToday ? (
            <button
              type="button"
              disabled={saving}
              onClick={() => void stopManualToday()}
              className="px-4 py-2 rounded-lg border border-gray-300 bg-white text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-60"
            >
              Dừng sale hôm nay
            </button>
          ) : null}
        </div>
        {manualActiveToday ? (
          <p className="text-xs text-emerald-800 font-medium">
            Đang sale flash hôm nay
            {data.manual_discount_percent != null ? ` — giảm ${data.manual_discount_percent}%` : ''}.
          </p>
        ) : (
          <p className="text-xs text-gray-500">Dùng cho flash sale hoặc test nhanh trên shop.</p>
        )}
      </div>

      <div className="rounded-xl border border-orange-100 bg-orange-50/40 p-5 space-y-3">
        <div>
          <p className="font-semibold text-gray-900">Sale ngày bất kỳ</p>
          <p className="text-xs text-gray-500 mt-1">
            Chọn một ngày cụ thể (không cần trùng tháng). Chạy kèm teaser — không ảnh hưởng bảng bật/tắt tháng bên
            dưới. Trong cửa sổ teaser/active, ngày đặt lịch được ưu tiên hiển thị.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Ngày sale</label>
            <input
              type="date"
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
              value={scheduledDate}
              min={todayIsoVn()}
              disabled={saving}
              onChange={(e) => {
                const next = e.target.value;
                setScheduledDate(next);
                if (next) setScheduledDiscount(String(defaultDiscountForDate(next)));
              }}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Giảm giá (%)</label>
            <input
              type="number"
              min={0}
              max={50}
              step={0.5}
              className="w-24 border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
              value={scheduledDiscount}
              disabled={saving}
              onChange={(e) => setScheduledDiscount(e.target.value)}
            />
          </div>
          <button
            type="button"
            disabled={saving}
            onClick={() => void saveScheduled()}
            className="px-4 py-2 rounded-lg bg-orange-600 text-white text-sm font-medium hover:bg-orange-700 disabled:opacity-60"
          >
            Lưu ngày sale
          </button>
          {data.scheduled_sale_date ? (
            <button
              type="button"
              disabled={saving}
              onClick={() => void cancelScheduled()}
              className="px-4 py-2 rounded-lg border border-red-200 bg-white text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-60"
            >
              Hủy ngày sale
            </button>
          ) : null}
        </div>
        {data.scheduled_sale_date ? (
          <p className="text-xs text-gray-600">
            Đang đặt: <strong>{formatDateVn(data.scheduled_sale_date)}</strong>
            {data.scheduled_discount_percent != null ? ` — giảm ${data.scheduled_discount_percent}%` : ''}. Teaser từ{' '}
            <strong>{formatDateVn(customTimeline?.teaserStart ?? addDaysIso(data.scheduled_sale_date, -data.teaser_days))}</strong>{' '}
            → giá shop giảm đúng ngày <strong>{formatDateVn(data.scheduled_sale_date)}</strong>.
          </p>
        ) : (
          <p className="text-xs text-gray-500">Chưa có — chọn ngày và bấm Lưu (tùy chọn, bên cạnh lịch tháng).</p>
        )}
      </div>

      <div className="rounded-xl border border-violet-100 bg-violet-50/40 p-5 space-y-3">
        <div>
          <p className="font-semibold text-gray-900">Thanh lý trong kho (duyệt hoàn)</p>
          <p className="text-xs text-gray-500 mt-1">
            Áp dụng cho sản phẩm import id có dấu «/» (vd. HN256/XL). Một mức % chung — hiển thị trên block
            «Thanh lý trong kho» ở trang sản phẩm (hoặc giá trực tiếp nếu chưa có SP gốc). Không cộng sale ngày trùng tháng.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="inline-flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={warehouseEnabled}
              disabled={saving}
              onChange={(e) => setWarehouseEnabled(e.target.checked)}
              className="rounded border-gray-300"
            />
            Bật giảm giá kho
          </label>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Giảm giá kho (%)</label>
            <input
              type="number"
              min={0}
              max={80}
              step={0.5}
              className="w-24 border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
              value={warehouseDiscount}
              disabled={saving}
              onChange={(e) => setWarehouseDiscount(e.target.value)}
            />
          </div>
          <button
            type="button"
            disabled={saving}
            onClick={() => void saveWarehouseClearance()}
            className="px-4 py-2 rounded-lg bg-violet-600 text-white text-sm font-medium hover:bg-violet-700 disabled:opacity-60"
          >
            Lưu cài đặt kho
          </button>
        </div>
      </div>

      <div className={`overflow-hidden rounded-xl border border-gray-200 ${embedded ? 'bg-white' : 'bg-white'}`}>
        <div className="px-5 py-3 border-b border-gray-100 space-y-1">
          <div className="font-semibold text-gray-900">Bật/tắt từng ngày {`{tháng}/{tháng}`}</div>
          <p className="text-xs text-gray-500">
            Mỗi dòng là một ngày lặp hàng tháng (6/6, 7/7…). Tắt = không sale và không teaser tháng đó.
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
              <tr>
                <th className="px-4 py-2">Tháng</th>
                <th className="px-4 py-2">Ngày sale</th>
                <th className="px-4 py-2">Mặc định</th>
                <th className="px-4 py-2">Override %</th>
                <th className="px-4 py-2">Bật/tắt</th>
              </tr>
            </thead>
            <tbody>
              {data.month_rules.map((rule) => (
                <tr
                  key={rule.month}
                  className={`border-t border-gray-100 ${!rule.enabled ? 'bg-gray-50/80 text-gray-500' : ''}`}
                >
                  <td className="px-4 py-2 font-medium">{MONTH_NAMES[rule.month - 1]}</td>
                  <td className="px-4 py-2">
                    {rule.month}/{rule.month}
                  </td>
                  <td className="px-4 py-2">{rule.default_discount_percent}%</td>
                  <td className="px-4 py-2">
                    <input
                      type="number"
                      min={0}
                      max={50}
                      step={0.5}
                      className="w-20 border border-gray-300 rounded px-2 py-1 disabled:bg-gray-50"
                      placeholder="Auto"
                      disabled={saving || !rule.enabled}
                      defaultValue={rule.discount_percent_override ?? ''}
                      onBlur={(e) => {
                        if (!rule.enabled) return;
                        const raw = e.target.value.trim();
                        void updateMonth(
                          rule.month,
                          raw === ''
                            ? { discount_percent_override: null }
                            : { discount_percent_override: Number(raw) },
                        );
                      }}
                    />
                  </td>
                  <td className="px-4 py-2">
                    <label
                      className={`inline-flex items-center gap-2 ${!saving ? 'cursor-pointer' : 'cursor-not-allowed opacity-60'}`}
                    >
                      <input
                        type="checkbox"
                        className="sr-only peer"
                        checked={rule.enabled}
                        disabled={saving}
                        onChange={() => void updateMonth(rule.month, { enabled: !rule.enabled })}
                      />
                      <span
                        aria-hidden
                        className={`relative inline-flex h-6 w-11 shrink-0 rounded-full transition-colors ${
                          rule.enabled ? 'bg-green-500' : 'bg-gray-300'
                        } ${!saving ? 'peer-focus-visible:ring-2 peer-focus-visible:ring-orange-400' : ''}`}
                      >
                        <span
                          className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
                            rule.enabled ? 'translate-x-5' : 'translate-x-0'
                          }`}
                        />
                      </span>
                      <span className="text-xs font-medium min-w-[2rem]">{rule.enabled ? 'Bật' : 'Tắt'}</span>
                    </label>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className={`${embedded ? 'rounded-xl border border-gray-100 bg-gray-50/50' : 'bg-white rounded-xl border border-gray-200'} p-5`}>
        <h3 className="font-semibold text-gray-900 mb-3">Lịch sắp tới</h3>
        {data.upcoming.length > 0 ? (
          <ul className="space-y-2 text-sm">
            {data.upcoming.map((ev) => (
              <li key={`${ev.event_date}-${ev.event_label}`} className="flex flex-wrap gap-x-3 gap-y-1 border-b border-gray-50 pb-2">
                <span className="font-medium">{ev.event_label}</span>
                <span className="text-gray-600">-{ev.discount_percent}%</span>
                <span className="text-gray-500 text-xs">Teaser từ {ev.teaser_start.slice(0, 10)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-gray-500">Chưa có sự kiện sắp tới.</p>
        )}
      </div>
    </section>
  );
}
