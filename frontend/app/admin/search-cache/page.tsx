'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  adminSearchCacheAPI,
  type ProductSearchCacheListResponse,
  type SearchKeywordStatsResponse,
} from '@/lib/admin-api';

const KW_PAGE = 100;
const CACHE_PAGE = 40;

function formatDt(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'short' });
  } catch {
    return iso;
  }
}

export default function AdminSearchCachePage() {
  const [kwDays, setKwDays] = useState(30);
  const [kwPage, setKwPage] = useState(1);
  const [kwData, setKwData] = useState<SearchKeywordStatsResponse | null>(null);
  const [kwLoading, setKwLoading] = useState(true);

  const [cachePage, setCachePage] = useState(1);
  const [cacheData, setCacheData] = useState<ProductSearchCacheListResponse | null>(null);
  const [cacheLoading, setCacheLoading] = useState(true);

  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);
  const [clearing, setClearing] = useState<'expired' | 'all' | null>(null);

  const showToast = (type: 'ok' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 4000);
  };

  const loadKeywords = useCallback(async () => {
    setKwLoading(true);
    try {
      const res = await adminSearchCacheAPI.getKeywordStats({
        days: kwDays,
        skip: (kwPage - 1) * KW_PAGE,
        limit: KW_PAGE,
      });
      setKwData(res);
    } catch (err: unknown) {
      showToast('err', (err as Error)?.message || 'Không tải được thống kê từ khóa');
      setKwData(null);
    } finally {
      setKwLoading(false);
    }
  }, [kwDays, kwPage]);

  const loadCache = useCallback(async () => {
    setCacheLoading(true);
    try {
      const res = await adminSearchCacheAPI.getProductCache({
        skip: (cachePage - 1) * CACHE_PAGE,
        limit: CACHE_PAGE,
      });
      setCacheData(res);
    } catch (err: unknown) {
      showToast('err', (err as Error)?.message || 'Không tải được cache');
      setCacheData(null);
    } finally {
      setCacheLoading(false);
    }
  }, [cachePage]);

  useEffect(() => {
    loadKeywords();
  }, [loadKeywords]);

  useEffect(() => {
    loadCache();
  }, [loadCache]);

  const kwTotalPages = useMemo(() => {
    if (!kwData) return 1;
    const t = kwData.total_distinct_keywords;
    return Math.max(1, Math.ceil(t / KW_PAGE));
  }, [kwData]);

  const handleClear = async (scope: 'expired' | 'all') => {
    if (scope === 'all') {
      const ok = confirm(
        'Xóa toàn bộ cache JSON tìm kiếm (product_search_cache)? Khách sẽ tải lại kết quả từ DB.',
      );
      if (!ok) return;
    }
    setClearing(scope);
    try {
      const r = await adminSearchCacheAPI.clearProductCache(scope);
      showToast('ok', `Đã xóa ${r.deleted} dòng cache (${r.scope}).`);
      await loadCache();
    } catch (err: unknown) {
      showToast('err', (err as Error)?.message || 'Xóa cache thất bại');
    } finally {
      setClearing(null);
    }
  };

  return (
      <div className="p-6 max-w-6xl">
        <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Cache & thống kê tìm kiếm</h1>
            <p className="text-sm text-gray-600 mt-1">
              Thống kê dựa trên nhật ký <code className="text-xs bg-gray-100 px-1 rounded">search_logs</code> (mỗi lần
              tìm có <code className="text-xs bg-gray-100 px-1 rounded">q</code> trên API sản phẩm). Cache hiển thị là
              bảng <code className="text-xs bg-gray-100 px-1 rounded">product_search_cache</code> (~5 phút TTL).
            </p>
          </div>
          {toast && (
            <span
              className={`text-sm px-3 py-1.5 rounded-lg shrink-0 ${
                toast.type === 'ok' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
              }`}
            >
              {toast.msg}
            </span>
          )}
        </div>

        <section className="bg-white rounded-xl border border-gray-200 p-4 mb-8">
          <div className="flex flex-wrap items-end gap-4 mb-4">
            <h2 className="text-lg font-semibold text-gray-900 w-full sm:w-auto sm:mr-auto">
              Từ khóa được tìm nhiều
            </h2>
            <label className="text-sm text-gray-600">
              Trong&nbsp;
              <select
                className="border border-gray-300 rounded-lg px-2 py-1.5 ml-1"
                value={kwDays}
                onChange={(e) => {
                  setKwPage(1);
                  setKwDays(Number(e.target.value));
                }}
              >
                {[7, 30, 90, 180, 365].map((d) => (
                  <option key={d} value={d}>
                    {d} ngày
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={() => loadKeywords()}
              className="text-sm px-3 py-1.5 rounded-lg border border-gray-300 hover:bg-gray-50"
            >
              Làm mới
            </button>
          </div>

          {kwLoading ? (
            <p className="text-gray-500">Đang tải…</p>
          ) : !kwData ? null : (
            <>
              <p className="text-sm text-gray-600 mb-2">
                <strong>{kwData.total_distinct_keywords}</strong> từ khóa khác nhau trong {kwData.days} ngày — cột «AI»
                là số lần có xử lý gợi ý/sửa query.
              </p>
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 text-left text-gray-500">
                      <th className="py-2 pr-4 font-medium w-12">#</th>
                      <th className="py-2 pr-4 font-medium">Từ khóa</th>
                      <th className="py-2 pr-4 font-medium text-right">Lần tìm</th>
                      <th className="py-2 pr-4 font-medium text-right">TB số SP</th>
                      <th className="py-2 font-medium text-right">Lần AI</th>
                    </tr>
                  </thead>
                  <tbody>
                    {kwData.items.map((row, i) => (
                      <tr key={`${row.keyword}-${i}`} className="border-b border-gray-100">
                        <td className="py-2 pr-4 text-gray-400">{(kwPage - 1) * KW_PAGE + i + 1}</td>
                        <td className="py-2 pr-4 font-medium text-gray-900 break-all max-w-md">{row.keyword}</td>
                        <td className="py-2 pr-4 text-right tabular-nums">{row.search_count}</td>
                        <td className="py-2 pr-4 text-right tabular-nums">{row.avg_result_count.toFixed(1)}</td>
                        <td className="py-2 text-right tabular-nums">{row.ai_processed_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {kwTotalPages > 1 && (
                <div className="flex items-center gap-2 mt-4">
                  <button
                    type="button"
                    disabled={kwPage <= 1}
                    onClick={() => setKwPage((p) => Math.max(1, p - 1))}
                    className="px-3 py-1 rounded border border-gray-300 disabled:opacity-40"
                  >
                    Trước
                  </button>
                  <span className="text-sm text-gray-600">
                    Trang {kwPage} / {kwTotalPages}
                  </span>
                  <button
                    type="button"
                    disabled={kwPage >= kwTotalPages}
                    onClick={() => setKwPage((p) => p + 1)}
                    className="px-3 py-1 rounded border border-gray-300 disabled:opacity-40"
                  >
                    Sau
                  </button>
                </div>
              )}
            </>
          )}
        </section>

        <section className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex flex-wrap items-center gap-4 mb-4">
            <h2 className="text-lg font-semibold text-gray-900">Cache JSON tìm kiếm</h2>
            <div className="flex flex-wrap gap-2 text-sm">
              <span className="px-2 py-1 rounded bg-slate-100 text-slate-700">
                Tổng: {cacheData?.total_rows ?? '—'}
              </span>
              <span className="px-2 py-1 rounded bg-green-50 text-green-800">
                Còn hạn: {cacheData?.active_rows ?? '—'}
              </span>
              <span className="px-2 py-1 rounded bg-amber-50 text-amber-900">
                Hết hạn: {cacheData?.expired_rows ?? '—'}
              </span>
            </div>
            <div className="flex flex-wrap gap-2 ml-auto">
              <button
                type="button"
                disabled={!!clearing}
                onClick={() => handleClear('expired')}
                className="text-sm px-3 py-1.5 rounded-lg border border-amber-300 text-amber-900 hover:bg-amber-50 disabled:opacity-50"
              >
                {clearing === 'expired' ? 'Đang xóa…' : 'Xóa cache hết hạn'}
              </button>
              <button
                type="button"
                disabled={!!clearing}
                onClick={() => handleClear('all')}
                className="text-sm px-3 py-1.5 rounded-lg border border-red-300 text-red-800 hover:bg-red-50 disabled:opacity-50"
              >
                {clearing === 'all' ? 'Đang xóa…' : 'Xóa toàn bộ cache'}
              </button>
              <button
                type="button"
                onClick={() => loadCache()}
                className="text-sm px-3 py-1.5 rounded-lg border border-gray-300 hover:bg-gray-50"
              >
                Làm mới
              </button>
            </div>
          </div>

          <p className="text-sm text-gray-600 mb-3">
            Khóa lưu là hash; cột «Gợi ý» lấy từ trường normalized/applied trong JSON nếu có.
          </p>

          {cacheLoading ? (
            <p className="text-gray-500">Đang tải…</p>
          ) : !cacheData ? null : (
            <>
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 text-left text-gray-500">
                      <th className="py-2 pr-3 font-medium">Khóa</th>
                      <th className="py-2 pr-3 font-medium">Gợi ý</th>
                      <th className="py-2 pr-3 font-medium text-right">Kích thước</th>
                      <th className="py-2 pr-3 font-medium">Tạo</th>
                      <th className="py-2 font-medium">Hết hạn</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cacheData.items.map((row) => (
                      <tr key={row.cache_key} className="border-b border-gray-100">
                        <td className="py-2 pr-3 font-mono text-xs text-gray-700 break-all max-w-[10rem]">
                          {row.cache_key}
                        </td>
                        <td className="py-2 pr-3 text-gray-800 break-all max-w-xs">
                          {row.hint_query || '—'}
                        </td>
                        <td className="py-2 pr-3 text-right tabular-nums">{row.response_size_bytes} B</td>
                        <td className="py-2 pr-3 whitespace-nowrap text-gray-600">{formatDt(row.created_at)}</td>
                        <td className="py-2 whitespace-nowrap text-gray-600">{formatDt(row.expires_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex items-center gap-2 mt-4">
                <button
                  type="button"
                  disabled={cachePage <= 1}
                  onClick={() => setCachePage((p) => Math.max(1, p - 1))}
                  className="px-3 py-1 rounded border border-gray-300 disabled:opacity-40"
                >
                  Trước
                </button>
                <span className="text-sm text-gray-600">Trang {cachePage}</span>
                <button
                  type="button"
                  disabled={cacheData.items.length < CACHE_PAGE}
                  onClick={() => setCachePage((p) => p + 1)}
                  className="px-3 py-1 rounded border border-gray-300 disabled:opacity-40"
                >
                  Sau
                </button>
              </div>
            </>
          )}
        </section>
      </div>
  );
}
