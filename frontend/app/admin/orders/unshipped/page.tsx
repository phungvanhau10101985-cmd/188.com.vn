'use client';

import { useCallback, useEffect, useState } from 'react';
import AdminOrderDetailModal from '@/components/admin/AdminOrderDetailModal';
import { adminOrderAPI, type AdminOrder, type DepositedNoEmsReceivable } from '@/lib/admin-api';

const PAGE_SIZE = 25;

type DepositPeriod = 'all' | 'today' | 'this_week' | 'last_week' | 'this_month' | 'last_month';

const PERIOD_OPTIONS: { key: DepositPeriod; label: string }[] = [
  { key: 'all', label: 'Tất cả' },
  { key: 'today', label: 'Hôm nay' },
  { key: 'this_week', label: 'Tuần này' },
  { key: 'last_week', label: 'Tuần trước' },
  { key: 'this_month', label: 'Tháng này' },
  { key: 'last_month', label: 'Tháng trước' },
];

function formatVnd(n: number | string) {
  const x = typeof n === 'string' ? parseFloat(n) : n;
  const v = Number.isFinite(x) ? x : 0;
  return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(v);
}

function daysSinceDeposit(order: AdminOrder): number | null {
  const iso = order.deposit_paid_at || order.created_at;
  if (!iso) return null;
  const start = new Date(iso);
  if (Number.isNaN(start.getTime())) return null;
  const dayKey = (d: Date) =>
    new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' }).format(d);
  const elapsed = Date.parse(`${dayKey(new Date())}T00:00:00Z`) - Date.parse(`${dayKey(start)}T00:00:00Z`);
  if (!Number.isFinite(elapsed)) return null;
  return Math.max(0, Math.round(elapsed / 86_400_000));
}

function amountDue(order: AdminOrder): number {
  return Math.max(0, Math.round(Number(order.total_amount || 0) - Number(order.deposit_paid || 0)));
}

function productLine(order: AdminOrder): string {
  const items = order.items || [];
  const name = (items[0]?.product_name || '').trim();
  if (!name) return 'Chưa có tên sản phẩm';
  if (items.length <= 1) return name;
  return `${name} (+${items.length - 1})`;
}

export default function UnshippedReceivablePage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [orders, setOrders] = useState<AdminOrder[]>([]);
  const [receivable, setReceivable] = useState<DepositedNoEmsReceivable | null>(null);
  const [filteredTotal, setFilteredTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [period, setPeriod] = useState<DepositPeriod>('all');
  const [detailOrder, setDetailOrder] = useState<AdminOrder | null>(null);
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);

  const notify = (type: 'ok' | 'err', msg: string) => {
    setToast({ type, msg });
    window.setTimeout(() => setToast(null), 3000);
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await adminOrderAPI.getAllOrders({
        preset: 'deposited_no_ems',
        deposit_preset: period === 'all' ? undefined : period,
        q: appliedSearch || undefined,
        skip: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
      });
      const total = data.pagination?.filtered_total ?? data.items.length;
      const maxPage = Math.max(1, Math.ceil(total / PAGE_SIZE));
      if (total > 0 && page > maxPage) {
        setPage(maxPage);
        return;
      }
      setOrders(data.items);
      setFilteredTotal(total);
      setReceivable(data.receivable ?? null);
    } catch (err: unknown) {
      setOrders([]);
      setReceivable(null);
      setError(err instanceof Error ? err.message : 'Không tải được danh sách đơn chưa gửi');
    } finally {
      setLoading(false);
    }
  }, [appliedSearch, page, period]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setAppliedSearch(search.trim());
      setPage(1);
    }, 400);
    return () => window.clearTimeout(timer);
  }, [search]);

  const totalPages = Math.max(1, Math.ceil(filteredTotal / PAGE_SIZE));
  const displayFrom = filteredTotal === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const displayTo = Math.min(page * PAGE_SIZE, filteredTotal);

  return (
    <div className="mx-auto max-w-3xl p-4 sm:p-6">
      {toast ? (
        <div
          className={`fixed top-24 right-4 z-[100] max-w-[min(20rem,calc(100vw-2rem))] rounded-lg px-4 py-2 shadow-lg sm:right-6 ${
            toast.type === 'ok' ? 'bg-green-600 text-white' : 'bg-red-600 text-white'
          }`}
          role="status"
          aria-live="polite"
        >
          {toast.msg}
        </div>
      ) : null}
      <div className="mb-4">
        <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">Cần thu chưa gửi</h1>
        <p className="mt-1 text-sm text-gray-600">
          Đơn khách đã cọc, chưa có mã vận chuyển EMS. Đơn chờ lâu nhất xếp trên.
        </p>
      </div>

      <section className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-4 sm:px-5" aria-label="Tổng tiền cần thu">
        <p className="text-sm font-medium text-amber-900">Tổng tiền cần thu chưa gửi</p>
        <p className="mt-1 text-2xl font-bold tabular-nums text-amber-950 sm:text-3xl">
          {receivable ? formatVnd(receivable.amount_due) : loading ? '…' : formatVnd(0)}
        </p>
        <p className="mt-2 text-sm text-amber-900/80">
          {receivable ? `${receivable.order_count} đơn` : '—'}
          {receivable ? ` · Đã thu cọc ${formatVnd(receivable.deposit_collected)}` : ''}
          {receivable ? ` · Tổng đơn ${formatVnd(receivable.order_total)}` : ''}
        </p>
        <p className="mt-1 text-xs text-amber-800/70">
          Phần còn lại sau khi trừ tiền cọc, thu khi giao hàng. Kỳ thống kê tính theo ngày bắt đầu đặt cọc.
        </p>
      </section>

      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6" role="group" aria-label="Thống kê theo kỳ">
        {PERIOD_OPTIONS.map((option) => {
          const stat =
            option.key === 'all'
              ? receivable
              : receivable?.periods?.find((row) => row.key === option.key);
          const selected = period === option.key;
          return (
            <button
              key={option.key}
              type="button"
              onClick={() => {
                setPeriod(option.key);
                setPage(1);
              }}
              aria-pressed={selected}
              className={`rounded-xl border px-3 py-2.5 text-left transition-colors ${
                selected
                  ? 'border-[#ea580c] bg-orange-50 ring-1 ring-[#ea580c]'
                  : 'border-gray-200 bg-white hover:bg-gray-50'
              }`}
            >
              <p className="text-xs font-medium text-gray-500">{option.label}</p>
              <p className="mt-1 text-sm font-bold tabular-nums text-gray-900">
                {stat ? formatVnd(stat.amount_due) : '—'}
              </p>
              <p className="mt-0.5 text-[11px] text-gray-500">{stat ? `${stat.order_count} đơn` : '—'}</p>
            </button>
          );
        })}
      </div>

      <div className="mt-4">
        <label htmlFor="unshipped-search" className="sr-only">
          Tìm đơn chưa gửi
        </label>
        <input
          id="unshipped-search"
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Tìm mã đơn, tên, số điện thoại"
          className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm"
        />
      </div>

      <section className="mt-4" aria-label="Danh sách đơn chưa gửi">
        <div className="mb-2 flex items-baseline justify-between gap-3">
          <h2 className="text-sm font-semibold text-gray-800">
            Danh sách đơn
            {period !== 'all'
              ? ` · ${PERIOD_OPTIONS.find((option) => option.key === period)?.label}`
              : ''}
          </h2>
          <button
            type="button"
            onClick={() => void load()}
            className="text-sm font-medium text-[#ea580c] hover:underline"
          >
            Làm mới
          </button>
        </div>

        {error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}{' '}
            <button type="button" onClick={() => void load()} className="font-medium underline">
              Thử lại
            </button>
          </div>
        ) : null}

        {loading ? (
          <p className="rounded-lg border border-gray-200 bg-white px-4 py-8 text-center text-sm text-gray-500">
            Đang tải danh sách…
          </p>
        ) : null}

        {!loading && !error && orders.length === 0 ? (
          <p className="rounded-lg border border-dashed border-gray-300 bg-white px-4 py-8 text-center text-sm text-gray-500">
            {appliedSearch
              ? 'Không có đơn khớp từ khóa.'
              : period === 'all'
                ? 'Không có đơn đã cọc nào đang chờ gửi.'
                : 'Không có đơn đặt cọc trong kỳ này.'}
          </p>
        ) : null}

        {!loading && !error && orders.length > 0 ? (
          <ul className="divide-y divide-gray-200 overflow-hidden rounded-xl border border-gray-200 bg-white">
            {orders.map((order) => {
              const days = daysSinceDeposit(order);
              return (
                <li key={order.id} className="px-3 py-3 sm:px-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-sm font-semibold text-gray-900">{order.order_code}</span>
                        <span
                          className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                            order.fulfillment_source === 'china'
                              ? 'bg-red-50 text-red-700'
                              : 'bg-emerald-50 text-emerald-700'
                          }`}
                        >
                          {order.fulfillment_source === 'china' ? 'Trung Quốc' : 'Việt Nam'}
                        </span>
                        {days != null ? (
                          <span className="text-xs font-medium text-amber-700" title="Số ngày kể từ ngày bắt đầu đặt cọc">
                            {days} ngày
                          </span>
                        ) : null}
                      </div>
                      <p className="mt-1 truncate text-sm text-gray-800">
                        {order.customer_name}
                        <span className="text-gray-500"> · {order.customer_phone}</span>
                      </p>
                      <p className="mt-0.5 truncate text-xs text-gray-500">{productLine(order)}</p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="text-sm font-semibold tabular-nums text-gray-900">{formatVnd(amountDue(order))}</p>
                      <p className="mt-0.5 text-[11px] text-gray-500">Cần thu</p>
                      <p className="mt-1 text-[11px] tabular-nums text-gray-400">{formatVnd(order.total_amount)}</p>
                    </div>
                  </div>
                  <div className="mt-2 flex justify-end">
                    <button
                      type="button"
                      onClick={() => setDetailOrder(order)}
                      className="inline-flex min-h-[36px] items-center rounded-lg border border-[#ea580c] px-3 py-1.5 text-xs font-semibold text-[#ea580c] hover:bg-orange-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#ea580c]"
                    >
                      Xem chi tiết
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        ) : null}

        {!loading && filteredTotal > 0 ? (
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm text-gray-600">
            <span>
              {displayFrom}–{displayTo} / {filteredTotal}
              {appliedSearch ? ` · «${appliedSearch}»` : ''}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1 || loading}
                className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 hover:bg-gray-50 disabled:opacity-40"
              >
                Trước
              </button>
              <span className="self-center tabular-nums">
                {page}/{totalPages}
              </span>
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages || loading}
                className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 hover:bg-gray-50 disabled:opacity-40"
              >
                Sau
              </button>
            </div>
          </div>
        ) : null}
      </section>

      {detailOrder ? (
        <AdminOrderDetailModal
          order={detailOrder}
          onClose={() => setDetailOrder(null)}
          onOrderChange={(next) => {
            setDetailOrder(next);
            setOrders((prev) => prev.map((row) => (row.id === next.id ? { ...row, ...next } : row)));
          }}
          onRefresh={() => void load()}
          notify={notify}
        />
      ) : null}
    </div>
  );
}
