'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  adminListingFacetCacheAPI,
  type ListingFacetCacheListResponse,
  type ListingFacetCacheRowItem,
} from '@/lib/admin-api';

const PAGE_SIZE = 40;

const SCOPE_LABELS: Record<string, string> = {
  category_l1: 'Danh mục L1',
  category_l2: 'Danh mục L2',
  category_l3: 'Danh mục L3',
  search_q: 'Tìm kiếm',
  seo_cluster: 'SEO cluster',
};

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

function formatPrice(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—';
  return `${Math.round(v).toLocaleString('vi-VN')} đ`;
}

export default function AdminListingFacetCachePage() {
  const [scopeFilter, setScopeFilter] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState<ListingFacetCacheListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);
  const [rebuilding, setRebuilding] = useState<string | null>(null);
  const [pinKeyword, setPinKeyword] = useState('');
  const [pinning, setPinning] = useState(false);

  const showToast = (type: 'ok' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 4500);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await adminListingFacetCacheAPI.list({
        scope_type: scopeFilter || undefined,
        skip: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
      });
      setData(res);
    } catch (err: unknown) {
      showToast('err', (err as Error)?.message || 'Không tải được cache bộ lọc');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [page, scopeFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const totalPages = useMemo(() => {
    if (!data) return 1;
    return Math.max(1, Math.ceil(data.total_rows / PAGE_SIZE));
  }, [data]);

  const handleRebuild = async (scope: 'category' | 'search' | 'seo_cluster' | 'all') => {
    if (scope === 'all') {
      const ok = confirm('Rebuild toàn bộ cache bộ lọc? Có thể mất vài phút với dữ liệu lớn.');
      if (!ok) return;
    }
    setRebuilding(scope);
    try {
      const r = await adminListingFacetCacheAPI.rebuild(scope);
      showToast('ok', r.message || `Đã rebuild ${r.rebuilt} bộ lọc.`);
      await load();
    } catch (err: unknown) {
      showToast('err', (err as Error)?.message || 'Rebuild thất bại');
    } finally {
      setRebuilding(null);
    }
  };

  const handlePinSearch = async () => {
    const kw = pinKeyword.trim();
    if (!kw) {
      showToast('err', 'Nhập từ khóa tìm kiếm');
      return;
    }
    setPinning(true);
    try {
      await adminListingFacetCacheAPI.pinSearch(kw);
      showToast('ok', `Đã ghim cache bộ lọc cho «${kw}».`);
      setPinKeyword('');
      await load();
    } catch (err: unknown) {
      showToast('err', (err as Error)?.message || 'Không ghim được từ khóa');
    } finally {
      setPinning(false);
    }
  };

  const handleToggle = async (row: ListingFacetCacheRowItem) => {
    try {
      await adminListingFacetCacheAPI.toggleEnabled(row.id, !row.is_enabled);
      showToast('ok', row.is_enabled ? 'Đã tắt cache' : 'Đã bật cache');
      await load();
    } catch (err: unknown) {
      showToast('err', (err as Error)?.message || 'Không cập nhật được');
    }
  };

  const handleDelete = async (row: ListingFacetCacheRowItem) => {
    const ok = confirm(`Xóa cache «${row.display_label || row.scope_key}»?`);
    if (!ok) return;
    try {
      await adminListingFacetCacheAPI.deleteRow(row.id);
      showToast('ok', 'Đã xóa cache');
      await load();
    } catch (err: unknown) {
      showToast('err', (err as Error)?.message || 'Không xóa được');
    }
  };

  const counts = data?.counts_by_type ?? {};

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Cache bộ lọc listing</h1>
        <p className="text-sm text-gray-600 mt-1">
          Bộ lọc size/màu/kiểu/giá được lưu sẵn cho danh mục (luôn), từ khóa tìm kiếm (≥200 SP hoặc
          ghim thủ công), SEO cluster (≥200 SP). Tự làm mới khi thêm/sửa/xóa sản phẩm.
        </p>
      </div>

      {toast && (
        <div
          className={`rounded-lg px-4 py-3 text-sm border ${
            toast.type === 'ok'
              ? 'bg-green-50 border-green-200 text-green-800'
              : 'bg-red-50 border-red-200 text-red-700'
          }`}
        >
          {toast.msg}
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {Object.entries(SCOPE_LABELS).map(([key, label]) => (
          <div key={key} className="bg-white rounded-xl border border-gray-200 p-3 text-center">
            <div className="text-xs text-gray-500">{label}</div>
            <div className="text-xl font-semibold text-gray-900">{counts[key] ?? 0}</div>
          </div>
        ))}
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-4">
        <h2 className="font-semibold text-gray-900">Ghim từ khóa tìm kiếm (whitelist)</h2>
        <div className="flex flex-wrap gap-2">
          <input
            type="text"
            value={pinKeyword}
            onChange={(e) => setPinKeyword(e.target.value)}
            placeholder="Ví dụ: giày sneaker nữ"
            className="flex-1 min-w-[200px] border border-gray-300 rounded-lg px-3 py-2 text-sm"
            onKeyDown={(e) => e.key === 'Enter' && handlePinSearch()}
          />
          <button
            type="button"
            onClick={handlePinSearch}
            disabled={pinning}
            className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
          >
            {pinning ? 'Đang ghim…' : 'Ghim & rebuild'}
          </button>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
        <h2 className="font-semibold text-gray-900">Rebuild hàng loạt</h2>
        <div className="flex flex-wrap gap-2">
          {(
            [
              ['category', 'Danh mục'],
              ['search', 'Tìm kiếm'],
              ['seo_cluster', 'SEO cluster'],
              ['all', 'Tất cả'],
            ] as const
          ).map(([scope, label]) => (
            <button
              key={scope}
              type="button"
              onClick={() => handleRebuild(scope)}
              disabled={rebuilding !== null}
              className="px-3 py-1.5 rounded-lg border border-gray-300 text-sm hover:bg-gray-50 disabled:opacity-50"
            >
              {rebuilding === scope ? 'Đang chạy…' : `Rebuild ${label}`}
            </button>
          ))}
          <button
            type="button"
            onClick={load}
            className="px-3 py-1.5 rounded-lg border border-gray-300 text-sm hover:bg-gray-50"
          >
            Làm mới danh sách
          </button>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <label className="text-sm text-gray-700">
            Lọc loại:
            <select
              value={scopeFilter}
              onChange={(e) => {
                setScopeFilter(e.target.value);
                setPage(1);
              }}
              className="ml-2 border border-gray-300 rounded-lg px-2 py-1 text-sm"
            >
              <option value="">Tất cả</option>
              {Object.entries(SCOPE_LABELS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          <span className="text-sm text-gray-500">{data ? `${data.total_rows} dòng` : ''}</span>
        </div>

        {loading ? (
          <p className="text-sm text-gray-500 py-8 text-center">Đang tải…</p>
        ) : !data?.items.length ? (
          <p className="text-sm text-gray-500 py-8 text-center">
            Chưa có cache. Bấm «Rebuild Danh mục» hoặc tìm kiếm trên site với từ khóa ≥200 SP.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left text-gray-600">
                  <th className="py-2 pr-3">Loại</th>
                  <th className="py-2 pr-3">Nhãn / key</th>
                  <th className="py-2 pr-3">SP</th>
                  <th className="py-2 pr-3">Size</th>
                  <th className="py-2 pr-3">Màu</th>
                  <th className="py-2 pr-3">Giá</th>
                  <th className="py-2 pr-3">Trạng thái</th>
                  <th className="py-2 pr-3">Cập nhật</th>
                  <th className="py-2">Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => (
                  <tr key={row.id} className="border-b border-gray-100 hover:bg-gray-50/80">
                    <td className="py-2 pr-3 whitespace-nowrap">
                      {SCOPE_LABELS[row.scope_type] || row.scope_type}
                      {row.is_manual && (
                        <span className="ml-1 text-xs text-indigo-600">(ghim)</span>
                      )}
                    </td>
                    <td className="py-2 pr-3 max-w-[220px]">
                      <div className="font-medium text-gray-900 truncate">
                        {row.display_label || row.scope_key}
                      </div>
                      <div className="text-xs text-gray-400 truncate">{row.scope_key}</div>
                    </td>
                    <td className="py-2 pr-3">{row.product_count.toLocaleString('vi-VN')}</td>
                    <td className="py-2 pr-3">{row.sizes_count}</td>
                    <td className="py-2 pr-3">{row.colors_count}</td>
                    <td className="py-2 pr-3 whitespace-nowrap text-xs">
                      {formatPrice(row.price_min)} – {formatPrice(row.price_max)}
                    </td>
                    <td className="py-2 pr-3">
                      {!row.is_enabled && (
                        <span className="text-xs text-gray-500 block">Tắt</span>
                      )}
                      {row.is_stale && (
                        <span className="text-xs text-amber-600 block">Stale</span>
                      )}
                      {row.is_enabled && !row.is_stale && (
                        <span className="text-xs text-green-600">OK</span>
                      )}
                    </td>
                    <td className="py-2 pr-3 whitespace-nowrap text-xs text-gray-500">
                      {formatDt(row.updated_at)}
                    </td>
                    <td className="py-2 whitespace-nowrap">
                      <button
                        type="button"
                        onClick={() => handleToggle(row)}
                        className="text-indigo-600 hover:underline text-xs mr-2"
                      >
                        {row.is_enabled ? 'Tắt' : 'Bật'}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(row)}
                        className="text-red-600 hover:underline text-xs"
                      >
                        Xóa
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-3 mt-4 pt-4 border-t border-gray-100">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="px-3 py-1 rounded border text-sm disabled:opacity-40"
            >
              Trước
            </button>
            <span className="text-sm text-gray-600">
              Trang {page}/{totalPages}
            </span>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
              className="px-3 py-1 rounded border text-sm disabled:opacity-40"
            >
              Sau
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
