// frontend/app/admin/orders/page.tsx - ADMIN ORDER MANAGEMENT (Tailwind only, no antd)
'use client';

import { useState, useEffect, useCallback } from 'react';
import { adminOrderAPI, type AdminOrder, type PaymentRecord } from '@/lib/admin-api';
import { cdnUrl, normalizeRemoteImageUrlForDisplay } from '@/lib/cdn-url';

const STATUS_TEXTS: Record<string, string> = {
  pending: 'Chờ xác nhận',
  waiting_deposit: 'Chờ đặt cọc',
  deposit_paid: 'Chờ gửi hàng',
  confirmed: 'Chờ gửi hàng',
  processing: 'Chờ gửi hàng',
  shipping: 'Chờ nhận hàng',
  delivered: 'Đã nhận hàng',
  completed: 'Đã đánh giá',
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
  if (order.deposit_percentage === 100) return total;
  if (order.deposit_percentage === 30) return Math.round(total * 0.3);
  if (order.deposit_type === 'percent_100') return total;
  if (order.deposit_type === 'percent_30') return Math.round(total * 0.3);
  if (order.status === 'waiting_deposit' && total > 0) return Math.round(total * 0.3);
  return 0;
}

/**
 * Số tiền khách phải trả khi nhận hàng (COD sau cọc / khi không cọc là cả đơn).
 */
function amountDueOnDelivery(order: AdminOrder): number {
  const total = parseMoney(order.total_amount);
  const paidDeposit = parseMoney(order.deposit_paid);
  const apiRemain = parseMoney(order.remaining_amount);
  const needDeposit = depositRequiredDisplay(order);

  if (!adminOrderExpectsDeposit(order)) {
    if (apiRemain > 0) return Math.max(0, Math.round(apiRemain));
    return Math.max(0, Math.round(total));
  }

  if (paidDeposit <= 0) {
    return Math.max(0, Math.round(total - needDeposit));
  }

  if (apiRemain > 0 || paidDeposit >= needDeposit || order.status !== 'waiting_deposit') {
    const r = apiRemain > 0 ? apiRemain : total - paidDeposit;
    return Math.max(0, Math.round(r));
  }

  return Math.max(0, Math.round(total - paidDeposit));
}

/** Link SP public: ưu tiên NEXT_PUBLIC_SITE_URL để admin localhost vẫn mở đúng shop. */
function shopOrigin(): string {
  const env = process.env.NEXT_PUBLIC_SITE_URL?.trim().replace(/\/$/, '');
  if (env) return env;
  if (typeof window !== 'undefined') return window.location.origin;
  return 'https://188.com.vn';
}

function orderItemImageUrl(src: string | null | undefined): string {
  if (!src?.trim()) return cdnUrl('/images/placeholder-product.jpg');
  const s = normalizeRemoteImageUrlForDisplay(src);
  if (/^https?:\/\//i.test(s)) return s;
  return cdnUrl(s.startsWith('/') ? s : `/${s}`);
}

function productPublicUrl(slug: string | null | undefined): string | null {
  if (!slug?.trim()) return null;
  return `${shopOrigin()}/products/${encodeURIComponent(slug.trim())}`;
}

function colorDisplay(item: {
  selected_color_name?: string | null;
  selected_color?: string | null;
}): string | null {
  const name = item.selected_color_name?.trim();
  const code = item.selected_color?.trim();
  if (name && code && name !== code) return `${name} (${code})`;
  return name || code || null;
}

export default function AdminOrdersPage() {
  const [loading, setLoading] = useState(false);
  const [orders, setOrders] = useState<AdminOrder[]>([]);
  const [filteredOrders, setFilteredOrders] = useState<AdminOrder[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [statusCounts, setStatusCounts] = useState<any>(null); // Số đơn theo trạng thái (period=all) cho tab
  const [activeTab, setActiveTab] = useState('all');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [paymentFilter, setPaymentFilter] = useState('');
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);
  const [selectedOrder, setSelectedOrder] = useState<AdminOrder | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [paymentOpen, setPaymentOpen] = useState(false);
  const [orderPayments, setOrderPayments] = useState<PaymentRecord[]>([]);
  const [paymentNote, setPaymentNote] = useState('');
  const [loadingPayments, setLoadingPayments] = useState(false);
  const [consultSavingId, setConsultSavingId] = useState<number | null>(null);

  const showToast = (type: 'ok' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 3000);
  };

  const copyCustomerAddress = async (address: string | undefined | null) => {
    const text = address?.trim();
    if (!text) {
      showToast('err', 'Không có địa chỉ để sao chép');
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      showToast('ok', 'Đã sao chép địa chỉ');
    } catch {
      showToast('err', 'Không sao chép được — kiểm tra quyền trình duyệt');
    }
  };

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    try {
      let statusParam: string | undefined;
      if (activeTab === 'all') statusParam = undefined;
      else if (activeTab === 'waiting_ship') statusParam = 'deposit_paid,confirmed,processing';
      else statusParam = activeTab;
      const data = await adminOrderAPI.getAllOrders({
        status: statusParam,
        limit: 100,
      });
      setOrders(data);
      setFilteredOrders(data);
    } catch {
      showToast('err', 'Lỗi tải đơn hàng');
    } finally {
      setLoading(false);
    }
  }, [activeTab]);

  const fetchStats = useCallback(async () => {
    try {
      const [todayData, allData] = await Promise.all([
        adminOrderAPI.getStats('today'),
        adminOrderAPI.getStats('all'),
      ]);
      setStats(todayData);
      setStatusCounts(allData); // Dùng số đơn toàn bộ cho tab
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => {
    fetchOrders();
    fetchStats();
  }, [fetchOrders, fetchStats]);

  useEffect(() => {
    let result = orders;
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        (o) =>
          o.order_code.toLowerCase().includes(q) ||
          o.customer_name.toLowerCase().includes(q) ||
          o.customer_phone.includes(q)
      );
    }
    if (statusFilter) {
      if (statusFilter === 'waiting_ship') {
        result = result.filter((o) => ['deposit_paid', 'confirmed', 'processing'].includes(o.status));
      } else {
        result = result.filter((o) => o.status === statusFilter);
      }
    }
    if (paymentFilter) result = result.filter((o) => o.payment_status === paymentFilter);
    setFilteredOrders(result);
  }, [orders, search, statusFilter, paymentFilter]);

  const openPaymentModal = async (order: AdminOrder) => {
    setSelectedOrder(order);
    setPaymentOpen(true);
    setOrderPayments([]);
    setPaymentNote('');
    setLoadingPayments(true);
    try {
      const payments = await adminOrderAPI.getOrderPayments(order.id);
      setOrderPayments(payments);
    } catch {
      showToast('err', 'Không tải được danh sách thanh toán');
    } finally {
      setLoadingPayments(false);
    }
  };

  const handleConfirmDeposit = async (orderId: number, paymentId: number, isConfirmed: boolean, note?: string) => {
    try {
      await adminOrderAPI.confirmDeposit(orderId, {
        payment_id: paymentId,
        is_confirmed: isConfirmed,
        confirmation_note: note || undefined,
      });
      showToast('ok', isConfirmed ? 'Đã xác nhận cọc' : 'Đã từ chối cọc');
      setPaymentOpen(false);
      setSelectedOrder(null);
      setOrderPayments([]);
      setPaymentNote('');
      fetchOrders();
      fetchStats();
    } catch (err: any) {
      showToast('err', err.message || 'Lỗi xác nhận cọc');
    }
  };

  const handleConfirmDepositManual = async () => {
    if (!selectedOrder) return;
    try {
      await adminOrderAPI.confirmDepositManual(selectedOrder.id, { confirmation_note: paymentNote || undefined });
      showToast('ok', 'Đã xác nhận cọc');
      setPaymentOpen(false);
      setSelectedOrder(null);
      setOrderPayments([]);
      setPaymentNote('');
      fetchOrders();
      fetchStats();
    } catch (err: any) {
      showToast('err', err.message || 'Lỗi xác nhận cọc');
    }
  };

  const handleUpdateStatus = async (orderId: number, status: string) => {
    try {
      await adminOrderAPI.updateOrder(orderId, { status });
      showToast('ok', 'Đã cập nhật trạng thái');
      fetchOrders();
      fetchStats();
    } catch {
      showToast('err', 'Lỗi cập nhật trạng thái');
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
    { key: 'cancelled', label: 'Đã hủy', countKey: 'cancelled_orders' as const },
  ];

  return (
      <div className="p-6">
        {toast && (
          <div
            className={`fixed top-4 right-4 z-50 px-4 py-2 rounded-lg shadow-lg ${
              toast.type === 'ok' ? 'bg-green-600 text-white' : 'bg-red-600 text-white'
            }`}
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
            onClick={fetchOrders}
            className="px-4 py-2 bg-[#ea580c] text-white rounded-lg hover:bg-[#c2410c]"
          >
            Làm mới
          </button>
        </div>

        {stats && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-white rounded-lg shadow p-4">
              <p className="text-gray-500 text-sm">Tổng đơn hàng</p>
              <p className="text-2xl font-bold">{stats.total_orders}</p>
            </div>
            <div className="bg-white rounded-lg shadow p-4">
              <p className="text-gray-500 text-sm">Doanh thu hôm nay</p>
              <p className="text-2xl font-bold text-green-600">{formatVnd(Number(stats.total_revenue))}</p>
            </div>
            <div className="bg-white rounded-lg shadow p-4">
              <p className="text-gray-500 text-sm">Chờ đặt cọc</p>
              <p className="text-2xl font-bold text-orange-600">{stats.waiting_deposit_orders}</p>
            </div>
            <div className="bg-white rounded-lg shadow p-4">
              <p className="text-gray-500 text-sm">Đang giao hàng</p>
              <p className="text-2xl font-bold">{stats.shipping_orders}</p>
            </div>
          </div>
        )}

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
                {t.label} ({statusCounts != null ? (t.countKey === 'total_orders' ? statusCounts.total_orders : t.countKey === 'waiting_ship' ? (statusCounts.deposit_paid_orders ?? 0) + (statusCounts.confirmed_orders ?? 0) + (statusCounts.processing_orders ?? 0) : statusCounts[t.countKey] ?? 0) : '—'})
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
            <button
              onClick={() => {
                setSearch('');
                setStatusFilter('');
                setPaymentFilter('');
              }}
              className="px-3 py-2 border rounded-lg hover:bg-gray-50"
            >
              Xóa bộ lọc
            </button>
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
                  {filteredOrders.map((order) => (
                    <tr key={order.id} className="border-b hover:bg-gray-50">
                      <td className="p-3 font-mono text-sm">{order.order_code}</td>
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
                      <td className="p-3 font-semibold">{formatVnd(order.total_amount)}</td>
                      <td className="p-3 text-sm">
                        {depositRequiredDisplay(order) > 0 || adminOrderExpectsDeposit(order) ? (
                          <>
                            Cần: {formatVnd(depositRequiredDisplay(order))}
                            <br />
                            Đã cọc: {formatVnd(parseMoney(order.deposit_paid))}
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
                  ))}
                </tbody>
              </table>
            )}
            {!loading && filteredOrders.length === 0 && (
              <div className="p-8 text-center text-gray-500">Không có đơn hàng nào.</div>
            )}
          </div>
        </div>

        {/* Modal chi tiết đơn */}
        {detailOpen && selectedOrder && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setDetailOpen(false)}>
            <div
              className="relative flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-xl bg-white shadow-xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex shrink-0 items-center justify-between gap-3 border-b border-gray-100 bg-white px-6 py-4">
                <h2 className="min-w-0 flex-1 text-xl font-bold leading-tight text-gray-900 pr-2">Chi tiết đơn hàng</h2>
                <button
                  type="button"
                  aria-label="Đóng"
                  onClick={() => setDetailOpen(false)}
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-gray-300"
                >
                  <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
                <div>
                  <p className="text-gray-500 text-sm">Mã đơn (hiển thị khách)</p>
                  <p className="font-semibold text-lg tracking-wide">{selectedOrder.order_code}</p>
                  <p className="text-xs text-gray-500 mt-1">ID đơn nội bộ: #{selectedOrder.id}</p>
                  <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm text-gray-800">
                    <input
                      type="checkbox"
                      checked={!!selectedOrder.staff_consultation_contacted}
                      disabled={consultSavingId === selectedOrder.id}
                      onChange={(e) => void handleConsultationToggle(selectedOrder, e.target.checked)}
                      className="h-4 w-4 rounded border-gray-300 text-[#ea580c] focus:ring-[#ea580c] cursor-pointer disabled:opacity-50"
                    />
                    <span title="Nhân viên chốt đơn đã liên hệ tư vấn khách">Đã liên hệ tư vấn khách</span>
                  </label>
                  <p className="text-sm text-gray-600 mt-2">{formatDate(selectedOrder.created_at)}</p>
                </div>
                <div className="min-w-0">
                  <p className="text-gray-500 text-sm">Khách hàng</p>
                  <p className="font-medium">{selectedOrder.customer_name}</p>
                  <p className="text-sm">{selectedOrder.customer_phone}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <p className="text-gray-500 text-sm">Địa chỉ nhận hàng</p>
                    <button
                      type="button"
                      onClick={() => void copyCustomerAddress(selectedOrder.customer_address)}
                      disabled={!selectedOrder.customer_address?.trim()}
                      title="Sao chép địa chỉ"
                      aria-label="Sao chép địa chỉ nhận hàng"
                      className="inline-flex items-center gap-1 rounded-md border border-gray-200 bg-white px-2 py-0.5 text-xs font-medium text-gray-600 shadow-sm hover:bg-gray-50 disabled:pointer-events-none disabled:opacity-45"
                    >
                      <svg className="h-3.5 w-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                        />
                      </svg>
                      Sao chép
                    </button>
                  </div>
                  <p className="text-sm text-gray-800 mt-0.5 whitespace-pre-wrap break-words">
                    {selectedOrder.customer_address?.trim() || (
                      <span className="text-gray-400 italic">Chưa có địa chỉ</span>
                    )}
                  </p>
                  <p className="text-sm mt-2">{STATUS_TEXTS[selectedOrder.status]} / {PAYMENT_TEXTS[selectedOrder.payment_status] || selectedOrder.payment_status}</p>
                </div>
              </div>
              <div className="rounded-lg border border-amber-200 bg-amber-50/70 p-4 mb-4">
                <p className="text-sm font-semibold text-amber-900 mb-3">Thanh toán</p>
                <dl className="grid gap-2 text-sm">
                  <div className="flex flex-wrap justify-between gap-x-4 gap-y-1">
                    <dt className="text-gray-600">Tổng đơn</dt>
                    <dd className="font-semibold text-gray-900 tabular-nums">{formatVnd(parseMoney(selectedOrder.total_amount))}</dd>
                  </div>
                  {adminOrderExpectsDeposit(selectedOrder) ? (
                    <div className="flex flex-wrap justify-between gap-x-4 gap-y-1 items-baseline">
                      <dt className="text-gray-600 shrink-0">Đặt cọc</dt>
                      <dd className="font-medium text-gray-900 text-right tabular-nums">
                        <span>Cần: {formatVnd(depositRequiredDisplay(selectedOrder))}</span>
                        <span className="text-gray-400 font-normal mx-1.5">·</span>
                        <span>Đã cọc: {formatVnd(parseMoney(selectedOrder.deposit_paid))}</span>
                      </dd>
                    </div>
                  ) : (
                    <div className="flex flex-wrap justify-between gap-x-4 gap-y-1">
                      <dt className="text-gray-600">Đặt cọc</dt>
                      <dd className="text-green-700 font-medium">Không</dd>
                    </div>
                  )}
                  <div className="flex flex-wrap justify-between gap-x-4 gap-y-1 border-t border-amber-200/80 pt-2 mt-1 items-baseline">
                    <dt className="text-gray-800 font-medium shrink-0">
                      Số tiền thanh toán khi nhận hàng
                      {adminOrderExpectsDeposit(selectedOrder) && (
                        <span className="text-gray-500 font-normal hidden sm:inline"> (sau cọc)</span>
                      )}
                    </dt>
                    <dd className="font-semibold text-red-700 tabular-nums">{formatVnd(amountDueOnDelivery(selectedOrder))}</dd>
                  </div>
                </dl>
              </div>
              <div className="mb-4 overflow-x-auto">
                <h3 className="font-semibold mb-2">Sản phẩm</h3>
                <table className="w-full text-sm min-w-[560px]">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left py-2 w-[140px] min-w-[140px] font-medium text-gray-600">Ảnh</th>
                      <th className="text-left py-2 font-medium text-gray-600">Sản phẩm</th>
                      <th className="text-right py-2 font-medium text-gray-600 whitespace-nowrap">SL</th>
                      <th className="text-right py-2 font-medium text-gray-600 whitespace-nowrap">Đơn giá</th>
                      <th className="text-right py-2 font-medium text-gray-600 whitespace-nowrap">Thành tiền</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(selectedOrder.items || []).map((item) => {
                      const href = productPublicUrl(item.product_slug);
                      const color = colorDisplay(item);
                      const size = item.selected_size?.trim();
                      return (
                        <tr key={item.id} className="border-b align-top">
                          <td className="py-2 pr-2 align-middle">
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                              src={orderItemImageUrl(item.product_image)}
                              alt=""
                              className="block w-32 h-32 shrink-0 aspect-square rounded-lg object-cover border border-gray-100 bg-gray-50"
                              width={128}
                              height={128}
                            />
                          </td>
                          <td className="py-2 min-w-0 pr-2">
                            <div className="font-medium text-gray-900 leading-snug">
                              {href ? (
                                <a href={href} target="_blank" rel="noopener noreferrer" className="text-[#ea580c] hover:underline">
                                  {item.product_name}
                                </a>
                              ) : (
                                item.product_name
                              )}
                            </div>
                            <div className="mt-1.5 space-y-0.5 text-xs text-gray-600">
                              {item.product_id != null ? <p>Mã SP (ID): {item.product_id}</p> : null}
                              {color ? <p>Màu: {color}</p> : null}
                              {size ? <p>Size: {size}</p> : null}
                              {href ? (
                                <p className="truncate" title={href}>
                                  <span className="text-gray-500">Link: </span>
                                  <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-700 hover:underline break-all">
                                    {href.replace(/^https?:\/\//, '')}
                                  </a>
                                </p>
                              ) : (
                                <p className="text-gray-400 italic">Không có slug — không tạo link trang SP</p>
                              )}
                            </div>
                          </td>
                          <td className="py-2 text-right whitespace-nowrap">{item.quantity}</td>
                          <td className="py-2 text-right whitespace-nowrap">{formatVnd(item.unit_price)}</td>
                          <td className="py-2 text-right whitespace-nowrap font-medium">{formatVnd(item.total_price)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div className="flex flex-wrap gap-2 pt-4 border-t">
                {selectedOrder.status === 'waiting_deposit' && depositRequiredDisplay(selectedOrder) > 0 && (
                  <button onClick={() => { setDetailOpen(false); openPaymentModal(selectedOrder); }} className="px-4 py-2 bg-[#ea580c] text-white rounded-lg hover:bg-[#c2410c]">
                    Xác nhận cọc
                  </button>
                )}
                {(selectedOrder.status === 'deposit_paid' || selectedOrder.status === 'confirmed' || selectedOrder.status === 'processing') && (
                  <button onClick={() => handleUpdateStatus(selectedOrder.id, 'shipping')} className="px-4 py-2 bg-[#ea580c] text-white rounded-lg hover:bg-[#c2410c]">
                    Chuyển Chờ nhận hàng
                  </button>
                )}
                {selectedOrder.status === 'shipping' && (
                  <button onClick={() => handleUpdateStatus(selectedOrder.id, 'delivered')} className="px-4 py-2 bg-[#ea580c] text-white rounded-lg hover:bg-[#c2410c]">
                    Xác nhận đã giao
                  </button>
                )}
                {selectedOrder.status === 'delivered' && (
                  <button onClick={() => handleUpdateStatus(selectedOrder.id, 'completed')} className="px-4 py-2 bg-[#ea580c] text-white rounded-lg hover:bg-[#c2410c]">
                    Hoàn thành
                  </button>
                )}
                {!['cancelled', 'completed'].includes(selectedOrder.status) && (
                  <button onClick={() => handleUpdateStatus(selectedOrder.id, 'cancelled')} className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700">
                    Hủy đơn hàng
                  </button>
                )}
                <button onClick={() => setDetailOpen(false)} className="px-4 py-2 border rounded-lg hover:bg-gray-50">
                  Đóng
                </button>
              </div>
              </div>
            </div>
          </div>
        )}

        {/* Modal xác nhận cọc */}
        {paymentOpen && selectedOrder && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setPaymentOpen(false)}>
            <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6" onClick={(e) => e.stopPropagation()}>
              <h2 className="text-xl font-bold mb-4">Xác nhận đặt cọc</h2>
              <p className="mb-2">
                Đơn <strong>{selectedOrder.order_code}</strong>. Số tiền cọc:{' '}
                <strong className="text-red-600">{formatVnd(depositRequiredDisplay(selectedOrder))}</strong>
              </p>
              {loadingPayments && <p className="text-gray-500 text-sm">Đang tải...</p>}
              {!loadingPayments && orderPayments.length === 0 && (
                <p className="text-amber-600 text-sm mb-2">Chưa có giao dịch cọc.</p>
              )}
              {!loadingPayments && orderPayments.length === 0 && (
                <p className="text-gray-600 text-sm mb-3">Nếu khách đã chuyển khoản, bấm &quot;Xác nhận cọc&quot; bên dưới.</p>
              )}
              {!loadingPayments && orderPayments.length > 0 && <p className="text-sm text-gray-600 mb-3">Có {orderPayments.length} giao dịch chờ xác nhận.</p>}
              <div className="mb-4">
                <label className="block text-sm font-medium mb-1">Ghi chú</label>
                <textarea
                  rows={3}
                  placeholder="Ghi chú..."
                  value={paymentNote}
                  onChange={(e) => setPaymentNote(e.target.value)}
                  className="w-full border rounded-lg px-3 py-2"
                />
              </div>
              <div className="flex flex-wrap gap-2 justify-end">
                <button onClick={() => setPaymentOpen(false)} className="px-4 py-2 border rounded-lg hover:bg-gray-50">Hủy</button>
                {orderPayments.length === 0 ? (
                  <button
                    onClick={handleConfirmDepositManual}
                    className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
                  >
                    Xác nhận cọc
                  </button>
                ) : (
                  <>
                    <button
                      onClick={() => {
                        const p = orderPayments.find((x) => x.payment_status === 'pending') || orderPayments[0];
                        if (p) handleConfirmDeposit(selectedOrder.id, p.id, false, paymentNote);
                      }}
                      className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
                    >
                      Từ chối cọc
                    </button>
                    <button
                      onClick={() => {
                        const p = orderPayments.find((x) => x.payment_status === 'pending') || orderPayments[0];
                        if (p) handleConfirmDeposit(selectedOrder.id, p.id, true, paymentNote);
                      }}
                      className="px-4 py-2 bg-[#ea580c] text-white rounded-lg hover:bg-[#c2410c]"
                    >
                      Xác nhận đã nhận cọc
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
