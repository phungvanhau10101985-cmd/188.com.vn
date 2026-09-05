'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  adminMarketingBannerAPI,
  type AdminMarketingBannerAsset,
  type AdminMarketingBannerKind,
} from '@/lib/admin-api';
import { notifyWarehouseBannersChanged, WAREHOUSE_BANNER_SYNC_EVENT } from '@/lib/warehouse-banner-sync';

function defaultDateKey() {
  const now = new Date();
  return `${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

function kindLabel(kind: AdminMarketingBannerKind | string) {
  if (kind === 'birthday') return 'Sinh nhật';
  if (kind === 'warehouse') return 'Sale kho';
  return 'Sale';
}

export default function MarketingBannerManager() {
  const [items, setItems] = useState<AdminMarketingBannerAsset[]>([]);
  const [kind, setKind] = useState<AdminMarketingBannerKind>('birthday');
  const [dateKey, setDateKey] = useState(defaultDateKey);
  const [warehousePercent, setWarehousePercent] = useState('30');
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await adminMarketingBannerAPI.list();
      setItems(response.items);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không tải được danh sách banner.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 15000);
    const onSync = () => {
      void load();
    };
    window.addEventListener(WAREHOUSE_BANNER_SYNC_EVENT, onSync);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener(WAREHOUSE_BANNER_SYNC_EVENT, onSync);
    };
  }, [load]);

  const grouped = useMemo(() => {
    const result = new Map<string, AdminMarketingBannerAsset[]>();
    items.forEach((item) => {
      const key = `${item.kind}:${item.campaign_key}`;
      result.set(key, [...(result.get(key) ?? []), item]);
    });
    return Array.from(result.values());
  }, [items]);

  const queueRegenerate = async (
    nextKind: AdminMarketingBannerKind,
    nextDateKey?: string,
    nextPercent?: number,
  ) => {
    setWorking(true);
    setError(null);
    setMessage(null);
    try {
      if (nextKind === 'warehouse') {
        const pct = Number(nextPercent);
        if (!Number.isFinite(pct) || pct <= 0 || pct > 80) {
          setError('Giảm giá kho phải từ 0.5–80%.');
          setWorking(false);
          return;
        }
        const response = await adminMarketingBannerAPI.regenerate({
          kind: 'warehouse',
          discount_percent: pct,
        });
        setMessage(response.message);
        notifyWarehouseBannersChanged();
      } else {
        const [month, day] = (nextDateKey || '').split('-').map(Number);
        if (!month || !day) {
          setError('Ngày-tháng không hợp lệ.');
          setWorking(false);
          return;
        }
        const response = await adminMarketingBannerAPI.regenerate({
          kind: nextKind,
          day,
          month,
        });
        setMessage(response.message);
      }
      window.setTimeout(() => void load(), 1200);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thể tạo lại banner.');
    } finally {
      setWorking(false);
    }
  };

  const activate = async (asset: AdminMarketingBannerAsset) => {
    setWorking(true);
    setError(null);
    try {
      await adminMarketingBannerAPI.activate(asset.id);
      setMessage(`Đã dùng lại phiên bản ${asset.version}.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thể kích hoạt ảnh này.');
    } finally {
      setWorking(false);
    }
  };

  return (
    <section id="ai-banners" className="mt-8 space-y-5 rounded-xl border border-orange-200 bg-white p-6">
      <div>
        <h2 className="text-lg font-bold text-gray-900">Banner AI sale, sinh nhật và kho</h2>
        <p className="mt-1 text-sm text-gray-600">
          Nano Banana Pro tạo một ảnh 21:9 dùng nguyên vẹn trên desktop và mobile. Slider trang
          chủ ưu tiên CMSN, rồi sale ngày trùng tháng, rồi sale kho. Ảnh sale kho được lưu theo
          từng mức % để dùng lại.
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

      <div className="grid gap-3 rounded-lg bg-orange-50 p-4 sm:grid-cols-[180px_180px_auto]">
        <select
          value={kind}
          onChange={(event) => {
            const nextKind = event.target.value as AdminMarketingBannerKind;
            setKind(nextKind);
            if (nextKind === 'sale') {
              const month = dateKey.slice(0, 2);
              setDateKey(`${month}-${month}`);
            }
          }}
          className="rounded-lg border border-orange-200 bg-white px-3 py-2 text-sm"
          aria-label="Loại banner"
        >
          <option value="birthday">Sinh nhật</option>
          <option value="sale">Sale trùng ngày-tháng</option>
          <option value="warehouse">Sale kho</option>
        </select>
        {kind === 'warehouse' ? (
          <input
            type="number"
            min={0.5}
            max={80}
            step={0.5}
            value={warehousePercent}
            onChange={(event) => setWarehousePercent(event.target.value)}
            className="rounded-lg border border-orange-200 bg-white px-3 py-2 text-sm"
            aria-label="Giảm giá kho (%)"
          />
        ) : (
          <input
            type="text"
            inputMode="numeric"
            value={dateKey}
            onChange={(event) => setDateKey(event.target.value)}
            placeholder="MM-DD"
            pattern="[0-1][0-9]-[0-3][0-9]"
            className="rounded-lg border border-orange-200 bg-white px-3 py-2 text-sm"
            aria-label="Ngày tháng dạng MM-DD"
          />
        )}
        <button
          type="button"
          disabled={working}
          onClick={() =>
            void queueRegenerate(
              kind,
              dateKey,
              kind === 'warehouse' ? Number(warehousePercent) : undefined,
            )
          }
          className="rounded-lg bg-orange-600 px-4 py-2 text-sm font-semibold text-white hover:bg-orange-700 disabled:opacity-50"
        >
          {working ? 'Đang xử lý…' : kind === 'warehouse' ? 'Tạo ảnh cho mức % này' : 'Tạo ảnh cho ngày này'}
        </button>
      </div>

      {loading ? (
        <div className="aspect-[21/9] animate-pulse rounded-lg bg-gray-100" aria-label="Đang tải banner" />
      ) : grouped.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 px-4 py-8 text-center text-sm text-gray-500">
          Chưa có banner. Cron hằng ngày tạo ảnh CMSN/sale; lưu % kho sẽ tạo banner sale kho.
        </div>
      ) : (
        <div className="space-y-5">
          {grouped.map((versions) => {
            const current = versions.find((item) => item.is_active) ?? versions[0];
            return (
              <article key={`${current.kind}:${current.campaign_key}`} className="rounded-xl border border-gray-200 p-4">
                <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold text-gray-900">
                      {kindLabel(current.kind)}
                      {current.kind === 'warehouse' ? '' : ` ${current.date_key}`} · giảm{' '}
                      {current.discount_percent}%
                    </p>
                    <p className="text-xs text-gray-500">
                      {current.model} · {versions.length} phiên bản · trạng thái {current.status}
                    </p>
                  </div>
                  <button
                    type="button"
                    disabled={working}
                    onClick={() =>
                      void queueRegenerate(
                        current.kind,
                        current.date_key,
                        current.kind === 'warehouse' ? current.discount_percent : undefined,
                      )
                    }
                    className="rounded-lg border border-orange-300 px-3 py-2 text-sm font-medium text-orange-700 hover:bg-orange-50 disabled:opacity-50"
                  >
                    Tạo lại
                  </button>
                </div>

                {current.image_url ? (
                  <img
                    src={current.image_url}
                    alt={`Banner ${current.kind} ${current.date_key}`}
                    className="h-auto w-full rounded-lg border border-gray-100"
                    loading="lazy"
                  />
                ) : (
                  <div className="rounded-lg bg-gray-100 px-4 py-8 text-center text-sm text-gray-600">
                    {current.status === 'generating' ? 'Đang tạo ảnh…' : current.error_message || 'Chưa có ảnh'}
                  </div>
                )}

                {versions.length > 1 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {versions.map((version) => (
                      <button
                        key={version.id}
                        type="button"
                        disabled={working || version.status !== 'ready' || version.is_active}
                        onClick={() => void activate(version)}
                        className={`rounded-md px-3 py-1.5 text-xs ${
                          version.is_active
                            ? 'bg-emerald-100 font-semibold text-emerald-800'
                            : 'border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-50'
                        }`}
                      >
                        v{version.version}{version.is_active ? ' đang dùng' : ' dùng lại'}
                      </button>
                    ))}
                  </div>
                ) : null}

                <details className="mt-3 text-xs text-gray-600">
                  <summary className="cursor-pointer font-medium">Xem prompt và lỗi</summary>
                  <p className="mt-2 whitespace-pre-wrap rounded bg-gray-50 p-3">{current.prompt}</p>
                  {current.error_message ? <p className="mt-2 text-red-700">{current.error_message}</p> : null}
                </details>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
