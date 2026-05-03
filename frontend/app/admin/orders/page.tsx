// frontend/app/admin/orders/page.tsx - ADMIN ORDER MANAGEMENT (Tailwind only, no antd)
'use client';

import { useState, useEffect, useCallback } from 'react';
import { adminOrderAPI, type AdminOrder, type PaymentRecord } from '@/lib/admin-api';
import { cdnUrl } from '@/lib/cdn-url';

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

/** Link SP public: ưu tiên NEXT_PUBLIC_SITE_URL để admin localhost vẫn mở đúng shop. */
function shopOrigin(): string {
  const env = process.env.NEXT_PUBLIC_SITE_URL?.trim().replace(/\/$/, '');
  if (env) return env;
  if (typeof window !== 'undefined') return window.location.origin;
  return 'https://188.com.vn';
}

function orderItemImageUrl(src: string | null | undefined): string {
  if (!src?.trim()) return cdnUrl('/images/placeholder-product.jpg');
  const s = src.trim();
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

  const showToast = (type: 'ok' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 3000);
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
                    <th className="p-3 font-medium">Khách hàng</th>
                    <th className="p-3 font-medium">Tổng tiền</th>
                    <th className="p-3 font-medium">Đặt cọc</th>
                    <th className="p-3 font-medium">Trạng thái</th>
                    <th className="p-3 font-medium">Thanh toán</th>
                    <th className="p-3 font-medium">Ngày đặt</th>
                    <th className="p-3 font-medium">Thao tác</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredOrders.map((order) => (
                    <tr key={order.id} className="border-b hover:bg-gray-50">
                      <td className="p-3 font-mono text-sm">{order.order_code}</td>
                      <td className="p-3">
                        <div className="font-medium">{order.customer_name}</div>
                        <div className="text-gray-500 text-sm">{order.customer_phone}</div>
                      </td>
                      <td className="p-3 font-semibold">{formatVnd(order.total_amount)}</td>
                      <td className="p-3 text-sm">
                        {order.requires_deposit ? (
                          <>
                            Cần: {formatVnd(order.deposit_amount)}
                            <br />
                            Đã cọc: {formatVnd(order.deposit_paid)}
                          </>
                        ) : (
                          <span className="text-green-600">Không cần cọc</span>
                        )}
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
                          {order.status === 'waiting_deposit' && (
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
            <div className="bg-white rounded-xl shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto p-6" onClick={(e) => e.stopPropagation()}>
              <h2 className="text-xl font-bold mb-4">Chi tiết đơn hàng</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
                <div>
                  <p className="text-gray-500 text-sm">Mã đơn (hiển thị khách)</p>
                  <p className="font-semibold text-lg tracking-wide">{selectedOrder.order_code}</p>
                  <p className="text-xs text-gray-500 mt-1">ID đơn nội bộ: #{selectedOrder.id}</p>
                  <p className="text-sm text-gray-600 mt-2">{formatDate(selectedOrder.created_at)}</p>
                  <p className="font-semibold text-red-600 mt-1">{formatVnd(selectedOrder.total_amount)}</p>
                </div>
                <div>
                  <p className="text-gray-500 text-sm">Khách hàng</p>
                  <p className="font-medium">{selectedOrder.customer_name}</p>
                  <p className="text-sm">{selectedOrder.customer_phone}</p>
                  <p className="text-sm mt-1">{STATUS_TEXTS[selectedOrder.status]} / {PAYMENT_TEXTS[selectedOrder.payment_status] || selectedOrder.payment_status}</p>
                </div>
              </div>
              {selectedOrder.requires_deposit && (
                <div className="p-4 bg-yellow-50 rounded-lg mb-4">
                  <p className="font-medium text-yellow-800">Đặt cọc: Cần {formatVnd(selectedOrder.deposit_amount)} — Đã cọc {formatVnd(selectedOrder.deposit_paid)}</p>
                </div>
              )}
              <div className="mb-4 overflow-x-auto">
                <h3 className="font-semibold mb-2">Sản phẩm</h3>
                <table className="w-full text-sm min-w-[520px]">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left py-2 w-[76px] font-medium text-gray-600">Ảnh</th>
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
                          <td className="py-2 pr-2">
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                              src={orderItemImageUrl(item.product_image)}
                              alt=""
                              className="w-14 h-14 rounded-lg object-cover border border-gray-100 bg-gray-50"
                              width={56}
                              height={56}
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
                {selectedOrder.status === 'waiting_deposit' && (
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
        )}

        {/* Modal xác nhận cọc */}
        {paymentOpen && selectedOrder && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setPaymentOpen(false)}>
            <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6" onClick={(e) => e.stopPropagation()}>
              <h2 className="text-xl font-bold mb-4">Xác nhận đặt cọc</h2>
              <p className="mb-2">Đơn <strong>{selectedOrder.order_code}</strong>. Số tiền cọc: <strong className="text-red-600">{formatVnd(selectedOrder.deposit_amount)}</strong></p>
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
