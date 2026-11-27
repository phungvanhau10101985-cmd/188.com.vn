'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import {
  adminCounterfeitReportAPI,
  type AdminCounterfeitReport,
} from '@/lib/admin-api';
import { productPathSlugFromApi } from '@/lib/product-path-slug';

function formatPrice(value: number): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return new Intl.NumberFormat('vi-VN').format(n) + 'đ';
}

export default function AdminCounterfeitReportPage() {
  const [page, setPage] = useState(1);
  const [draftQuery, setDraftQuery] = useState('');
  const [query, setQuery] = useState('');
  const [data, setData] = useState<AdminCounterfeitReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    adminCounterfeitReportAPI
      .list({ page, q: query })
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Không tải được báo cáo');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [page, query]);

  useEffect(() => load(), [load]);

  const total = data?.total ?? 0;
  const pageSize = data?.page_size || 50;
  const pages = Math.max(1, Math.ceil(total / pageSize));

  async function onExport() {
    setExporting(true);
    setExportError(null);
    try {
      await adminCounterfeitReportAPI.exportFile(query);
    } catch (err: unknown) {
      setExportError(err instanceof Error ? err.message : 'Không xuất được file');
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">Báo cáo hàng giả</h1>
          <p className="mt-1 max-w-2xl text-sm text-zinc-600">
            Batch Gemini 3.8 Flash tự chạy. Sản phẩm đã đăng vẫn hiện trên web. Hàng có logo bị ẩn,
            không bản địa hóa và không vào nguồn cấp. Hàng sạch phải bản địa hóa xong mới vào
            Google, Meta, TikTok và web nền tảng khác. Kết quả kiểm tra có thể về trong 24 giờ.
            Model AI không chạy thì email admin, và nếu chưa xử lý thì mỗi ngày một lần.
          </p>
        </div>
        <button
          type="button"
          onClick={onExport}
          disabled={exporting || total === 0}
          className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {exporting ? 'Đang xuất…' : 'Xuất Excel'}
        </button>
      </div>

      <form
        className="mt-4 flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          setPage(1);
          setQuery(draftQuery.trim());
        }}
      >
        <input
          value={draftQuery}
          onChange={(event) => setDraftQuery(event.target.value)}
          placeholder="Mã, SKU hoặc tên sản phẩm"
          className="w-full max-w-md rounded-lg border border-zinc-300 px-3 py-2 text-sm"
          aria-label="Tìm sản phẩm nghi hàng giả"
        />
        <button type="submit" className="rounded-lg border border-zinc-300 px-3 py-2 text-sm">
          Tìm
        </button>
      </form>

      {exportError && (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {exportError}
        </div>
      )}

      {error && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}{' '}
          <button type="button" onClick={load} className="font-medium underline">
            Thử lại
          </button>
        </div>
      )}

      {loading && <p className="mt-6 text-sm text-zinc-500">Đang tải danh sách…</p>}

      {!loading && !error && total === 0 && (
        <p className="mt-6 rounded-lg border border-dashed border-zinc-300 px-4 py-8 text-center text-sm text-zinc-600">
          Chưa có sản phẩm nghi hàng giả.
        </p>
      )}

      {!loading && !error && total > 0 && (
        <>
          <p className="mt-4 text-sm text-zinc-600">{total} sản phẩm</p>
          <div className="mt-2 overflow-x-auto rounded-lg border border-zinc-200">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-zinc-50 text-zinc-600">
                <tr>
                  <th className="px-3 py-2 font-medium">Sản phẩm</th>
                  <th className="px-3 py-2 font-medium">Dấu hiệu</th>
                  <th className="px-3 py-2 font-medium">Giá</th>
                  <th className="px-3 py-2 font-medium">Trạng thái</th>
                </tr>
              </thead>
              <tbody>
                {data?.items.map((item) => (
                  <tr key={item.id} className="border-t border-zinc-100 align-top">
                    <td className="px-3 py-3">
                      <div className="font-medium text-zinc-900">{item.name || '—'}</div>
                      <div className="text-xs text-zinc-500">
                        {item.product_id}
                        {item.code ? ` · ${item.code}` : ''}
                      </div>
                      {productPathSlugFromApi(item.slug, item.product_id) ? (
                        <Link
                          href={`/products/${productPathSlugFromApi(item.slug, item.product_id)}`}
                          className="text-xs text-zinc-700 underline"
                        >
                          Xem trang sản phẩm
                        </Link>
                      ) : null}
                    </td>
                    <td className="px-3 py-3">
                      <div>{item.hits.join(', ') || '—'}</div>
                      <ul className="mt-1 space-y-1 text-xs text-zinc-500">
                        {item.images.map((image) => (
                          <li key={image.url}>
                            <a href={image.url} className="break-all underline" target="_blank" rel="noreferrer">
                              {image.hits.join(', ')}
                            </a>
                          </li>
                        ))}
                      </ul>
                    </td>
                    <td className="px-3 py-3 whitespace-nowrap">{formatPrice(item.price)}</td>
                    <td className="px-3 py-3">{item.is_active ? 'Đang bán' : 'Đang ẩn'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {pages > 1 && (
            <div className="mt-3 flex items-center gap-2 text-sm">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((current) => Math.max(1, current - 1))}
                className="rounded border border-zinc-300 px-3 py-1 disabled:opacity-40"
              >
                Trước
              </button>
              <span>
                {page}/{pages}
              </span>
              <button
                type="button"
                disabled={page >= pages}
                onClick={() => setPage((current) => current + 1)}
                className="rounded border border-zinc-300 px-3 py-1 disabled:opacity-40"
              >
                Sau
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
