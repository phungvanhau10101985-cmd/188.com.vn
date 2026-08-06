'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { ladipageAdminAPI, type Ladipage, type LadipageAdminStats } from '@/lib/admin-api';
import { useToast } from '@/components/ToastProvider';
import type { LadipageListKind } from '@/components/ladipage/ladipage-admin-kinds';

const PAGE_SIZE = 20;

const STATUS_LABEL: Record<string, string> = {
  draft: 'Nháp',
  published: 'Đã đăng',
};

function sourceDetail(item: Ladipage, kind: LadipageListKind): string {
  if (kind === 'category') {
    return item.category_name ? item.category_name : 'Danh mục cấp 3';
  }
  if (kind === 'product_single') {
    return 'Gắn PDP sản phẩm';
  }
  const n = item.product_ids?.length ?? 0;
  return n > 0 ? `${n} sản phẩm` : 'Chưa chọn SP';
}

function formatDate(raw?: string | null): string {
  if (!raw) return '—';
  try {
    return new Date(raw).toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'short' });
  } catch {
    return raw;
  }
}

function formatCount(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '—';
  return n.toLocaleString('vi-VN');
}

function LadipageStatsCards({ kind, stats }: { kind: LadipageListKind; stats: LadipageAdminStats | null }) {
  if (!stats) return null;

  if (kind === 'product_single') {
    const total = stats.active_products_total ?? 0;
    const withLp = stats.products_with_ladipage ?? 0;
    const published = stats.products_with_published_ladipage ?? 0;
    const without = stats.products_without_ladipage ?? Math.max(0, total - withLp);
    const pct = total > 0 ? Math.min(100, Math.round((withLp / total) * 1000) / 10) : 0;

    return (
      <div className="mb-4 space-y-3">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="Sản phẩm đang bán" value={formatCount(total)} />
          <StatCard label="Đã có ladipage" value={formatCount(withLp)} hint={`${pct}% catalog`} accent="orange" />
          <StatCard label="Đã đăng (published)" value={formatCount(published)} accent="emerald" />
          <StatCard label="Chưa có ladipage" value={formatCount(without)} />
        </div>
        {total > 0 && (
          <div>
            <div className="mb-1 flex justify-between text-xs text-gray-500">
              <span>Tỷ lệ coverage</span>
              <span>{pct}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-gray-100">
              <div
                className="h-full rounded-full bg-orange-500 transition-all"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        )}
      </div>
    );
  }

  if (kind === 'category') {
    const total = stats.category_l3_total ?? 0;
    const withLp = stats.categories_with_ladipage ?? 0;
    const without = stats.categories_without_ladipage ?? Math.max(0, total - withLp);
    const pct = total > 0 ? Math.min(100, Math.round((withLp / total) * 1000) / 10) : 0;

    return (
      <div className="mb-4 space-y-3">
        <div className="grid gap-3 sm:grid-cols-3">
          <StatCard label="Danh mục cấp 3" value={formatCount(total)} />
          <StatCard label="Đã có ladipage" value={formatCount(withLp)} hint={`${pct}%`} accent="orange" />
          <StatCard label="Chưa có ladipage" value={formatCount(without)} />
        </div>
      </div>
    );
  }

  return (
    <div className="mb-4 grid gap-3 sm:grid-cols-2">
      <StatCard label="Trang ladipage nhiều SP" value={formatCount(stats.ladipage_pages_total)} />
      <StatCard
        label="Sản phẩm trong các trang này"
        value={formatCount(stats.products_in_multi_ladipages)}
        hint="unique"
      />
    </div>
  );
}

function StatCard({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: string;
  hint?: string;
  accent?: 'orange' | 'emerald';
}) {
  const valueClass =
    accent === 'orange'
      ? 'text-orange-600'
      : accent === 'emerald'
        ? 'text-emerald-600'
        : 'text-gray-900';

  return (
    <div className="rounded-xl border border-gray-100 bg-white px-4 py-3 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</p>
      <p className={`mt-1 text-2xl font-bold tabular-nums ${valueClass}`}>{value}</p>
      {hint ? <p className="mt-0.5 text-xs text-gray-400">{hint}</p> : null}
    </div>
  );
}

interface AdminLadipageListPanelProps {
  kind: LadipageListKind;
  kindLabel: string;
  kindDescription: string;
  emptyHint: string;
  newHref?: string;
}

export default function AdminLadipageListPanel({
  kind,
  kindLabel,
  kindDescription,
  emptyHint,
  newHref = '/admin/ladipage/new',
}: AdminLadipageListPanelProps) {
  const router = useRouter();
  const pathname = usePathname() || '';
  const searchParams = useSearchParams();
  const { pushToast } = useToast();

  const pageFromUrl = Math.max(1, parseInt(searchParams.get('page') || '1', 10) || 1);
  const [page, setPage] = useState(pageFromUrl);
  const [items, setItems] = useState<Ladipage[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<LadipageAdminStats | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState<number | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

  useEffect(() => {
    setPage(pageFromUrl);
  }, [pageFromUrl]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const load = useCallback(async () => {
    setStatus('loading');
    setError('');
    try {
      const [res, statsRes] = await Promise.all([
        ladipageAdminAPI.list({
          kind,
          skip: (page - 1) * PAGE_SIZE,
          limit: PAGE_SIZE,
        }),
        ladipageAdminAPI.stats(kind).catch(() => null),
      ]);
      setItems(res.items);
      setTotal(res.total);
      setStats(statsRes);
      setStatus('ready');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không tải được danh sách');
      setStatus('error');
    }
  }, [kind, page]);

  useEffect(() => {
    load();
  }, [load]);

  const goToPage = (nextPage: number) => {
    const clamped = Math.min(Math.max(1, nextPage), totalPages);
    const params = new URLSearchParams(searchParams.toString());
    if (clamped <= 1) params.delete('page');
    else params.set('page', String(clamped));
    const qs = params.toString();
    router.push(`${pathname}${qs ? `?${qs}` : ''}`);
  };

  const togglePublish = async (item: Ladipage) => {
    setBusyId(item.id);
    try {
      if (item.status === 'published') {
        await ladipageAdminAPI.unpublish(item.id);
        pushToast({ title: 'Đã chuyển về nháp', variant: 'success', durationMs: 2500 });
      } else {
        await ladipageAdminAPI.publish(item.id);
        pushToast({
          title: 'Đã đăng trang',
          description: `Xem tại ${item.public_url || `/lp/${item.slug}`}`,
          variant: 'success',
          durationMs: 3500,
        });
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
      if (items.length === 1 && page > 1) goToPage(page - 1);
      else await load();
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
    <>
      <div className="mb-4 rounded-xl border border-gray-100 bg-white px-4 py-3 shadow-sm">
        <h2 className="text-base font-semibold text-gray-900">{kindLabel}</h2>
        <p className="mt-1 text-sm text-gray-500">{kindDescription}</p>
        {status === 'ready' && (
          <p className="mt-2 text-xs text-gray-400">
            {total.toLocaleString('vi-VN')} ladipage trong danh sách · trang {page}/{totalPages}
          </p>
        )}
      </div>

      {(status === 'loading' || stats) && (
        <>
          {status === 'loading' && !stats ? (
            <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-20 animate-pulse rounded-xl bg-gray-100" />
              ))}
            </div>
          ) : (
            <LadipageStatsCards kind={kind} stats={stats} />
          )}
        </>
      )}

      {status === 'loading' && (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
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
          <p className="text-gray-500">{emptyHint}</p>
          <Link
            href={newHref}
            className="mt-3 inline-flex items-center rounded-full bg-orange-600 px-5 py-2 text-sm font-semibold text-white shadow hover:bg-orange-700"
          >
            Tạo ladipage {kindLabel.toLowerCase()}
          </Link>
        </div>
      )}

      {status === 'ready' && items.length > 0 && (
        <>
          <div className="overflow-x-auto rounded-xl border border-gray-100 bg-white shadow-sm">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="border-b border-gray-100 bg-gray-50 text-xs uppercase text-gray-500">
                <tr>
                  <th className="px-4 py-3">Tiêu đề</th>
                  <th className="px-4 py-3">Chi tiết</th>
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
                    <td className="px-4 py-3 text-gray-600">{sourceDetail(item, kind)}</td>
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

          {totalPages > 1 && (
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-gray-500">
                Hiển thị {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} / {total}
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={page <= 1}
                  onClick={() => goToPage(page - 1)}
                  className="rounded-md border border-gray-200 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-40"
                >
                  ← Trước
                </button>
                <button
                  type="button"
                  disabled={page >= totalPages}
                  onClick={() => goToPage(page + 1)}
                  className="rounded-md border border-gray-200 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-40"
                >
                  Sau →
                </button>
              </div>
            </div>
          )}
        </>
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
    </>
  );
}
