'use client';

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { apiClient } from '@/lib/api-client';
import type { BankAccountInfo } from '@/lib/api-client';
import ProductReviewFormModal from '@/app/products/[slug]/components/ProductReviewFormModal/ProductReviewFormModal';
import { getOptimizedImage } from '@/lib/image-utils';
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
  customer_phone?: string;
  total_amount: number;
  status: string;
  payment_status?: string;
  requires_deposit?: boolean;
  deposit_type?: string;
  deposit_amount?: number;
  deposit_paid?: number;
  remaining_amount?: number;
  created_at: string;
  items: OrderItem[];
  tracking_number?: string | null;
}

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
  return d.toLocaleDateString('vi-VN') + ' ' + d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
}

function formatVnd(n: number) {
  return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(n);
}

function shortTransferContent(orderCode: string, phone: string): string {
  const digits = (phone || '').replace(/\D/g, '').slice(-10) || '';
  return `${orderCode}-${digits}`.replace(/-$/, '') || orderCode;
}

function copyToClipboard(text: string) {
  if (typeof navigator !== 'undefined' && navigator.clipboard) {
    navigator.clipboard.writeText(text);
  }
}

export default function AccountOrderDetailPage() {
  const params = useParams();
  const id = Number(params?.id);
  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bankAccounts, setBankAccounts] = useState<BankAccountInfo[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [reviewedProductIds, setReviewedProductIds] = useState<Set<number>>(new Set());
  const [reviewModalProductId, setReviewModalProductId] = useState<number | null>(null);
  const [reviewModalProduct, setReviewModalProduct] = useState<any>(null);
  const [copied, setCopied] = useState(false);
  const [copiedAccountId, setCopiedAccountId] = useState<number | null>(null);
  const [depositOption, setDepositOption] = useState<'30' | '100'>('30');
  const [updatingDeposit, setUpdatingDeposit] = useState(false);
  const [showConfirmReceivedModal, setShowConfirmReceivedModal] = useState(false);
  const [cancellingId, setCancellingId] = useState<number | null>(null);
  const [cancelReason, setCancelReason] = useState('');
  const [showCancelModal, setShowCancelModal] = useState(false);
  const { pushToast } = useToast();
  const orderStatusPollRef = useRef<string | null>(null);

  const loadOrder = useCallback(() => {
    if (!id) return;
    setLoading(true);
    setError(null);
    apiClient
      .getOrder(id)
      .then(setOrder)
      .catch((e) => {
        setOrder(null);
        setError((e as Error)?.message || 'Không thể tải đơn hàng');
      })
      .finally(() => setLoading(false));
  }, [id]);

  const reviewableProductIds = useMemo(() => {
    if (!order || !['delivered', 'completed'].includes(order.status)) return [];
    return (order.items || []).filter((i) => i.product_id).map((i) => i.product_id!);
  }, [order]);

  useEffect(() => {
    loadOrder();
  }, [loadOrder]);

  useEffect(() => {
    if (!id || !order || order.status !== 'waiting_deposit' || !order.requires_deposit) return;
    const iv = setInterval(() => {
      apiClient
        .getOrder(id)
        .then((o) => {
          setOrder(o);
          const prev = orderStatusPollRef.current;
          if (prev === 'waiting_deposit' && o.status !== 'waiting_deposit') {
            if (o.status === 'deposit_paid' || o.status === 'confirmed') {
              pushToast({
                title: 'Đã ghi nhận đặt cọc',
                description: 'Trạng thái đơn đã cập nhật. Email xác nhận đã được gửi (nếu có email đơn hàng).',
                variant: 'success',
                durationMs: 5500,
              });
            }
          }
          orderStatusPollRef.current = o.status;
        })
        .catch(() => {});
    }, 5000);
    orderStatusPollRef.current = order.status;
    return () => clearInterval(iv);
  }, [id, order?.id, order?.status, order?.requires_deposit, pushToast]);

  useEffect(() => {
    if (reviewableProductIds.length === 0) return;
    apiClient
      .getUserReviewedProductIds(reviewableProductIds)
      .then((r) => setReviewedProductIds(new Set(r.product_ids || [])));
  }, [reviewableProductIds]);

  useEffect(() => {
    if (!reviewModalProductId) { setReviewModalProduct(null); return; }
    apiClient.getProductById(reviewModalProductId).then(setReviewModalProduct).catch(() => setReviewModalProduct(null));
  }, [reviewModalProductId]);

  useEffect(() => {
    if (order?.requires_deposit && order.status === 'waiting_deposit') {
      apiClient.getBankAccounts().then(setBankAccounts).catch(() => setBankAccounts([]));
      const t = order.deposit_type ?? '';
      setDepositOption(t === 'percent_100' ? '100' : '30');
    }
  }, [order]);


  const handleDepositTypeChange = async (option: '30' | '100') => {
    if (!order || order.status !== 'waiting_deposit' || option === depositOption) return;
    setUpdatingDeposit(true);
    try {
      await apiClient.updateOrderDepositType(order.id, option === '100' ? 'percent_100' : 'percent_30');
      setDepositOption(option);
      loadOrder();
      pushToast({ title: 'Đã cập nhật mức cọc', variant: 'success', durationMs: 2500 });
    } catch (e) {
      pushToast({ title: 'Không thể đổi mức cọc', description: (e as Error).message || 'Vui lòng thử lại', variant: 'error', durationMs: 3500 });
    } finally {
      setUpdatingDeposit(false);
    }
  };

  const handleConfirmReceivedSubmit = async () => {
    if (!order) return;
    setConfirming(true);
    try {
      await apiClient.confirmReceived(order.id);
      loadOrder();
      setShowConfirmReceivedModal(false);
      trackEvent('order_confirm_received', { order_id: order.id });
      pushToast({ title: 'Đã xác nhận nhận hàng', variant: 'success', durationMs: 2500 });
    } catch (e) {
      pushToast({ title: 'Không thể xác nhận', description: (e as Error).message || 'Vui lòng thử lại', variant: 'error', durationMs: 3500 });
    } finally {
      setConfirming(false);
    }
  };

  const handleCancel = async () => {
    if (!order) return;
    const reason = cancelReason.trim() || 'Khách hàng hủy';
    setCancellingId(order.id);
    try {
      await apiClient.cancelOrder(order.id, reason);
      setShowCancelModal(false);
      setCancelReason('');
      loadOrder();
      trackEvent('order_cancel', { order_id: order.id });
      pushToast({ title: 'Đã hủy đơn hàng', variant: 'success', durationMs: 2500 });
    } catch (e) {
      pushToast({ title: 'Không thể hủy đơn', description: (e as Error).message || 'Vui lòng thử lại', variant: 'error', durationMs: 3500 });
    } finally {
      setCancellingId(null);
    }
  };

  if (loading) {
    return <div className="py-12 text-center text-gray-500">Đang tải...</div>;
  }
  if (error) {
    return (
      <div className="py-12 text-center">
        <p className="text-gray-500 mb-2">{error}</p>
        <button onClick={loadOrder} className="text-blue-600 hover:underline">Thử lại</button>
      </div>
    );
  }
  if (!order) {
    return (
      <div className="py-12 text-center">
        <p className="text-gray-500">Không tìm thấy đơn hàng.</p>
        <Link href="/account/orders" className="text-blue-600 hover:underline mt-2 inline-block">Quay lại đơn hàng</Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-4">
        <h2 className="text-xl font-bold text-gray-900">Đơn #{order.order_code}</h2>
        <span className="px-2 py-1 rounded text-sm font-medium bg-gray-100 text-gray-700">
          {STATUS_LABELS[order.status] || order.status}
        </span>
      </div>

      <div className="bg-white rounded-xl shadow border border-gray-100 p-6 space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <p className="text-gray-500 text-sm">Ngày đặt</p>
            <p className="font-medium">{formatDate(order.created_at)}</p>
          </div>
          <div>
            <p className="text-gray-500 text-sm">Tổng đơn hàng (bao gồm phí vận chuyển)</p>
            <p className="font-bold text-lg text-gray-900">{formatVnd(Number(order.total_amount))}</p>
          </div>
        </div>

        {order.requires_deposit && order.status === 'waiting_deposit' && (
          <div className="p-6 bg-orange-50 border border-orange-200 rounded-2xl flex flex-col md:flex-row items-center justify-between gap-4">
            <div>
              <h3 className="font-semibold text-orange-700 text-lg">Đơn hàng chờ đặt cọc</h3>
              <p className="text-orange-600 text-sm mt-1">
                Vui lòng thanh toán đặt cọc để chúng tôi tiến hành xử lý đơn hàng của bạn.
              </p>
            </div>
            <div className="flex gap-3">
               <button 
                 onClick={() => setShowCancelModal(true)}
                 className="px-5 py-2.5 bg-white border border-orange-200 text-orange-700 text-sm font-medium rounded-lg hover:bg-orange-50"
               >
                 Hủy đơn
               </button>
               <Link
                 href={`/account/orders/${order.id}/deposit`}
                 className="px-5 py-2.5 bg-[#ea580c] text-white text-sm font-medium rounded-lg hover:bg-[#c2410c]"
               >
                 Tiến hành đặt cọc
               </Link>
            </div>
          </div>
        )}
        {order.requires_deposit && order.status !== 'waiting_deposit' && (
          <div className="p-4 bg-gray-50 rounded-lg text-sm">
            <p className="text-gray-600">Đã cọc: {formatVnd(Number(order.deposit_paid || 0))} — Còn lại khi nhận hàng: {formatVnd(Number(order.remaining_amount ?? 0))}</p>
          </div>
        )}

        <div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-gray-500">
                <th className="py-2">Sản phẩm</th>
                <th className="py-2 text-center w-20">SL</th>
                <th className="py-2 text-right w-28">Đơn giá</th>
                <th className="py-2 text-right w-28">Thành tiền</th>
                {['delivered', 'completed'].includes(order.status) && <th className="py-2 w-28"></th>}
              </tr>
            </thead>
            <tbody>
              {(order.items || []).map((item) => (
                <tr key={item.id} className="border-b">
                  <td className="py-2">
                    <div className="flex items-center gap-2">
                      {item.product_image ? (
                        <div className="w-12 h-12 rounded overflow-hidden bg-gray-100 flex-shrink-0 relative">
                          <Image
                            src={getOptimizedImage(item.product_image, { fallbackStrategy: 'local' })}
                            alt=""
                            fill
                            sizes="48px"
                            className="object-cover"
                          />
                        </div>
                      ) : null}
                      <span>{item.product_name}</span>
                    </div>
                  </td>
                  <td className="py-2 text-center font-medium">{item.quantity}</td>
                  <td className="py-2 text-right font-medium">{formatVnd(item.unit_price)}</td>
                  <td className="py-2 text-right font-semibold text-[#ea580c]">{formatVnd((item.total_price ?? item.unit_price * item.quantity))}</td>
                  {['delivered', 'completed'].includes(order.status) && item.product_id && (
                    <td className="py-2">
                      {reviewedProductIds.has(item.product_id) ? (
                        <Link
                          href={item.product_slug ? `/products/${item.product_slug}/reviews` : '#'}
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
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Nút theo trạng thái */}
        <div className="pt-4 border-t flex flex-wrap gap-2">
          {order.status === 'waiting_deposit' && (
             <button 
               onClick={() => setShowCancelModal(true)}
               className="px-4 py-2 bg-red-100 text-red-700 rounded-lg text-sm font-medium hover:bg-red-200"
             >
               Hủy đơn
             </button>
          )}
          {['deposit_paid', 'confirmed', 'processing', 'shipping'].includes(order.status) && (
            <>
              {order.tracking_number && (
                <a href="#" className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-300">
                  Lịch trình đơn hàng
                </a>
              )}
              <button
                onClick={() => setShowConfirmReceivedModal(true)}
                disabled={confirming}
                className="px-4 py-2 bg-[#ea580c] text-white rounded-lg text-sm font-medium hover:bg-[#c2410c] disabled:opacity-50"
              >
                Đã nhận hàng
              </button>
            </>
          )}
        </div>
      </div>

      {/* Modal xác nhận đã nhận hàng */}
      {showConfirmReceivedModal && order && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setShowConfirmReceivedModal(false)}>
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 mx-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-bold text-gray-900 mb-4">Xác nhận đã nhận hàng</h3>
            <p className="text-gray-600 text-sm mb-6">
              Bấm <strong>{'"'}Xác nhận{'"'}</strong> nghĩa là <strong>188.com.vn</strong> đã hoàn thành trách nhiệm giao trả đầy đủ đơn hàng <strong>{order.order_code}</strong> cho quý khách đúng hẹn và không có khiếu nại gì.
            </p>
            <div className="flex gap-2 justify-end">
              <button 
                onClick={() => setShowConfirmReceivedModal(false)} 
                className="px-4 py-2 border rounded-lg hover:bg-gray-50"
              >
                Hủy bỏ
              </button>
              <button 
                onClick={handleConfirmReceivedSubmit} 
                disabled={confirming}
                className="px-4 py-2 bg-[#ea580c] text-white rounded-lg hover:bg-[#c2410c] disabled:opacity-50"
              >
                {confirming ? 'Đang xử lý...' : 'Xác nhận'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal hủy đơn */}
      {showCancelModal && order && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setShowCancelModal(false)}>
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 mx-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-bold text-gray-900 mb-2">Hủy đơn hàng</h3>
            <p className="text-gray-600 text-sm mb-4">Đơn {order.order_code}. Bạn chắc chắn muốn hủy?</p>
            <textarea
              placeholder="Lý do hủy (tùy chọn)"
              value={cancelReason}
              onChange={(e) => setCancelReason(e.target.value)}
              className="w-full border rounded-lg px-3 py-2 text-sm mb-4"
              rows={2}
            />
            <div className="flex gap-2 justify-end">
              <button onClick={() => { setShowCancelModal(false); setCancelReason(''); }} className="px-4 py-2 border rounded-lg hover:bg-gray-50">
                Không
              </button>
              <button onClick={handleCancel} disabled={!!cancellingId} className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50">
                {cancellingId ? 'Đang hủy...' : 'Hủy đơn'}
              </button>
            </div>
          </div>
        </div>
      )}

      {reviewModalProduct && (
        <ProductReviewFormModal
          product={reviewModalProduct}
          isOpen={!!reviewModalProduct}
          onClose={() => { setReviewModalProductId(null); setReviewModalProduct(null); }}
          onSuccess={() => { setReviewModalProductId(null); setReviewModalProduct(null); loadOrder(); }}
        />
      )}

    </div>
  );
}
