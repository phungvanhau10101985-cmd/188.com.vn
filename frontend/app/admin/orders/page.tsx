// frontend/app/admin/orders/page.tsx - ADMIN ORDER MANAGEMENT (Tailwind only, no antd)
'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useSearchParams } from 'next/navigation';
import { adminOrderAPI, type AdminOrder, type AdminOrderStats, type AdminOrderStatsPreset, type PaymentRecord } from '@/lib/admin-api';
import AdminOrderDetailModal from '@/components/admin/AdminOrderDetailModal';
import { partialDepositAmount } from '@/lib/order-deposit';

const STATUS_TEXTS: Record<string, string> = {
  pending: 'Chờ xác nhận',
  waiting_deposit: 'Chờ đặt cọc',
  deposit_paid: 'Chờ gửi hàng',
  confirmed: 'Chờ gửi hàng',
  processing: 'Chờ gửi hàng',
  shipping: 'Chờ nhận hàng',
  delivered: 'Đã nhận hàng',
  completed: 'Đã đánh giá',
  returned: 'Đơn hoàn đã trả shop',
  cancelled: 'Đã hủy',
};

const PAYMENT_TEXTS: Record<string, string> = {
  pending: 'Chờ thanh toán',
  deposit_paid: 'Đã đặt cọc',
  paid: 'Đã thanh toán',
  failed: 'Thanh toán thất bại',
};

function formatDate(s: string) {
  const d = new Date(s);
  return d.toLocaleDateString('vi-VN') + ' ' + d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
}

function formatVnd(n: number | string) {
  const x = typeof n === 'string' ? parseFloat(n) : n;
  const v = Number.isFinite(x) ? x : 0;
  return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(v);
}

function formatVndDigits(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return '';
  return Math.round(n).toLocaleString('vi-VN');
}

function parseVndDigits(raw: string): number {
  const digits = String(raw || '').replace(/[^\d]/g, '');
  if (!digits) return 0;
  const n = parseInt(digits, 10);
  return Number.isFinite(n) ? n : 0;
}

/** Chuẩn hóa số tiền từ API (number, string, Decimal JSON). */
function parseMoney(value: unknown): number {
  if (value == null) return 0;
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0;
  const s = String(value).trim().replace(/\s/g, '').replace(/,/g, '');
  const x = parseFloat(s);
  return Number.isFinite(x) ? x : 0;
}

/** Đơn có nghiệp vụ đặt cọc (cờ đơn hoặc có dòng SP cọc — tránh cờ và dòng không khớp). */
function adminOrderExpectsDeposit(order: AdminOrder): boolean {
  if (order.requires_deposit) return true;
  return (order.items || []).some((i) => i.requires_deposit);
}

/**
 * Tiền cọc cần thu: ưu tiên deposit_amount; không suy luận nếu không xác định là đơn cần cọc
 * (tránh hiển thị sai khi chỉ sót số trong DB).
 */
function depositRequiredDisplay(order: AdminOrder): number {
  const stored = parseMoney(order.deposit_amount);
  if (stored > 0) return stored;
  if (!adminOrderExpectsDeposit(order)) return 0;
  const total = parseMoney(order.total_amount);
  const shipping = parseMoney(order.shipping_fee);
  const goods = Math.max(0, total - shipping);
  const pct = Number(order.deposit_percentage) || 0;
  if (pct >= 100 || order.deposit_type === 'percent_100') return total;
  if (pct > 0 && pct < 100) return partialDepositAmount(goods, pct);
  if (order.deposit_type === 'percent_30') return partialDepositAmount(goods, 30);
  if (order.status === 'waiting_deposit' && total > 0) return partialDepositAmount(goods, 30);
  return 0;
}

/**
 * Số tiền khách phải trả khi nhận hàng.
 * Đã cọc số bất kỳ → còn lại = tổng đơn − đã cọc (không theo %).
 * Chưa cọc: đơn không cọc = cả đơn; đơn cần cọc = tổng − số cần cọc (chỉ để xem trước).
 */
function amountDueOnDelivery(order: AdminOrder): number {
  const total = parseMoney(order.total_amount);
  const paidDeposit = parseMoney(order.deposit_paid);

  if (paidDeposit > 0) {
    return Math.max(0, Math.round(total - paidDeposit));
  }

  if (!adminOrderExpectsDeposit(order)) {
    const apiRemain = parseMoney(order.remaining_amount);
    if (apiRemain > 0) return Math.max(0, Math.round(apiRemain));
    return Math.max(0, Math.round(total));
  }

  return Math.max(0, Math.round(total - depositRequiredDisplay(order)));
}

type RevenueReportMode = 'day' | 'week' | 'month' | 'year' | 'range';

type RevenueFilterState = {
  date: string;
  dateFrom: string;
  dateTo: string;
  year: string;
  month: string;
  preset: AdminOrderStatsPreset | null;
};

const EMPTY_REVENUE_FILTER: RevenueFilterState = {
  date: '',
  dateFrom: '',
  dateTo: '',
  year: String(new Date().getFullYear()),
  month: '',
  preset: null,
};

const ADMIN_ORDERS_DEFAULT_PAGE_SIZE = 100;

function formatSharePercent(part: number, whole: number): string {
  if (whole <= 0) return '—';
  const value = Math.round((part * 1000) / whole) / 10;
  return Number.isInteger(value) ? `${value}%` : `${value.toFixed(1)}%`;
}

function DepositPercentStats({ report }: { report: AdminOrderStats }) {
  const deposited = report.deposited_orders ?? 0;
  const total = report.total_orders ?? 0;
  const rows = [...(report.deposit_percent_breakdown ?? [])].sort((a, b) => {
    if (a.percent === 0) return 1;
    if (b.percent === 0) return -1;
    return a.percent - b.percent;
  });

  return (
    <div className="mt-4 rounded-lg border border-blue-100 bg-blue-50/40 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
        <h3 className="text-sm font-semibold text-gray-900">Thống kê % đặt cọc</h3>
        <p className="text-sm text-gray-600">
          Tỷ lệ đơn đã cọc:{' '}
          <span className="font-semibold text-blue-700">{formatSharePercent(deposited, total)}</span>
          {total > 0 ? ` (${deposited}/${total} đơn)` : null}
        </p>
      </div>
      {rows.length === 0 ? (
        <p className="text-sm text-gray-500">Chưa có đơn đã đặt cọc trong kỳ này.</p>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          {rows.map((row) => (
            <div key={row.percent} className="rounded-lg border border-blue-100 bg-white p-3">
              <p className="text-gray-500 text-sm">{row.percent > 0 ? `Cọc ${row.percent}%` : 'Chưa rõ %'}</p>
              <p className="text-xl font-bold text-blue-700">{row.orders} đơn</p>
              <p className="text-xs text-gray-500 mt-1">{formatSharePercent(row.orders, deposited)} số đơn đã cọc</p>
              <p className="text-xs text-gray-600 mt-1">
                Doanh thu:{' '}
                <span className="font-medium text-gray-800">{formatVnd(Number(row.revenue))}</span>
              </p>
              <p className="text-xs text-gray-600">
                Tiền cọc: <span className="font-medium text-gray-800">{formatVnd(Number(row.amount))}</span>
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function resolveAdminOrderStatusParam(activeTab: string, statusFilter: string): string | undefined {
  const key = statusFilter || activeTab;
  if (!key || key === 'all') return undefined;
  if (key === 'waiting_ship') return 'deposit_paid,confirmed,processing';
  return key;
}

function todayIsoVn(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date());
}

/** Số ngày lịch (giờ VN) kể từ lúc khách đặt cọc. */
function daysSinceDepositStart(order: AdminOrder): number | null {
  const deposited =
    Number(order.deposit_paid || 0) > 0 ||
    !!order.deposit_paid_at ||
    order.payment_status === 'deposit_paid' ||
    order.status === 'deposit_paid';
  if (!deposited) return null;
  const iso = order.deposit_paid_at || order.created_at;
  if (!iso) return null;
  const start = new Date(iso);
  if (Number.isNaN(start.getTime())) return null;
  const startDay = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' }).format(start);
  const elapsed = Date.parse(`${todayIsoVn()}T00:00:00Z`) - Date.parse(`${startDay}T00:00:00Z`);
  if (!Number.isFinite(elapsed)) return null;
  return Math.max(0, Math.round(elapsed / 86_400_000));
}

function monthInputToDateRange(value: string): { from: string; to: string } | null {
  if (!/^\d{4}-\d{2}$/.test(value)) return null;
  const [year, month] = value.split('-').map(Number);
  const lastDay = new Date(year, month, 0).getDate();
  return {
    from: `${value}-01`,
    to: `${value}-${String(lastDay).padStart(2, '0')}`,
  };
}

export default function AdminOrdersPage() {
  const searchParams = useSearchParams();
  const [loading, setLoading] = useState(false);
  const [orders, setOrders] = useState<AdminOrder[]>([]);
  const [filteredTotal, setFilteredTotal] = useState(0);
  const [listPage, setListPage] = useState(1);
  const [listPageSize, setListPageSize] = useState(ADMIN_ORDERS_DEFAULT_PAGE_SIZE);
  const [statusCounts, setStatusCounts] = useState<any>(null); // Số đơn theo trạng thái (period=all) cho tab
  const [activeTab, setActiveTab] = useState('all');
  const [search, setSearch] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [paymentFilter, setPaymentFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [specialFilter, setSpecialFilter] = useState('');
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);
  const [selectedOrder, setSelectedOrder] = useState<AdminOrder | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [paymentOpen, setPaymentOpen] = useState(false);
  const [orderPayments, setOrderPayments] = useState<PaymentRecord[]>([]);
  const [paymentNote, setPaymentNote] = useState('');
  const [depositReceivedInput, setDepositReceivedInput] = useState('');
  const [confirmingDeposit, setConfirmingDeposit] = useState(false);
  const [loadingPayments, setLoadingPayments] = useState(false);
  const [consultSavingId, setConsultSavingId] = useState<number | null>(null);
  const [revenueMode, setRevenueMode] = useState<RevenueReportMode>('day');
  const [revenueFilter, setRevenueFilter] = useState<RevenueFilterState>(() => ({
    ...EMPTY_REVENUE_FILTER,
    date: todayIsoVn(),
    preset: 'today',
  }));
  const [revenueReport, setRevenueReport] = useState<AdminOrderStats | null>(null);
  const [revenueLoading, setRevenueLoading] = useState(false);
  const [revenueError, setRevenueError] = useState<string | null>(null);

  const showToast = (type: 'ok' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 3000);
  };

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    try {
      const skip = (listPage - 1) * listPageSize;
      const listKey = statusFilter || activeTab;
      const preset =
        specialFilter === 'china_no_deposit'
          ? 'china_no_deposit'
          : listKey === 'waiting_ship'
            ? 'deposited_no_ems'
            : undefined;
      const data = await adminOrderAPI.getAllOrders({
        status: preset ? undefined : resolveAdminOrderStatusParam(activeTab, statusFilter),
        payment_status: paymentFilter || undefined,
        fulfillment_source: (sourceFilter || undefined) as 'china' | 'vietnam' | undefined,
        preset,
        deposit_hold_overdue: specialFilter === 'deposit_hold_overdue' ? true : undefined,
        fulfillment_needs_review: specialFilter === 'source_review' ? true : undefined,
        q: appliedSearch || undefined,
        skip,
        limit: listPageSize,
      });
      const total = data.pagination?.filtered_total ?? data.items.length;
      const maxPage = Math.max(1, Math.ceil(total / listPageSize));
      if (total > 0 && listPage > maxPage) {
        setListPage(maxPage);
        return;
      }
      setOrders(data.items);
      setFilteredTotal(total);
    } catch {
      showToast('err', 'Lỗi tải đơn hàng');
    } finally {
      setLoading(false);
    }
  }, [activeTab, statusFilter, paymentFilter, sourceFilter, specialFilter, appliedSearch, listPage, listPageSize]);

  const fetchStats = useCallback(async () => {
    try {
      const allData = await adminOrderAPI.getStats('all');
      setStatusCounts(allData);
    } catch (e) {
      console.error(e);
    }
  }, []);

  const loadRevenueReport = useCallback(
    async (mode: RevenueReportMode = revenueMode, filter: RevenueFilterState = revenueFilter) => {
      setRevenueLoading(true);
      setRevenueError(null);
      try {
        let data: AdminOrderStats;
        if (mode === 'day') {
          if (filter.preset === 'today') {
            data = await adminOrderAPI.getStats({ preset: 'today' });
          } else if (filter.date) {
            data = await adminOrderAPI.getStats({ date: filter.date });
          } else {
            setRevenueError('Chọn ngày hoặc bấm «Hôm nay».');
            setRevenueLoading(false);
            return;
          }
        } else if (mode === 'week') {
          if (!filter.preset || (filter.preset !== 'this_week' && filter.preset !== 'last_week')) {
            setRevenueError('Chọn «Tuần này» hoặc «Tuần trước».');
            setRevenueLoading(false);
            return;
          }
          data = await adminOrderAPI.getStats({ preset: filter.preset });
        } else if (mode === 'month') {
          if (filter.preset === 'this_month' || filter.preset === 'last_month') {
            data = await adminOrderAPI.getStats({ preset: filter.preset });
          } else if (filter.month) {
            const range = monthInputToDateRange(filter.month);
            if (!range) {
              setRevenueError('Tháng không hợp lệ.');
              setRevenueLoading(false);
              return;
            }
            data = await adminOrderAPI.getStats({ date_from: range.from, date_to: range.to });
          } else {
            setRevenueError('Chọn tháng hoặc bấm «Tháng này» / «Tháng trước».');
            setRevenueLoading(false);
            return;
          }
        } else if (mode === 'year') {
          const y = Number(filter.year);
          if (!Number.isFinite(y) || y < 1970 || y > 2100) {
            setRevenueError('Năm không hợp lệ.');
            setRevenueLoading(false);
            return;
          }
          data = await adminOrderAPI.getStats({ year: y });
        } else {
          const from = filter.dateFrom.trim();
          const to = (filter.dateTo || filter.dateFrom).trim();
          if (!from) {
            setRevenueError('Chọn ít nhất ngày bắt đầu.');
            setRevenueLoading(false);
            return;
          }
          data = await adminOrderAPI.getStats({ date_from: from, date_to: to });
        }
        setRevenueReport(data);
      } catch (e) {
        setRevenueReport(null);
        setRevenueError(e instanceof Error ? e.message : 'Không tải được báo cáo doanh thu');
      } finally {
        setRevenueLoading(false);
      }
    },
    [revenueMode, revenueFilter],
  );

  useEffect(() => {
    fetchOrders();
    fetchStats();
  }, [fetchOrders, fetchStats]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setAppliedSearch(search.trim());
      setListPage(1);
    }, 400);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    setListPage(1);
  }, [activeTab, statusFilter, paymentFilter, sourceFilter, specialFilter, listPageSize]);

  useEffect(() => {
    void loadRevenueReport();
    // Chỉ lần đầu: mặc định ngày hôm nay. Đổi ngày gọi loadRevenueReport trực tiếp.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openDetailCode = searchParams.get('open') === '1' ? (searchParams.get('q') || '').trim() : '';
  const openedDetailRef = useRef('');

  useEffect(() => {
    const q = (searchParams.get('q') || searchParams.get('highlight') || '').trim();
    if (q) {
      setSearch(q);
      setAppliedSearch(q);
    }
  }, [searchParams]);

  useEffect(() => {
    if (!openDetailCode || loading) return;
    if (openedDetailRef.current === openDetailCode) return;
    const match = orders.find((order) => order.order_code.toLowerCase() === openDetailCode.toLowerCase());
    if (!match) return;
    openedDetailRef.current = openDetailCode;
    setSelectedOrder(match);
    setDetailOpen(true);
  }, [openDetailCode, loading, orders]);

  const totalPages = Math.max(1, Math.ceil(filteredTotal / listPageSize));
  const displayFrom = filteredTotal === 0 ? 0 : (listPage - 1) * listPageSize + 1;
  const displayTo = Math.min(listPage * listPageSize, filteredTotal);

  const openPaymentModal = async (order: AdminOrder) => {
    setSelectedOrder(order);
    setPaymentOpen(true);
    setOrderPayments([]);
    setPaymentNote('');
    setDepositReceivedInput(formatVndDigits(depositRequiredDisplay(order)));
    setConfirmingDeposit(false);
    setLoadingPayments(true);
    try {
      const payments = await adminOrderAPI.getOrderPayments(order.id);
      setOrderPayments(payments);
      const pending = payments.find((x) => x.payment_status === 'pending') || payments[0];
      const paidAmt = pending ? parseMoney(pending.amount) : 0;
      if (paidAmt > 0) {
        setDepositReceivedInput(formatVndDigits(paidAmt));
      }
    } catch {
      showToast('err', 'Không tải được danh sách thanh toán');
    } finally {
      setLoadingPayments(false);
    }
  };

  const readReceivedDepositAmount = (order: AdminOrder): number | null => {
    const received = parseVndDigits(depositReceivedInput);
    const total = Math.round(parseMoney(order.total_amount));
    if (received <= 0) {
      showToast('err', 'Nhập số tiền đã nhận cọc');
      return null;
    }
    if (received > total) {
      showToast('err', 'Số tiền đã nhận cọc không được lớn hơn tổng đơn');
      return null;
    }
    return received;
  };

  const depositConfirmToast = (
    confirmed: boolean,
    email?: { sent: boolean; to?: string | null; detail: string },
  ) => {
    if (!confirmed) return { type: 'ok' as const, msg: 'Đã từ chối cọc' };
    if (email?.sent) {
      return {
        type: 'ok' as const,
        msg: `Đã xác nhận cọc. Email đã gửi tới ${email.to || 'khách'}.`,
      };
    }
    return {
      type: 'err' as const,
      msg: `Đã xác nhận cọc nhưng chưa gửi email: ${email?.detail || 'Không rõ lý do'}`,
    };
  };

  const closePaymentModal = () => {
    setPaymentOpen(false);
    setOrderPayments([]);
    setPaymentNote('');
    setDepositReceivedInput('');
    setConfirmingDeposit(false);
  };

  const handleConfirmDeposit = async (orderId: number, paymentId: number, isConfirmed: boolean, note?: string) => {
    if (!selectedOrder) return;
    let received: number | undefined;
    if (isConfirmed) {
      const parsed = readReceivedDepositAmount(selectedOrder);
      if (parsed == null) return;
      received = parsed;
    }
    setConfirmingDeposit(true);
    try {
      const res = await adminOrderAPI.confirmDeposit(orderId, {
        payment_id: paymentId,
        is_confirmed: isConfirmed,
        confirmation_note: note || undefined,
        received_amount: received,
      });
      const t = depositConfirmToast(isConfirmed, res.deposit_email);
      showToast(t.type, t.msg);
      closePaymentModal();
      setSelectedOrder(null);
      fetchOrders();
      fetchStats();
      void loadRevenueReport();
    } catch (err: any) {
      showToast('err', err.message || 'Lỗi xác nhận cọc');
    } finally {
      setConfirmingDeposit(false);
    }
  };

  const handleConfirmDepositManual = async () => {
    if (!selectedOrder) return;
    const received = readReceivedDepositAmount(selectedOrder);
    if (received == null) return;
    setConfirmingDeposit(true);
    try {
      const res = await adminOrderAPI.confirmDepositManual(selectedOrder.id, {
        received_amount: received,
        confirmation_note: paymentNote || undefined,
      });
      const t = depositConfirmToast(true, res.deposit_email);
      showToast(t.type, t.msg);
      closePaymentModal();
      setSelectedOrder(null);
      fetchOrders();
      fetchStats();
      void loadRevenueReport();
    } catch (err: any) {
      showToast('err', err.message || 'Lỗi xác nhận cọc');
    } finally {
      setConfirmingDeposit(false);
    }
  };

  const handleConsultationToggle = async (order: AdminOrder, checked: boolean) => {
    setConsultSavingId(order.id);
    try {
      const updated = await adminOrderAPI.updateOrder(order.id, { staff_consultation_contacted: checked });
      const flag = !!updated.staff_consultation_contacted;
      setOrders((prev) => prev.map((o) => (o.id === order.id ? { ...o, staff_consultation_contacted: flag } : o)));
      setSelectedOrder((cur) => (cur?.id === order.id ? { ...cur, staff_consultation_contacted: flag } : cur));
      showToast('ok', checked ? 'Đã đánh dấu đã liên hệ tư vấn' : 'Đã bỏ đánh dấu');
    } catch (err: unknown) {
      showToast('err', err instanceof Error ? err.message : 'Không cập nhật được cờ tư vấn');
    } finally {
      setConsultSavingId(null);
    }
  };

  const tabs = [
    { key: 'all', label: 'Tất cả', countKey: 'total_orders' as const },
    { key: 'waiting_deposit', label: 'Chờ đặt cọc', countKey: 'waiting_deposit_orders' as const },
    { key: 'waiting_ship', label: 'Chờ gửi hàng', countKey: 'waiting_ship' as const },
    { key: 'shipping', label: 'Chờ nhận hàng', countKey: 'shipping_orders' as const },
    { key: 'delivered', label: 'Đã nhận hàng', countKey: 'delivered_orders' as const },
    { key: 'completed', label: 'Đã đánh giá', countKey: 'completed_orders' as const },
    { key: 'returned', label: 'Đơn hoàn đã trả shop', countKey: 'returned_orders' as const },
    { key: 'cancelled', label: 'Đã hủy', countKey: 'cancelled_orders' as const },
  ];

  const depositModalReceived = parseVndDigits(depositReceivedInput);
  const depositModalTotal = selectedOrder ? Math.round(parseMoney(selectedOrder.total_amount)) : 0;
  const depositModalRemaining = Math.max(0, depositModalTotal - depositModalReceived);
  const depositModalAmountInvalid =
    !selectedOrder || depositModalReceived <= 0 || depositModalReceived > depositModalTotal;

  return (
      <div className="p-6">
        {toast && (
          <div
            className={`fixed top-24 right-4 z-[100] max-w-[min(20rem,calc(100vw-2rem))] px-4 py-2 rounded-lg shadow-lg sm:right-6 ${
              toast.type === 'ok' ? 'bg-green-600 text-white' : 'bg-red-600 text-white'
            }`}
            role="status"
            aria-live="polite"
          >
            {toast.msg}
          </div>
        )}

        <div className="flex justify-between items-center mb-6">
          <div>
            <h1 className="text-2xl font-bold">Quản lý đơn hàng</h1>
            <p className="text-gray-600">Quản lý và xử lý đơn hàng, đặt cọc</p>
          </div>
          <button
            onClick={() => {
              fetchOrders();
              fetchStats();
              void loadRevenueReport();
            }}
            className="px-4 py-2 bg-[#ea580c] text-white rounded-lg hover:bg-[#c2410c]"
          >
            Làm mới
          </button>
        </div>

        <section className="bg-white rounded-lg shadow mb-6 overflow-hidden" aria-label="Báo cáo doanh thu">
          <div className="border-b px-4 py-3">
            <h2 className="text-lg font-semibold text-gray-900">Doanh thu</h2>
            <p className="text-sm text-gray-500 mt-0.5">
              Mặc định ngày hôm nay. Chọn ngày khác thì số liệu bên dưới đổi theo ngày đó.
            </p>
          </div>

          <div className="px-4 py-3 border-b flex flex-wrap gap-2">
            {(
              [
                ['day', 'Theo ngày'],
                ['week', 'Theo tuần'],
                ['month', 'Theo tháng'],
                ['year', 'Theo năm'],
                ['range', 'Khoảng ngày'],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => {
                  setRevenueMode(key);
                  setRevenueError(null);
                  if (key === 'day') {
                    const next = { ...EMPTY_REVENUE_FILTER, date: todayIsoVn(), preset: 'today' as const };
                    setRevenueFilter(next);
                    void loadRevenueReport('day', next);
                    return;
                  }
                  setRevenueFilter(EMPTY_REVENUE_FILTER);
                  setRevenueReport(null);
                }}
                className={`rounded-lg px-3 py-2 text-sm font-medium border ${
                  revenueMode === key
                    ? 'bg-[#ea580c] text-white border-[#ea580c]'
                    : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="px-4 py-3 flex flex-wrap items-end gap-3 bg-gray-50/80 border-b">
            {revenueMode === 'day' ? (
              <>
                <label className="text-sm text-gray-700">
                  Chọn ngày
                  <input
                    type="date"
                    value={revenueFilter.date}
                    onChange={(e) => {
                      const next = { ...EMPTY_REVENUE_FILTER, date: e.target.value, preset: null };
                      setRevenueFilter(next);
                      if (e.target.value) void loadRevenueReport('day', next);
                    }}
                    className="mt-1 block rounded-lg border border-gray-200 px-3 py-1.5 text-sm"
                  />
                </label>
                <button
                  type="button"
                  onClick={() => {
                    const next = { ...EMPTY_REVENUE_FILTER, date: todayIsoVn(), preset: 'today' as const };
                    setRevenueFilter(next);
                    void loadRevenueReport('day', next);
                  }}
                  disabled={revenueLoading}
                  className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                >
                  Hôm nay
                </button>
              </>
            ) : null}

            {revenueMode === 'week' ? (
              <>
                <button
                  type="button"
                  onClick={() => {
                    const next = { ...EMPTY_REVENUE_FILTER, preset: 'this_week' as const };
                    setRevenueFilter(next);
                    void loadRevenueReport('week', next);
                  }}
                  disabled={revenueLoading}
                  className={`rounded-lg px-3 py-2 text-sm font-medium border ${
                    revenueFilter.preset === 'this_week'
                      ? 'bg-emerald-600 text-white border-emerald-600'
                      : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
                  }`}
                >
                  Tuần này
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const next = { ...EMPTY_REVENUE_FILTER, preset: 'last_week' as const };
                    setRevenueFilter(next);
                    void loadRevenueReport('week', next);
                  }}
                  disabled={revenueLoading}
                  className={`rounded-lg px-3 py-2 text-sm font-medium border ${
                    revenueFilter.preset === 'last_week'
                      ? 'bg-emerald-600 text-white border-emerald-600'
                      : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
                  }`}
                >
                  Tuần trước
                </button>
              </>
            ) : null}

            {revenueMode === 'month' ? (
              <>
                <button
                  type="button"
                  onClick={() => {
                    const next = { ...EMPTY_REVENUE_FILTER, preset: 'this_month' as const };
                    setRevenueFilter(next);
                    void loadRevenueReport('month', next);
                  }}
                  disabled={revenueLoading}
                  className={`rounded-lg px-3 py-2 text-sm font-medium border ${
                    revenueFilter.preset === 'this_month'
                      ? 'bg-emerald-600 text-white border-emerald-600'
                      : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
                  }`}
                >
                  Tháng này
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const next = { ...EMPTY_REVENUE_FILTER, preset: 'last_month' as const };
                    setRevenueFilter(next);
                    void loadRevenueReport('month', next);
                  }}
                  disabled={revenueLoading}
                  className={`rounded-lg px-3 py-2 text-sm font-medium border ${
                    revenueFilter.preset === 'last_month'
                      ? 'bg-emerald-600 text-white border-emerald-600'
                      : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
                  }`}
                >
                  Tháng trước
                </button>
                <label className="text-sm text-gray-700">
                  Chọn tháng
                  <input
                    type="month"
                    value={revenueFilter.month}
                    onChange={(e) =>
                      setRevenueFilter({ ...EMPTY_REVENUE_FILTER, month: e.target.value, preset: null })
                    }
                    className="mt-1 block rounded-lg border border-gray-200 px-3 py-1.5 text-sm"
                  />
                </label>
                <button
                  type="button"
                  onClick={() => void loadRevenueReport('month', revenueFilter)}
                  disabled={revenueLoading || !revenueFilter.month}
                  className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                >
                  Xem tháng
                </button>
              </>
            ) : null}

            {revenueMode === 'year' ? (
              <>
                <label className="text-sm text-gray-700">
                  Năm
                  <input
                    type="number"
                    min={1970}
                    max={2100}
                    value={revenueFilter.year}
                    onChange={(e) =>
                      setRevenueFilter({ ...EMPTY_REVENUE_FILTER, year: e.target.value, preset: null })
                    }
                    className="mt-1 block w-28 rounded-lg border border-gray-200 px-3 py-1.5 text-sm"
                  />
                </label>
                <button
                  type="button"
                  onClick={() => void loadRevenueReport('year', revenueFilter)}
                  disabled={revenueLoading}
                  className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                >
                  Xem theo năm
                </button>
              </>
            ) : null}

            {revenueMode === 'range' ? (
              <>
                <label className="text-sm text-gray-700">
                  Từ ngày
                  <input
                    type="date"
                    value={revenueFilter.dateFrom}
                    onChange={(e) =>
                      setRevenueFilter((prev) => ({
                        ...prev,
                        dateFrom: e.target.value,
                        preset: null,
                      }))
                    }
                    className="mt-1 block rounded-lg border border-gray-200 px-3 py-1.5 text-sm"
                  />
                </label>
                <label className="text-sm text-gray-700">
                  Đến ngày
                  <input
                    type="date"
                    value={revenueFilter.dateTo}
                    onChange={(e) =>
                      setRevenueFilter((prev) => ({
                        ...prev,
                        dateTo: e.target.value,
                        preset: null,
                      }))
                    }
                    className="mt-1 block rounded-lg border border-gray-200 px-3 py-1.5 text-sm"
                  />
                </label>
                <button
                  type="button"
                  onClick={() => void loadRevenueReport('range', revenueFilter)}
                  disabled={revenueLoading || !revenueFilter.dateFrom}
                  className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                >
                  Xem khoảng ngày
                </button>
              </>
            ) : null}
          </div>

          <div className="p-4">
            {revenueError ? (
              <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {revenueError}
              </div>
            ) : null}
            {revenueLoading && !revenueReport ? (
              <p className="text-sm text-gray-500">Đang tải doanh thu…</p>
            ) : revenueReport ? (
              <div>
                <p className="text-sm text-gray-500 mb-3">
                  Đang xem:{' '}
                  <span className="font-semibold text-gray-900">{revenueReport.period_label || '—'}</span>
                  {revenueLoading ? <span className="ml-2 text-gray-400">Đang tải…</span> : null}
                </p>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                  <div className="rounded-lg border border-emerald-100 bg-emerald-50/40 p-4">
                    <p className="text-gray-500 text-sm">Doanh thu</p>
                    <p className="text-2xl font-bold text-green-600">
                      {formatVnd(Number(revenueReport.total_revenue))}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setActiveTab('all');
                      setStatusFilter('');
                      setPaymentFilter('');
                      setListPage(1);
                    }}
                    className="rounded-lg border border-gray-100 bg-white p-4 text-left hover:shadow-md transition-shadow"
                    title="Xem tất cả đơn hàng"
                  >
                    <p className="text-gray-500 text-sm">Tổng đơn hàng</p>
                    <p className="text-2xl font-bold text-gray-900">{revenueReport.total_orders}</p>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setActiveTab('waiting_deposit');
                      setStatusFilter('');
                      setPaymentFilter('');
                      setListPage(1);
                    }}
                    className="rounded-lg border border-orange-100 bg-orange-50/40 p-4 text-left hover:shadow-md transition-shadow"
                    title="Lọc đơn chờ đặt cọc"
                  >
                    <p className="text-gray-500 text-sm">Chờ đặt cọc</p>
                    <p className="text-2xl font-bold text-orange-600">{revenueReport.waiting_deposit_orders}</p>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setActiveTab('shipping');
                      setStatusFilter('');
                      setPaymentFilter('');
                      setListPage(1);
                    }}
                    className="rounded-lg border border-gray-100 bg-white p-4 text-left hover:shadow-md transition-shadow"
                    title="Lọc đơn đang giao hàng"
                  >
                    <p className="text-gray-500 text-sm">Đang giao hàng</p>
                    <p className="text-2xl font-bold text-gray-900">{revenueReport.shipping_orders}</p>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setActiveTab('all');
                      setStatusFilter('');
                      setPaymentFilter('deposit_paid');
                      setListPage(1);
                    }}
                    className="rounded-lg border border-blue-100 bg-blue-50/40 p-4 text-left hover:shadow-md transition-shadow"
                    title="Lọc đơn đã đặt cọc"
                  >
                    <p className="text-gray-500 text-sm">Số đơn đã cọc</p>
                    <p className="text-2xl font-bold text-blue-600">{revenueReport.deposited_orders ?? 0}</p>
                  </button>
                  <div className="rounded-lg border border-teal-100 bg-teal-50/40 p-4">
                    <p className="text-gray-500 text-sm">Doanh thu đơn đã cọc</p>
                    <p className="text-2xl font-bold text-emerald-600">
                      {formatVnd(Number(revenueReport.deposited_revenue ?? 0))}
                    </p>
                    {Number(revenueReport.deposited_amount ?? 0) > 0 && (
                      <p className="text-xs text-gray-500 mt-1">
                        Cọc đã thu:{' '}
                        <span className="font-medium text-gray-700">
                          {formatVnd(Number(revenueReport.deposited_amount))}
                        </span>
                      </p>
                    )}
                  </div>
                </div>
                <DepositPercentStats report={revenueReport} />
                <p className="text-sm text-gray-600 mt-3">
                  Doanh thu và tổng đơn đã trừ đơn đã hủy:{' '}
                  <span className="font-semibold text-gray-800">
                    {revenueReport.cancelled_orders} hủy · {revenueReport.returned_orders ?? 0} hoàn
                  </span>
                  . Đơn trùng (cùng số điện thoại, cùng sản phẩm, cùng tổng tiền) chỉ tính một lần;
                  nếu trong nhóm có đơn đã đặt cọc thì chỉ tính đơn đó.
                </p>
              </div>
            ) : !revenueError ? (
              <p className="text-sm text-gray-500">Chọn kỳ để xem doanh thu.</p>
            ) : null}
          </div>
        </section>

        <div className="bg-white rounded-lg shadow">
          <div className="border-b flex flex-wrap gap-2 p-2">
            {tabs.map((t) => (
              <button
                key={t.key}
                onClick={() => setActiveTab(t.key)}
                className={`px-3 py-2 rounded-lg text-sm font-medium ${
                  activeTab === t.key ? 'bg-[#ea580c] text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                {t.label} ({statusCounts != null ? (t.countKey === 'total_orders' ? (statusCounts.orders_including_cancelled ?? (statusCounts.total_orders ?? 0) + (statusCounts.cancelled_orders ?? 0)) : t.countKey === 'waiting_ship' ? (statusCounts.deposited_no_ems_orders ?? 0) : statusCounts[t.countKey] ?? 0) : '—'})
              </button>
            ))}
          </div>

          <div className="p-4 flex flex-wrap gap-3">
            <input
              type="text"
              placeholder="Tìm theo mã đơn, tên, SĐT..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="border rounded-lg px-3 py-2 w-64"
            />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="border rounded-lg px-3 py-2 w-40"
            >
              <option value="">Tất cả trạng thái</option>
              {tabs.slice(1).map((t) => (
                <option key={t.key} value={t.key}>
                  {t.label}
                </option>
              ))}
            </select>
            <select
              value={paymentFilter}
              onChange={(e) => setPaymentFilter(e.target.value)}
              className="border rounded-lg px-3 py-2 w-40"
            >
              <option value="">TT thanh toán</option>
              <option value="pending">Chờ thanh toán</option>
              <option value="deposit_paid">Đã đặt cọc</option>
              <option value="paid">Đã thanh toán</option>
              <option value="failed">Thanh toán thất bại</option>
            </select>
            <select
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value)}
              className="border rounded-lg px-3 py-2 w-44"
              aria-label="Lọc theo nguồn hàng"
            >
              <option value="">Tất cả nguồn hàng</option>
              <option value="vietnam">Có sẵn Việt Nam</option>
              <option value="china">Hàng Trung Quốc</option>
            </select>
            <select
              value={specialFilter}
              onChange={(e) => {
                const value = e.target.value;
                setSpecialFilter(value);
                if (value === 'china_no_deposit') {
                  setActiveTab('all');
                  setStatusFilter('');
                  setSourceFilter('china');
                }
              }}
              className="border rounded-lg px-3 py-2 w-48"
              aria-label="Lọc nghiệp vụ vận hành"
            >
              <option value="">Tất cả nghiệp vụ</option>
              <option value="china_no_deposit">TQ không cọc</option>
              <option value="deposit_hold_overdue">Quá hạn giữ tồn cọc</option>
              <option value="source_review">Cần rà soát nguồn</option>
            </select>
            <button
              onClick={() => {
                setSearch('');
                setAppliedSearch('');
                setStatusFilter('');
                setPaymentFilter('');
                setSourceFilter('');
                setSpecialFilter('');
                setListPage(1);
              }}
              className="px-3 py-2 border rounded-lg hover:bg-gray-50"
            >
              Xóa bộ lọc
            </button>
            <select
              value={listPageSize}
              onChange={(e) => setListPageSize(Number(e.target.value))}
              className="border rounded-lg px-3 py-2 w-36"
              aria-label="Số đơn mỗi trang"
            >
              <option value={25}>25 / trang</option>
              <option value={50}>50 / trang</option>
              <option value={100}>100 / trang</option>
            </select>
          </div>

          <div className="overflow-x-auto">
            {loading ? (
              <div className="p-8 text-center text-gray-500">Đang tải...</div>
            ) : (
              <table className="w-full text-left">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="p-3 font-medium">Mã đơn</th>
                    <th
                      className="p-3 font-medium text-center w-28"
                      title="Nhân viên chốt đơn đã liên hệ tư vấn khách"
                    >
                      Đã liên hệ tư vấn
                    </th>
                    <th className="p-3 font-medium">Khách hàng</th>
                    <th className="p-3 font-medium">Tổng tiền</th>
                    <th className="p-3 font-medium">Đặt cọc</th>
                    <th className="p-3 font-medium min-w-[8.5rem] max-w-[11rem] leading-snug align-bottom" title="COD khi nhận hàng sau khi đã trừ cọc (hoặc cả đơn nếu không cọc)">
                      Số tiền cần thanh toán khi nhận hàng
                    </th>
                    <th className="p-3 font-medium">Trạng thái</th>
                    <th className="p-3 font-medium whitespace-nowrap">Thanh toán</th>
                    <th className="p-3 font-medium">Ngày đặt</th>
                    <th className="p-3 font-medium">Thao tác</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((order) => {
                    const depositDays = daysSinceDepositStart(order);
                    return (
                    <tr key={order.id} className="border-b hover:bg-gray-50">
                      <td className="p-3 text-sm">
                        <div className="font-mono">{order.order_code}</div>
                        <span className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${
                          order.fulfillment_source === 'china'
                            ? 'bg-red-50 text-red-700'
                            : 'bg-emerald-50 text-emerald-700'
                        }`}>
                          {order.fulfillment_source === 'china' ? 'Trung Quốc' : 'Việt Nam'}
                        </span>
                      </td>
                      <td className="p-3 text-center">
                        <input
                          type="checkbox"
                          checked={!!order.staff_consultation_contacted}
                          disabled={consultSavingId === order.id}
                          onChange={(e) => void handleConsultationToggle(order, e.target.checked)}
                          className="h-4 w-4 rounded border-gray-300 text-[#ea580c] focus:ring-[#ea580c] cursor-pointer disabled:opacity-50"
                          title="Nhân viên chốt đơn đã liên hệ tư vấn khách"
                          aria-label={`Đã liên hệ tư vấn — đơn ${order.order_code}`}
                        />
                      </td>
                      <td className="p-3">
                        <div className="font-medium">{order.customer_name}</div>
                        <div className="text-gray-500 text-sm">{order.customer_phone}</div>
                      </td>
                      <td className="p-3 font-semibold">
                        <div>{formatVnd(order.total_amount)}</div>
                        {depositDays != null ? (
                          <div
                            className="mt-0.5 text-xs font-medium text-amber-700"
                            title="Số ngày kể từ ngày bắt đầu đặt cọc"
                          >
                            {depositDays} ngày
                          </div>
                        ) : null}
                      </td>
                      <td className="p-3 text-sm">
                        {depositRequiredDisplay(order) > 0 || adminOrderExpectsDeposit(order) ? (
                          <>
                            Cần: {formatVnd(depositRequiredDisplay(order))}
                            <br />
                            Đã cọc:{' '}
                            <span className={parseMoney(order.deposit_paid) > 0 ? 'font-semibold text-emerald-700' : 'text-gray-600'}>
                              {formatVnd(parseMoney(order.deposit_paid))}
                            </span>
                          </>
                        ) : (
                          <span className="text-green-600">Không cần cọc</span>
                        )}
                      </td>
                      <td className="p-3 text-sm whitespace-nowrap font-semibold tabular-nums text-gray-900">
                        {formatVnd(amountDueOnDelivery(order))}
                      </td>
                      <td className="p-3">
                        <span className="px-2 py-1 rounded text-sm bg-gray-100">
                          {STATUS_TEXTS[order.status] || order.status}
                        </span>
                        {order.status === 'waiting_deposit' &&
                        (order.deposit_hold_overdue ||
                          (order.stock_hold_expires_at &&
                            new Date(order.stock_hold_expires_at).getTime() < Date.now())) ? (
                          <span className="mt-1 block text-xs font-medium text-red-600">Giữ tồn đã quá hạn</span>
                        ) : null}
                        {order.fulfillment_needs_review ? (
                          <span className="mt-1 block text-xs font-medium text-amber-700">Cần rà soát nguồn</span>
                        ) : null}
                        {order.deposit_exception ? (
                          <span className="mt-1 block text-xs font-medium text-red-700" title={order.deposit_exception_note || undefined}>
                            Cọc đã nhận — thiếu tồn
                          </span>
                        ) : null}
                        {(order.sla_warnings || []).map((warning) => (
                          <span key={warning} className="mt-1 block text-xs font-medium text-orange-700">
                            {warning}
                          </span>
                        ))}
                      </td>
                      <td className="p-3">
                        <span
                          className={`px-2 py-1 rounded text-sm ${
                            order.payment_status === 'paid' ? 'bg-green-100 text-green-800' : 'bg-orange-100 text-orange-800'
                          }`}
                        >
                          {PAYMENT_TEXTS[order.payment_status] || order.payment_status}
                        </span>
                      </td>
                      <td className="p-3 text-sm text-gray-600">{formatDate(order.created_at)}</td>
                      <td className="p-3">
                        <div className="flex gap-2">
                          <button
                            onClick={() => {
                              setSelectedOrder(order);
                              setDetailOpen(true);
                            }}
                            className="text-blue-600 hover:underline text-sm"
                          >
                            Chi tiết
                          </button>
                          {order.status === 'waiting_deposit' && depositRequiredDisplay(order) > 0 && (
                            <button
                              onClick={() => openPaymentModal(order)}
                              className="px-2 py-1 bg-[#ea580c] text-white rounded text-sm hover:bg-[#c2410c]"
                            >
                              Xác nhận cọc
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
            {!loading && orders.length === 0 && (
              <div className="p-8 text-center text-gray-500">Không có đơn hàng nào.</div>
            )}
            {!loading && filteredTotal > 0 && (
              <div className="px-4 py-3 border-t border-gray-100 flex flex-wrap items-center justify-between gap-3 text-sm text-gray-600">
                <span>
                  Hiển thị {displayFrom}–{displayTo} / {filteredTotal} đơn · Trang {listPage} / {totalPages}
                  {appliedSearch ? ` · tra «${appliedSearch}»` : ''}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setListPage(1)}
                    disabled={listPage <= 1 || loading}
                    className="rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 hover:bg-gray-50 disabled:opacity-40"
                  >
                    Đầu
                  </button>
                  <button
                    type="button"
                    onClick={() => setListPage((p) => Math.max(1, p - 1))}
                    disabled={listPage <= 1 || loading}
                    className="rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 hover:bg-gray-50 disabled:opacity-40"
                  >
                    Trước
                  </button>
                  <button
                    type="button"
                    onClick={() => setListPage((p) => Math.min(totalPages, p + 1))}
                    disabled={listPage >= totalPages || loading}
                    className="rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 hover:bg-gray-50 disabled:opacity-40"
                  >
                    Sau
                  </button>
                  <button
                    type="button"
                    onClick={() => setListPage(totalPages)}
                    disabled={listPage >= totalPages || loading}
                    className="rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 hover:bg-gray-50 disabled:opacity-40"
                  >
                    Cuối
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {detailOpen && selectedOrder && (
          <AdminOrderDetailModal
            order={selectedOrder}
            onClose={() => setDetailOpen(false)}
            onOrderChange={(next) => {
              setSelectedOrder(next);
              setOrders((prev) => prev.map((o) => (o.id === next.id ? { ...o, ...next } : o)));
            }}
            onRefresh={() => {
              fetchOrders();
              fetchStats();
              void loadRevenueReport();
            }}
            onRequestDepositConfirm={(order) => {
              setDetailOpen(false);
              void openPaymentModal(order);
            }}
            notify={showToast}
          />
        )}

        {/* Modal xác nhận cọc */}
        {paymentOpen && selectedOrder && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
            onClick={() => {
              if (!confirmingDeposit) closePaymentModal();
            }}
          >
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="confirm-deposit-title"
              className="bg-white rounded-xl shadow-xl max-w-md w-full p-6"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 id="confirm-deposit-title" className="text-xl font-bold mb-4">Xác nhận đặt cọc</h2>
              <p className="mb-1">
                Đơn <strong>{selectedOrder.order_code}</strong>
              </p>
              <p className="text-sm text-gray-600 mb-3">
                Tổng đơn <strong className="text-gray-900 tabular-nums">{formatVnd(depositModalTotal)}</strong>
                {' · '}
                Cần cọc <strong className="text-red-600 tabular-nums">{formatVnd(depositRequiredDisplay(selectedOrder))}</strong>
              </p>
              {loadingPayments && <p className="text-gray-500 text-sm">Đang tải...</p>}
              {!loadingPayments && orderPayments.length === 0 && (
                <p className="text-amber-700 text-sm mb-3">Chưa có giao dịch cọc. Nhập số tiền khách đã chuyển rồi xác nhận.</p>
              )}
              {!loadingPayments && orderPayments.length > 0 && (
                <p className="text-sm text-gray-600 mb-3">Có {orderPayments.length} giao dịch chờ xác nhận.</p>
              )}
              <div className="mb-3">
                <label htmlFor="deposit-received-amount" className="block text-sm font-medium mb-1">
                  Số tiền đã nhận cọc <span className="text-red-600">*</span>
                </label>
                <input
                  id="deposit-received-amount"
                  type="text"
                  inputMode="numeric"
                  autoComplete="off"
                  required
                  disabled={confirmingDeposit}
                  autoFocus
                  value={depositReceivedInput}
                  onChange={(e) => setDepositReceivedInput(formatVndDigits(parseVndDigits(e.target.value)))}
                  onKeyDown={(e) => {
                    if (e.key !== 'Enter') return;
                    e.preventDefault();
                    if (confirmingDeposit || loadingPayments || depositModalAmountInvalid) return;
                    if (orderPayments.length === 0) {
                      void handleConfirmDepositManual();
                      return;
                    }
                    const p = orderPayments.find((x) => x.payment_status === 'pending') || orderPayments[0];
                    if (p) void handleConfirmDeposit(selectedOrder.id, p.id, true, paymentNote);
                  }}
                  placeholder="Ví dụ: 980.250"
                  className="w-full border rounded-lg px-3 py-2 tabular-nums"
                  aria-invalid={depositReceivedInput !== '' && depositModalAmountInvalid}
                />
                <button
                  type="button"
                  disabled={confirmingDeposit || depositRequiredDisplay(selectedOrder) <= 0}
                  onClick={() => setDepositReceivedInput(formatVndDigits(depositRequiredDisplay(selectedOrder)))}
                  className="mt-1.5 text-sm font-medium text-blue-700 hover:underline disabled:opacity-50"
                >
                  Điền số cần cọc ({formatVnd(depositRequiredDisplay(selectedOrder))})
                </button>
              </div>
              <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm">
                <div className="flex justify-between gap-3">
                  <span className="text-gray-700">Đã nhận cọc</span>
                  <span className="font-semibold tabular-nums text-emerald-700">{formatVnd(depositModalReceived)}</span>
                </div>
                <div className="flex justify-between gap-3 mt-1">
                  <span className="text-gray-800 font-medium">Cần thanh toán khi nhận hàng</span>
                  <span className="font-semibold tabular-nums text-red-700">{formatVnd(depositModalRemaining)}</span>
                </div>
                {depositReceivedInput !== '' && depositModalReceived > depositModalTotal ? (
                  <p className="mt-2 text-red-700">Số tiền đã nhận không được lớn hơn tổng đơn.</p>
                ) : null}
              </div>
              <div className="mb-4">
                <label htmlFor="deposit-confirm-note" className="block text-sm font-medium mb-1">Ghi chú</label>
                <textarea
                  id="deposit-confirm-note"
                  rows={3}
                  placeholder="Ghi chú (không bắt buộc)"
                  value={paymentNote}
                  disabled={confirmingDeposit}
                  onChange={(e) => setPaymentNote(e.target.value)}
                  className="w-full border rounded-lg px-3 py-2"
                />
              </div>
              <div className="flex flex-wrap gap-2 justify-end">
                <button
                  type="button"
                  disabled={confirmingDeposit}
                  onClick={closePaymentModal}
                  className="px-4 py-2 border rounded-lg hover:bg-gray-50 disabled:opacity-50"
                >
                  Hủy
                </button>
                {orderPayments.length === 0 ? (
                  <button
                    type="button"
                    disabled={confirmingDeposit || loadingPayments || depositModalAmountInvalid}
                    onClick={() => void handleConfirmDepositManual()}
                    className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
                  >
                    {confirmingDeposit ? 'Đang xác nhận…' : 'Xác nhận'}
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      disabled={confirmingDeposit || loadingPayments}
                      onClick={() => {
                        const p = orderPayments.find((x) => x.payment_status === 'pending') || orderPayments[0];
                        if (p) void handleConfirmDeposit(selectedOrder.id, p.id, false, paymentNote);
                      }}
                      className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
                    >
                      Từ chối cọc
                    </button>
                    <button
                      type="button"
                      disabled={confirmingDeposit || loadingPayments || depositModalAmountInvalid}
                      onClick={() => {
                        const p = orderPayments.find((x) => x.payment_status === 'pending') || orderPayments[0];
                        if (p) void handleConfirmDeposit(selectedOrder.id, p.id, true, paymentNote);
                      }}
                      className="px-4 py-2 bg-[#ea580c] text-white rounded-lg hover:bg-[#c2410c] disabled:opacity-50"
                    >
                      {confirmingDeposit ? 'Đang xác nhận…' : 'Xác nhận'}
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
  );
}
