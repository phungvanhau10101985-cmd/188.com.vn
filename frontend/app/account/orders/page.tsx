'use client';

import { useState, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import Image from 'next/image';
import Link from 'next/link';
import { apiClient } from '@/lib/api-client';
import { getOptimizedImage } from '@/lib/image-utils';
import ProductReviewFormModal from '@/app/products/[slug]/components/ProductReviewFormModal/ProductReviewFormModal';
import { useToast } from '@/components/ToastProvider';
import { trackEvent } from '@/lib/analytics';

interface OrderItem {
  id: number;
  product_id?: number;
  product_slug?: string | null;
  product_name: string;
  product_image?: string | null;
  quantity: number;
  unit_price: number;
  total_price?: number;
}

interface Order {
  id: number;
  order_code: string;
  customer_name: string;
  total_amount: number;
  status: string;
  payment_status?: string;
  payment_method?: string;
  requires_deposit?: boolean;
  deposit_amount?: number;
  deposit_paid?: number;
  remaining_amount?: number;
  created_at: string;
  items: OrderItem[];
  tracking_number?: string | null;
}

const CUSTOMER_TABS = [
  { key: 'all', label: 'Tất cả', statuses: null as string[] | null },
  { key: 'waiting_deposit', label: 'Chờ đặt cọc', statuses: ['waiting_deposit'] },
  { key: 'waiting_receive', label: 'Chờ nhận hàng', statuses: ['deposit_paid', 'confirmed', 'processing', 'shipping'] },
  { key: 'delivered', label: 'Đã nhận hàng', statuses: ['delivered'] },
  { key: 'completed', label: 'Đã đánh giá', statuses: ['completed'] },
  { key: 'cancelled', label: 'Đã hủy', statuses: ['cancelled'] },
];

const STATUS_LABELS: Record<string, string> = {
  pending: 'Chờ xác nhận',
  waiting_deposit: 'Chờ đặt cọc',
  deposit_paid: 'Đã đặt cọc',
  confirmed: 'Đã xác nhận',
  processing: 'Đang xử lý',
  shipping: 'Đang giao hàng',
  delivered: 'Đã nhận hàng',
  completed: 'Đã đánh giá',
  cancelled: 'Đã hủy',
};

function formatDate(s: string) {
  const d = new Date(s);
  return d.toLocaleDateString('vi-VN', { year: 'numeric', month: '2-digit', day: '2-digit' }) + ' ' + d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function formatVnd(n: number) {
  return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(n);
}

function matchTab(order: Order, tab: (typeof CUSTOMER_TABS)[0]): boolean {
  if (tab.key === 'all') return true;
  if (!tab.statuses) return false;
  return tab.statuses.includes(order.status);
}

function paymentMethodText(order: Order, item?: OrderItem): string {
  const method = order.payment_method || '';
  if (method === 'cod') return 'Thanh toán khi nhận hàng';
  if (order.status === 'waiting_deposit' && order.requires_deposit && order.deposit_amount) {
    return `Thanh toán qua chuyển khoản. Chuyển khoản số tiền ${formatVnd(Number(order.deposit_amount))} nội dung ${order.order_code} để đặt cọc.`;
  }
  return method === 'bank_transfer' ? 'Chuyển khoản ngân hàng' : method || '—';
}

export default function AccountOrdersPage() {
  const searchParams = useSearchParams();
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState('all');
  const [cancellingId, setCancellingId] = useState<number | null>(null);
  const [confirmingId, setConfirmingId] = useState<number | null>(null);
  const [cancelReason, setCancelReason] = useState('');
  const [cancelModalOrder, setCancelModalOrder] = useState<Order | null>(null);
  const [reviewedProductIds, setReviewedProductIds] = useState<Set<number>>(new Set());
  const [reviewModalProductId, setReviewModalProductId] = useState<number | null>(null);
  const [reviewModalProduct, setReviewModalProduct] = useState<any>(null);
  const [confirmReceivedModalOrder, setConfirmReceivedModalOrder] = useState<Order | null>(null);
  const { pushToast } = useToast();

  const loadOrders = (opts?: { silent?: boolean }) => {
    if (!opts?.silent) {
      setLoading(true);
      setError(null);
    }
    apiClient
      .getOrders({ limit: 200 })
      .then((data) => setOrders(Array.isArray(data) ? data : []))
      .catch((e) => {
        if (!opts?.silent) {
          setOrders([]);
          setError((e as Error)?.message || 'Không thể tải danh sách đơn hàng');
        }
      })
      .finally(() => {
        if (!opts?.silent) setLoading(false);
      });
  };

  useEffect(() => {
    loadOrders();
  }, []);

  useEffect(() => {
    const onVis = () => {
      if (document.visibilityState === 'visible') loadOrders({ silent: true });
    };
    document.addEventListener('visibilitychange', onVis);
    return () => document.removeEventListener('visibilitychange', onVis);
  }, []);

  useEffect(() => {
    const tab = searchParams.get('tab');
    if (!tab) return;
    const exists = CUSTOMER_TABS.some((t) => t.key === tab);
    if (exists) setActiveTab(tab);
  }, [searchParams]);

  useEffect(() => {
    const productIds = orders.flatMap((o) =>
      (o.items || [])
        .filter((i) => i.product_id != null && ['delivered', 'completed'].includes(o.status))
        .map((i) => i.product_id!)
    );
    const unique = [...new Set(productIds)];
    if (unique.length === 0) {
      setReviewedProductIds(new Set());
      return;
    }
    apiClient
      .getUserReviewedProductIds(unique)
      .then((r) => setReviewedProductIds(new Set(r.product_ids || [])))
      .catch(() => setReviewedProductIds(new Set()));
  }, [orders]);

  useEffect(() => {
    if (!reviewModalProductId) {
      setReviewModalProduct(null);
      return;
    }
    apiClient
      .getProductById(reviewModalProductId)
      .then(setReviewModalProduct)
      .catch(() => setReviewModalProduct(null));
  }, [reviewModalProductId]);

  const handleReviewSuccess = () => {
    setReviewModalProductId(null);
    setReviewModalProduct(null);
    loadOrders();
  };

  const handleCancel = async (order: Order) => {
    const reason = cancelReason.trim() || 'Khách hàng hủy';
    setCancellingId(order.id);
    try {
      await apiClient.cancelOrder(order.id, reason);
      setCancelModalOrder(null);
      setCancelReason('');
      loadOrders();
      trackEvent('order_cancel', { order_id: order.id });
      pushToast({ title: 'Đã hủy đơn hàng', variant: 'success', durationMs: 2500 });
    } catch (e) {
      pushToast({ title: 'Không thể hủy đơn', description: (e as Error).message || 'Vui lòng thử lại', variant: 'error', durationMs: 3500 });
    } finally {
      setCancellingId(null);
    }
  };

  const handleConfirmReceived = async (order: Order) => {
    setConfirmReceivedModalOrder(order);
  };

  const handleConfirmReceivedSubmit = async () => {
    if (!confirmReceivedModalOrder) return;
    
    setConfirmingId(confirmReceivedModalOrder.id);
    try {
      await apiClient.confirmReceived(confirmReceivedModalOrder.id);
      loadOrders();
      setConfirmReceivedModalOrder(null);
      trackEvent('order_confirm_received', { order_id: confirmReceivedModalOrder.id });
      pushToast({ title: 'Đã xác nhận nhận hàng', variant: 'success', durationMs: 2500 });
    } catch (e) {
      pushToast({ title: 'Không thể xác nhận', description: (e as Error).message || 'Vui lòng thử lại', variant: 'error', durationMs: 3500 });
    } finally {
      setConfirmingId(null);
    }
  };

  const tabWithCounts = CUSTOMER_TABS.map((t) => {
    const count = t.key === 'all' ? orders.length : orders.filter((o) => matchTab(o, t)).length;
    return { ...t, count };
  });

  const filteredOrders =
    activeTab === 'all'
      ? orders
      : orders.filter((o) => {
          const tab = CUSTOMER_TABS.find((t) => t.key === activeTab);
          return tab ? matchTab(o, tab) : false;
        });

  return (
    <div className="space-y-4">
      {/* Header như ảnh */}
      <div className="flex flex-wrap justify-between items-center gap-4">
        <h1 className="text-2xl font-bold text-gray-900">Đơn hàng</h1>
        <p className="text-gray-600 text-sm">Hạng thành viên: L1</p>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <div className="grid grid-cols-6">
          {tabWithCounts.map((t) => (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key)}
              className={`flex flex-col items-center justify-between gap-1 py-2 text-[11px] md:text-sm font-medium border-b-2 ${
                activeTab === t.key
                  ? 'border-red-600 text-red-600'
                  : 'border-transparent text-gray-600 hover:text-gray-900'
              }`}
            >
              <span className="leading-tight text-center h-8 flex items-start justify-center pt-2">{t.label}</span>
              <span className="relative top-[0.3rem] inline-flex items-center justify-center min-w-[18px] h-4 px-1 rounded-full bg-orange-500 text-white text-[10px] font-bold">
                {t.count}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Cảnh báo */}
      <div className="bg-red-50 border border-red-100 rounded-lg px-4 py-2">
        <p className="text-red-700 text-sm">
          Lưu ý: Hệ thống sẽ tự động huỷ các đơn đặt hàng quá 03 ngày chưa được thanh toán.
        </p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          {error}{' '}
          <button type="button" onClick={() => loadOrders()} className="underline font-medium">
            Thử lại
          </button>
        </div>
      )}

      {loading ? (
        <div className="py-12 text-center text-gray-500">Đang tải đơn hàng...</div>
      ) : filteredOrders.length === 0 ? (
        <div className="py-12 text-center text-gray-500 bg-white rounded-xl border border-gray-100 p-8">
          Chưa có đơn hàng nào.
          <br />
          <Link href="/" className="text-blue-600 hover:underline mt-2 inline-block">Tiếp tục mua sắm</Link>
        </div>
      ) : (
        <ul className="space-y-6">
          {filteredOrders.map((order) => (
            <li key={order.id} className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
              {/* Tóm tắt đơn */}
              <div className="p-4 border-b border-gray-100">
                <div className="flex flex-wrap justify-between items-start gap-3">
                  <div>
                    <span className="text-gray-600">Đơn hàng: </span>
                    <Link href={`/account/orders/${order.id}`} className="text-blue-600 hover:underline font-medium">
                      {order.order_code}
                    </Link>
                    <p className="text-gray-500 text-sm mt-1">{formatDate(order.created_at)}</p>
                  </div>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-3 text-sm">
                  <p><span className="text-gray-500">Tổng chi phí(₫):</span> <strong>{formatVnd(Number(order.total_amount))}</strong></p>
                  <p><span className="text-gray-500">Số tiền đã thanh toán đặt cọc trước(₫):</span> <strong>{formatVnd(Number(order.deposit_paid || 0))}</strong></p>
                  <p><span className="text-gray-500">Số tiền thanh toán khi nhận hàng(₫):</span> <strong>{formatVnd(Number(order.remaining_amount ?? order.total_amount))}</strong></p>
                </div>
                <p className="text-sm text-gray-500 mt-1">Số lượng sản phẩm: {order.items?.length || 0}</p>
              </div>

              {/* Bảng sản phẩm */}
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-100">
                      <th className="text-left p-3 font-medium text-gray-700">Sản phẩm</th>
                      <th className="text-right p-3 font-medium text-gray-700">Giá</th>
                      <th className="text-right p-3 font-medium text-gray-700">Số lượng</th>
                      <th className="text-right p-3 font-medium text-gray-700">Thành tiền</th>
                      <th className="text-left p-3 font-medium text-gray-700">Trạng thái</th>
                      <th className="text-left p-3 font-medium text-gray-700">Phương thức thanh toán</th>
                      <th className="p-3 w-32"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {(order.items || []).map((item) => (
                      <tr key={item.id} className="border-b border-gray-50">
                        <td className="p-3">
                          <div className="flex items-center gap-3">
                            {item.product_image ? (
                              <div className="relative w-16 h-16 rounded overflow-hidden bg-gray-100 flex-shrink-0">
                                <Image
                                  src={getOptimizedImage(item.product_image, { fallbackStrategy: 'local' })}
                                  alt=""
                                  fill
                                  sizes="64px"
                                  className="object-cover"
                                />
                              </div>
                            ) : (
                              <div className="w-16 h-16 rounded bg-gray-100 flex-shrink-0" />
                            )}
                            <span className="text-gray-800 line-clamp-2">{item.product_name}</span>
                          </div>
                        </td>
                        <td className="p-3 text-right">{formatVnd(item.unit_price)}</td>
                        <td className="p-3 text-right">{item.quantity}</td>
                        <td className="p-3 text-right">{formatVnd((item.total_price ?? item.unit_price * item.quantity))}</td>
                        <td className="p-3">
                          <span className={order.status === 'cancelled' ? 'text-red-600' : 'text-gray-700'}>
                            {STATUS_LABELS[order.status] || order.status}
                          </span>
                        </td>
                        <td className="p-3 text-gray-600 text-xs max-w-[200px]">{paymentMethodText(order, item)}</td>
                        <td className="p-3">
                          {['delivered', 'completed'].includes(order.status) && item.product_id ? (
                            reviewedProductIds.has(item.product_id) ? (
                              <Link
                                href={item.product_slug ? `/products/${item.product_slug}/reviews` : `/account/orders/${order.id}`}
                                className="inline-block px-3 py-1.5 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300"
                              >
                                Xem đánh giá
                              </Link>
                            ) : (
                              <button
                                type="button"
                                onClick={() => setReviewModalProductId(item.product_id!)}
                                className="px-3 py-1.5 bg-[#ea580c] text-white rounded text-sm hover:bg-[#c2410c] font-medium"
                              >
                                Đánh giá
                              </button>
                            )
                          ) : (
                            <Link
                              href={`/account/orders/${order.id}`}
                              className="inline-block px-3 py-1.5 bg-gray-100 text-gray-700 rounded text-sm hover:bg-gray-200"
                            >
                              Chi tiết đơn hàng
                            </Link>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Nút theo trạng thái - đặt dưới bảng, mỗi đơn một hàng nút */}
              <div className="p-4 bg-gray-50 border-t border-gray-100 flex flex-wrap gap-2">
                <Link href={`/account/orders/${order.id}`} className="px-4 py-2 bg-gray-200 text-gray-800 rounded-lg text-sm font-medium hover:bg-gray-300">
                  Chi tiết đơn hàng
                </Link>
                {order.status === 'waiting_deposit' && (
                  <>
                    <Link href={`/account/orders/${order.id}/deposit`} className="px-4 py-2 bg-[#ea580c] text-white rounded-lg text-sm font-medium hover:bg-[#c2410c]">
                      Thanh toán đặt cọc
                    </Link>
                    <button onClick={() => setCancelModalOrder(order)} className="px-4 py-2 bg-red-100 text-red-700 rounded-lg text-sm font-medium hover:bg-red-200">
                      Hủy đơn
                    </button>
                  </>
                )}
                {['deposit_paid', 'confirmed', 'processing', 'shipping'].includes(order.status) && (
                  <>
                    {order.tracking_number && (
                      <a href="#" className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-300">
                        Lịch trình đơn hàng
                      </a>
                    )}
                    <button
                      onClick={() => handleConfirmReceived(order)}
                      disabled={!!confirmingId}
                      className="px-4 py-2 bg-[#ea580c] text-white rounded-lg text-sm font-medium hover:bg-[#c2410c] disabled:opacity-50"
                    >
                      Đã nhận hàng
                    </button>
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* Modal form đánh giá sản phẩm */}
      {reviewModalProduct && (
        <ProductReviewFormModal
          product={reviewModalProduct}
          isOpen={!!reviewModalProduct}
          onClose={() => { setReviewModalProductId(null); setReviewModalProduct(null); }}
          onSuccess={handleReviewSuccess}
        />
      )}

      {/* Modal hủy đơn */}
      {cancelModalOrder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setCancelModalOrder(null)}>
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 mx-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-bold text-gray-900 mb-2">Hủy đơn hàng</h3>
            <p className="text-gray-600 text-sm mb-4">Đơn {cancelModalOrder.order_code}. Bạn chắc chắn muốn hủy?</p>
            <textarea
              placeholder="Lý do hủy (tùy chọn)"
              value={cancelReason}
              onChange={(e) => setCancelReason(e.target.value)}
              className="w-full border rounded-lg px-3 py-2 text-sm mb-4"
              rows={2}
            />
            <div className="flex gap-2 justify-end">
              <button onClick={() => { setCancelModalOrder(null); setCancelReason(''); }} className="px-4 py-2 border rounded-lg hover:bg-gray-50">
                Không
              </button>
              <button onClick={() => handleCancel(cancelModalOrder)} disabled={!!cancellingId} className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50">
                {cancellingId ? 'Đang hủy...' : 'Hủy đơn'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal xác nhận đã nhận hàng */}
      {confirmReceivedModalOrder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setConfirmReceivedModalOrder(null)}>
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 mx-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-bold text-gray-900 mb-4">Xác nhận đã nhận hàng</h3>
            <p className="text-gray-600 text-sm mb-6">
              Bấm <strong>{'"'}Xác nhận{'"'}</strong> nghĩa là <strong>188.com.vn</strong> đã hoàn thành trách nhiệm giao trả đầy đủ đơn hàng <strong>{confirmReceivedModalOrder.order_code}</strong> cho quý khách đúng hẹn và không có khiếu nại gì.
            </p>
            <div className="flex gap-2 justify-end">
              <button 
                onClick={() => setConfirmReceivedModalOrder(null)} 
                className="px-4 py-2 border rounded-lg hover:bg-gray-50"
              >
                Hủy bỏ
              </button>
              <button 
                onClick={handleConfirmReceivedSubmit} 
                disabled={!!confirmingId}
                className="px-4 py-2 bg-[#ea580c] text-white rounded-lg hover:bg-[#c2410c] disabled:opacity-50"
              >
                {confirmingId === confirmReceivedModalOrder.id ? 'Đang xử lý...' : 'Xác nhận'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
