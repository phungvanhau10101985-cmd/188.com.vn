'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ladipageAdminAPI, type Ladipage } from '@/lib/admin-api';
import { useToast } from '@/components/ToastProvider';

const STATUS_LABEL: Record<string, string> = {
  draft: 'Nháp',
  published: 'Đã đăng',
};

const SOURCE_LABEL: Record<string, string> = {
  category: 'Danh mục',
  products: 'Sản phẩm',
};

function sourceDetail(item: Ladipage): string {
  if (item.source_type === 'category') {
    return item.category_name ? `Danh mục · ${item.category_name}` : 'Danh mục cấp 3';
  }
  const n = item.product_ids?.length ?? 0;
  if (n <= 1) return n === 1 ? '1 sản phẩm' : 'Sản phẩm (chưa chọn)';
  return `${n} sản phẩm`;
}

function formatDate(raw?: string | null): string {
  if (!raw) return '—';
  try {
    return new Date(raw).toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'short' });
  } catch {
    return raw;
  }
}

export default function AdminLadipageListPage() {
  const router = useRouter();
  const { pushToast } = useToast();
  const [items, setItems] = useState<Ladipage[]>([]);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState<number | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setStatus('loading');
    setError('');
    try {
      const res = await ladipageAdminAPI.list({ limit: 100 });
      setItems(res.items);
      setStatus('ready');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không tải được danh sách');
      setStatus('error');
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const togglePublish = async (item: Ladipage) => {
    setBusyId(item.id);
    try {
      if (item.status === 'published') {
        await ladipageAdminAPI.unpublish(item.id);
        pushToast({ title: 'Đã chuyển về nháp', variant: 'success', durationMs: 2500 });
      } else {
        await ladipageAdminAPI.publish(item.id);
        pushToast({ title: 'Đã đăng trang', description: `Xem tại ${item.public_url || `/lp/${item.slug}`}`, variant: 'success', durationMs: 3500 });
      }
      await load();
    } catch (err) {
      pushToast({
        title: 'Thao tác thất bại',
        description: err instanceof Error ? err.message : String(err),
        variant: 'error',
        durationMs: 3500,
      });
    } finally {
      setBusyId(null);
    }
  };

  const confirmDelete = async (id: number) => {
    setBusyId(id);
    try {
      await ladipageAdminAPI.remove(id);
      pushToast({ title: 'Đã xóa ladipage', variant: 'success', durationMs: 2500 });
      setConfirmDeleteId(null);
      await load();
    } catch (err) {
      pushToast({
        title: 'Không xóa được',
        description: err instanceof Error ? err.message : String(err),
        variant: 'error',
        durationMs: 3500,
      });
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="mx-auto max-w-6xl p-4 md:p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900 md:text-2xl">Ladipage AI</h1>
          <p className="mt-1 text-sm text-gray-500">
            Tạo landing page bán hàng tự động bằng AI theo danh mục hoặc sản phẩm chọn.
          </p>
        </div>
        <Link
          href="/admin/ladipage/new"
          className="inline-flex items-center rounded-full bg-orange-600 px-5 py-2.5 text-sm font-semibold text-white shadow hover:bg-orange-700"
        >
          + Tạo ladipage mới
        </Link>
      </div>

      {status === 'loading' && (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-16 animate-pulse rounded-xl bg-gray-100" />
          ))}
        </div>
      )}

      {status === 'error' && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}{' '}
          <button type="button" onClick={load} className="font-medium underline">
            Thử lại
          </button>
        </div>
      )}

      {status === 'ready' && items.length === 0 && (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white p-10 text-center">
          <p className="text-gray-500">Chưa có ladipage nào.</p>
          <Link
            href="/admin/ladipage/new"
            className="mt-3 inline-flex items-center rounded-full bg-orange-600 px-5 py-2 text-sm font-semibold text-white shadow hover:bg-orange-700"
          >
            Tạo ladipage đầu tiên
          </Link>
        </div>
      )}

      {status === 'ready' && items.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-gray-100 bg-white shadow-sm">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="border-b border-gray-100 bg-gray-50 text-xs uppercase text-gray-500">
              <tr>
                <th className="px-4 py-3">Tiêu đề</th>
                <th className="px-4 py-3">Nguồn</th>
                <th className="px-4 py-3">Trạng thái</th>
                <th className="px-4 py-3">Cập nhật</th>
                <th className="px-4 py-3 text-right">Hành động</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {items.map((item) => (
                <tr key={item.id} className="hover:bg-gray-50/60">
                  <td className="px-4 py-3">
                    <div className="font-medium text-gray-900">{item.title}</div>
                    <div className="text-xs text-gray-400">{item.public_url || `/lp/${item.slug}`}</div>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{sourceDetail(item)}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        item.status === 'published'
                          ? 'bg-emerald-100 text-emerald-700'
                          : 'bg-gray-100 text-gray-600'
                      }`}
                    >
                      {STATUS_LABEL[item.status] || item.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500">{formatDate(item.updated_at || item.created_at)}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => router.push(`/admin/ladipage/${item.id}/edit`)}
                        className="rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
                      >
                        Sửa
                      </button>
                      {item.status === 'published' && (
                        <a
                          href={item.public_url || `/lp/${item.slug}`}
                          target="_blank"
                          rel="noreferrer"
                          className="rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
                        >
                          Xem
                        </a>
                      )}
                      <button
                        type="button"
                        disabled={busyId === item.id}
                        onClick={() => togglePublish(item)}
                        className="rounded-md border border-orange-200 px-3 py-1.5 text-xs font-medium text-orange-700 hover:bg-orange-50 disabled:opacity-50"
                      >
                        {item.status === 'published' ? 'Gỡ đăng' : 'Đăng trang'}
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirmDeleteId(item.id)}
                        className="rounded-md border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50"
                      >
                        Xóa
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {confirmDeleteId != null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-xl bg-white p-5 shadow-xl">
            <h2 className="text-base font-semibold text-gray-900">Xóa ladipage này?</h2>
            <p className="mt-2 text-sm text-gray-500">
              Trang public và toàn bộ nội dung/ảnh AI đã tạo sẽ bị xóa vĩnh viễn. Dữ liệu sản phẩm không bị ảnh hưởng.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setConfirmDeleteId(null)}
                className="rounded-md px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100"
              >
                Hủy
              </button>
              <button
                type="button"
                disabled={busyId === confirmDeleteId}
                onClick={() => confirmDelete(confirmDeleteId)}
                className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              >
                {busyId === confirmDeleteId ? 'Đang xóa…' : 'Xóa vĩnh viễn'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
