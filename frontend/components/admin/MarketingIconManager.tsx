'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

import { APP_WEB_ICON_URL } from '@/lib/app-web-icon';
import {
  adminMarketingIconAPI,
  type AdminMarketingIconAsset,
} from '@/lib/admin-api';

function defaultSaleDateKey() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  return `${month}-${month}`;
}

export default function MarketingIconManager() {
  const [items, setItems] = useState<AdminMarketingIconAsset[]>([]);
  const [dateKey, setDateKey] = useState(defaultSaleDateKey);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await adminMarketingIconAPI.list();
      setItems(response.items);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không tải được danh sách icon.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 15000);
    return () => window.clearInterval(timer);
  }, [load]);

  const grouped = useMemo(() => {
    const result = new Map<string, AdminMarketingIconAsset[]>();
    items.forEach((item) => {
      const key = `${item.kind}:${item.campaign_key}`;
      result.set(key, [...(result.get(key) ?? []), item]);
    });
    return Array.from(result.values());
  }, [items]);

  const queueRegenerate = async (nextDateKey?: string) => {
    setWorking(true);
    setError(null);
    setMessage(null);
    try {
      const [month, day] = (nextDateKey || '').split('-').map(Number);
      if (!month || !day) {
        setError('Ngày-tháng không hợp lệ.');
        setWorking(false);
        return;
      }
      if (day !== month) {
        setError('Icon sale chỉ tạo cho ngày trùng tháng (1.1, 9.9, 11.11…).');
        setWorking(false);
        return;
      }
      const response = await adminMarketingIconAPI.regenerate({ day, month });
      setMessage(response.message);
      window.setTimeout(() => void load(), 1200);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thể tạo lại icon.');
    } finally {
      setWorking(false);
    }
  };

  return (
    <section id="ai-icons" className="mt-8 space-y-5 rounded-xl border border-amber-200 bg-white p-6">
      <div>
        <h2 className="text-lg font-bold text-gray-900">Favicon / ảnh đại diện web app AI</h2>
        <p className="mt-1 text-sm text-gray-600">
          Nano Banana chỉnh ảnh logo vuông hiện tại thành icon sale cùng ngày-tháng. Khi sale teaser
          hoặc đang diễn ra, logo trên đầu trang (và favicon tab) tự đổi sang icon này — khách mở shop
          là thấy, không cần cài lại web app. Hết sale tự về logo chữ.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-4 rounded-lg bg-amber-50 p-4">
        <div>
          <p className="text-xs font-medium text-amber-900">Logo gốc</p>
          <img
            src={APP_WEB_ICON_URL}
            alt="Favicon / ảnh đại diện mặc định"
            className="mt-2 h-16 w-16 rounded-2xl border border-amber-200 bg-white object-cover"
          />
        </div>
        <p className="text-sm text-amber-900">
          AI giữ nhân diện logo này, thêm huy hiệu SALE ngày.tháng trên icon vuông 512×512.
        </p>
      </div>

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}{' '}
          <button type="button" onClick={() => void load()} className="font-medium underline">
            Thử lại
          </button>
        </div>
      ) : null}
      {message ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {message}
        </div>
      ) : null}

      <div className="grid gap-3 rounded-lg bg-amber-50 p-4 sm:grid-cols-[180px_auto]">
        <input
          type="text"
          inputMode="numeric"
          value={dateKey}
          onChange={(event) => setDateKey(event.target.value)}
          placeholder="MM-DD"
          pattern="[0-1][0-9]-[0-3][0-9]"
          className="rounded-lg border border-amber-200 bg-white px-3 py-2 text-sm"
          aria-label="Ngày tháng dạng MM-DD, ngày trùng tháng"
        />
        <button
          type="button"
          disabled={working}
          onClick={() => void queueRegenerate(dateKey)}
          className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-700 disabled:opacity-50"
        >
          {working ? 'Đang xử lý…' : 'Tạo icon vuông cho ngày này'}
        </button>
      </div>

      {loading ? (
        <div className="h-24 w-24 animate-pulse rounded-2xl bg-gray-100" aria-label="Đang tải icon" />
      ) : grouped.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 px-4 py-8 text-center text-sm text-gray-500">
          Chưa có icon sale. Cron banner/icon tạo trước ngày trùng tháng; hoặc bấm tạo ở trên.
        </div>
      ) : (
        <div className="space-y-5">
          {grouped.map((versions) => {
            const generating = versions.find((item) => item.status === 'generating');
            const failed = versions.find((item) => item.status === 'failed');
            const current =
              versions.find((item) => item.is_active && item.status === 'ready') ??
              generating ??
              failed ??
              versions[0];
            const displayImage =
              versions.find((item) => item.is_active && item.image_url)?.image_url ||
              current.image_url;
            const statusLabel = generating ? 'đang tạo lại' : current.status;
            return (
              <article key={`${current.kind}:${current.campaign_key}`} className="rounded-xl border border-gray-200 p-4">
                <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold text-gray-900">
                      Sale {current.date_key} · giảm {current.discount_percent}%
                    </p>
                    <p className="text-xs text-gray-500">
                      {current.model} · {current.image_width || 512}×{current.image_height || 512} · trạng thái{' '}
                      {statusLabel}
                    </p>
                  </div>
                  <button
                    type="button"
                    disabled={working || Boolean(generating)}
                    onClick={() => void queueRegenerate(current.date_key)}
                    className="rounded-lg border border-amber-300 px-3 py-2 text-sm font-medium text-amber-800 hover:bg-amber-50 disabled:opacity-50"
                  >
                    {generating ? 'Đang tạo lại…' : 'Tạo lại'}
                  </button>
                </div>

                {displayImage ? (
                  <img
                    src={displayImage}
                    alt={`Icon sale ${current.date_key}`}
                    className="h-32 w-32 rounded-3xl border border-gray-100 bg-white object-cover"
                    loading="lazy"
                  />
                ) : (
                  <div className="rounded-lg bg-gray-100 px-4 py-8 text-center text-sm text-gray-600">
                    {generating ? 'Đang tạo ảnh…' : current.error_message || 'Chưa có ảnh'}
                  </div>
                )}
                {generating && displayImage ? (
                  <p className="mt-2 text-xs text-amber-700">
                    Đang tạo icon mới. Icon cũ vẫn dùng đến khi ảnh mới xong.
                  </p>
                ) : null}

                <details className="mt-3 text-xs text-gray-600">
                  <summary className="cursor-pointer font-medium">Xem prompt và lỗi</summary>
                  <p className="mt-2 whitespace-pre-wrap rounded bg-gray-50 p-3">{current.prompt}</p>
                  {failed?.error_message || current.error_message ? (
                    <p className="mt-2 text-red-700">{failed?.error_message || current.error_message}</p>
                  ) : null}
                </details>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
