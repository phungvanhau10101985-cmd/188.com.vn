'use client';

import { useCallback, useEffect, useState } from 'react';
import OrderItemVariantMeta, { orderItemImageLink } from '@/components/orders/OrderItemVariantMeta';
import { adminOrderAPI, type AdminOrder } from '@/lib/admin-api';
import { cdnUrl, normalizeRemoteImageUrlForDisplay } from '@/lib/cdn-url';
import { partialDepositAmount } from '@/lib/order-deposit';
import { productPathSlugFromApi } from '@/lib/product-path-slug';

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

type ShipmentTimeline = Awaited<ReturnType<typeof adminOrderAPI.getOrderShipmentTimeline>>;

type Notify = (type: 'ok' | 'err', msg: string) => void;

type AdminOrderDetailModalProps = {
  order: AdminOrder;
  onClose: () => void;
  onOrderChange: (order: AdminOrder) => void;
  onRefresh: () => void;
  onRequestDepositConfirm?: (order: AdminOrder) => void;
  notify: Notify;
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

function parseMoney(value: unknown): number {
  if (value == null) return 0;
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0;
  const s = String(value).trim().replace(/\s/g, '').replace(/,/g, '');
  const x = parseFloat(s);
  return Number.isFinite(x) ? x : 0;
}

function adminOrderExpectsDeposit(order: AdminOrder): boolean {
  if (order.requires_deposit) return true;
  return (order.items || []).some((i) => i.requires_deposit);
}

function depositRequiredDisplay(order: AdminOrder): number {
  const stored = parseMoney(order.deposit_amount);
  if (stored > 0) return stored;
  if (!adminOrderExpectsDeposit(order)) return 0;
  const total = parseMoney(order.total_amount);
  const shipping = parseMoney(order.shipping_fee);
  const goods = Math.max(0, total - shipping);
  const pct = Number(order.deposit_percentage) || 0;
  if (pct >= 100 || order.deposit_type === 'percent_100') return goods;
  if (pct > 0 && pct < 100) return partialDepositAmount(goods, pct);
  if (order.deposit_type === 'percent_30') return partialDepositAmount(goods, 30);
  if (order.status === 'waiting_deposit' && total > 0) return partialDepositAmount(goods, 30);
  return 0;
}

function amountDueOnDelivery(order: AdminOrder): number {
  const total = parseMoney(order.total_amount);
  const paidDeposit = parseMoney(order.deposit_paid);
  if (paidDeposit > 0) return Math.max(0, Math.round(total - paidDeposit));
  if (!adminOrderExpectsDeposit(order)) {
    const apiRemain = parseMoney(order.remaining_amount);
    if (apiRemain > 0) return Math.max(0, Math.round(apiRemain));
    return Math.max(0, Math.round(total));
  }
  return Math.max(0, Math.round(total - depositRequiredDisplay(order)));
}

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
  const seg = productPathSlugFromApi(slug);
  if (!seg) return null;
  return `${shopOrigin()}/products/${encodeURIComponent(seg)}`;
}

function orderItemSkuLabel(item: {
  product_sku?: string | null;
  product_code?: string | null;
}): string | null {
  const sku = item.product_sku?.trim();
  if (sku) return sku;
  const code = item.product_code?.trim();
  return code || null;
}

function externalLinkLine(label: string, url: string | null | undefined) {
  const href = url?.trim();
  if (!href) return null;
  return (
    <p className="break-words" title={href}>
      <span className="text-gray-500">{label}: </span>
      <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-700 hover:underline break-all">
        {href.replace(/^https?:\/\//, '')}
      </a>
    </p>
  );
}

function mergeOrder(current: AdminOrder, updated: AdminOrder): AdminOrder {
  return {
    ...current,
    ...updated,
    items: updated.items?.length ? updated.items : current.items,
  };
}

export default function AdminOrderDetailModal({
  order,
  onClose,
  onOrderChange,
  onRefresh,
  onRequestDepositConfirm,
  notify,
}: AdminOrderDetailModalProps) {
  const [consultSaving, setConsultSaving] = useState(false);
  const [shipmentTimeline, setShipmentTimeline] = useState<ShipmentTimeline | null>(null);
  const [shipmentLoading, setShipmentLoading] = useState(false);
  const [trackingNumber, setTrackingNumber] = useState('');
  const [shippingProvider, setShippingProvider] = useState('');
  const [clearCustomsBusy, setClearCustomsBusy] = useState(false);
  const [startPackingBusy, setStartPackingBusy] = useState(false);
  const [markOutForConfirmBusy, setMarkOutForConfirmBusy] = useState(false);
  const [overrideReason, setOverrideReason] = useState('');
  const [overrideBusy, setOverrideBusy] = useState(false);

  const loadShipmentTimeline = useCallback(async (orderId: number) => {
    setShipmentLoading(true);
    try {
      setShipmentTimeline(await adminOrderAPI.getOrderShipmentTimeline(orderId));
    } catch {
      setShipmentTimeline(null);
    } finally {
      setShipmentLoading(false);
    }
  }, []);

  useEffect(() => {
    setTrackingNumber(order.tracking_number || '');
    setShippingProvider(order.shipping_provider || '');
    void loadShipmentTimeline(order.id);
  }, [order, loadShipmentTimeline]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const applyUpdated = (updated: AdminOrder) => {
    const next = mergeOrder(order, updated);
    onOrderChange(next);
    return next;
  };

  const copyCustomerAddress = async (address: string | undefined | null) => {
    const text = address?.trim();
    if (!text) {
      notify('err', 'Không có địa chỉ để sao chép');
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      notify('ok', 'Đã sao chép địa chỉ');
    } catch {
      notify('err', 'Không sao chép được — kiểm tra quyền trình duyệt');
    }
  };

  const handleConsultationToggle = async (checked: boolean) => {
    setConsultSaving(true);
    try {
      const updated = await adminOrderAPI.updateOrder(order.id, { staff_consultation_contacted: checked });
      applyUpdated({ ...order, ...updated, staff_consultation_contacted: !!updated.staff_consultation_contacted });
      notify('ok', checked ? 'Đã đánh dấu đã liên hệ tư vấn' : 'Đã bỏ đánh dấu');
    } catch (err: unknown) {
      notify('err', err instanceof Error ? err.message : 'Không cập nhật được cờ tư vấn');
    } finally {
      setConsultSaving(false);
    }
  };

  const handleUpdateStatus = async (status: string) => {
    try {
      const updated = await adminOrderAPI.updateOrder(order.id, { status });
      notify('ok', 'Đã cập nhật trạng thái');
      const next = applyUpdated(updated);
      void loadShipmentTimeline(next.id);
      onRefresh();
    } catch {
      notify('err', 'Lỗi cập nhật trạng thái');
    }
  };

  const handleOverrideShipping = async () => {
    const reason = overrideReason.trim();
    if (reason.length < 5) {
      notify('err', 'Nhập lý do ghi đè ít nhất 5 ký tự');
      return;
    }
    setOverrideBusy(true);
    try {
      const updated = await adminOrderAPI.updateOrder(order.id, {
        status: 'shipping',
        override_reason: reason,
      });
      applyUpdated(updated);
      setOverrideReason('');
      notify('ok', 'Đã ghi đè trạng thái và lưu nhật ký');
      onRefresh();
    } catch (err: unknown) {
      notify('err', err instanceof Error ? err.message : 'Không thể ghi đè trạng thái');
    } finally {
      setOverrideBusy(false);
    }
  };

  const handleClearCustoms = async () => {
    setClearCustomsBusy(true);
    try {
      const updated = await adminOrderAPI.clearCustomsShipment(order.id);
      notify('ok', '188.com.vn: Đã thông quan — hàng về shop đóng gói');
      const next = applyUpdated(updated);
      void loadShipmentTimeline(next.id);
      onRefresh();
    } catch (err: unknown) {
      notify('err', err instanceof Error ? err.message : 'Không thể cập nhật lịch trình');
    } finally {
      setClearCustomsBusy(false);
    }
  };

  const handleStartVietnamPacking = async () => {
    setStartPackingBusy(true);
    try {
      const updated = await adminOrderAPI.startVietnamPacking(order.id);
      notify('ok', 'Kho Việt Nam: Bắt đầu soạn hàng');
      const next = applyUpdated(updated);
      void loadShipmentTimeline(next.id);
      onRefresh();
    } catch (err: unknown) {
      notify('err', err instanceof Error ? err.message : 'Không thể bắt đầu đóng gói');
    } finally {
      setStartPackingBusy(false);
    }
  };

  const handleMarkOutForCustomerConfirm = async () => {
    setMarkOutForConfirmBusy(true);
    try {
      const updated = await adminOrderAPI.markOutForCustomerConfirm(order.id, {
        tracking_number: trackingNumber.trim() || undefined,
        shipping_provider: shippingProvider.trim() || undefined,
      });
      notify('ok', '188.com.vn: Đã đóng hàng & gửi shipper — khách có thể xác nhận nhận hàng');
      const next = applyUpdated(updated);
      void loadShipmentTimeline(next.id);
      onRefresh();
    } catch (err: unknown) {
      notify('err', err instanceof Error ? err.message : 'Không thể cập nhật lịch trình');
    } finally {
      setMarkOutForConfirmBusy(false);
    }
  };

  const handleRefundDeposit = async () => {
    try {
      await adminOrderAPI.refundDeposit(order.id, { refund_note: 'Khách yêu cầu hoàn cọc' });
      notify('ok', 'Đã duyệt hoàn cọc và thu hồi hoa hồng affiliate');
      onRefresh();
      onClose();
    } catch (err: unknown) {
      notify('err', err instanceof Error ? err.message : 'Lỗi duyệt hoàn cọc');
    }
  };

  const handleApproveReturn = async () => {
    try {
      const updated = await adminOrderAPI.approveReturnReceived(order.id, {
        note: 'Shop đã nhận hàng hoàn',
      });
      notify('ok', 'Đã ghi nhận đơn hoàn đã trả shop — hoa hồng affiliate đã hủy');
      applyUpdated(updated);
      onRefresh();
    } catch (err: unknown) {
      notify('err', err instanceof Error ? err.message : 'Không thể duyệt hoàn hàng');
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="admin-order-detail-title"
        className="relative flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-xl bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-gray-100 bg-white px-6 py-4">
          <h2 id="admin-order-detail-title" className="min-w-0 flex-1 text-xl font-bold leading-tight text-gray-900 pr-2">
            Chi tiết đơn hàng
          </h2>
          <button
            type="button"
            aria-label="Đóng"
            onClick={onClose}
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
              <p className="font-semibold text-lg tracking-wide">{order.order_code}</p>
              <p className="text-xs text-gray-500 mt-1">ID đơn nội bộ: #{order.id}</p>
              <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm text-gray-800">
                <input
                  type="checkbox"
                  checked={!!order.staff_consultation_contacted}
                  disabled={consultSaving}
                  onChange={(e) => void handleConsultationToggle(e.target.checked)}
                  className="h-4 w-4 rounded border-gray-300 text-[#ea580c] focus:ring-[#ea580c] cursor-pointer disabled:opacity-50"
                />
                <span title="Nhân viên chốt đơn đã liên hệ tư vấn khách">Đã liên hệ tư vấn khách</span>
              </label>
              <p className="text-sm text-gray-600 mt-2">{formatDate(order.created_at)}</p>
            </div>
            <div className="min-w-0">
              <p className="text-gray-500 text-sm">Khách hàng</p>
              <p className="font-medium">{order.customer_name}</p>
              <p className="text-sm">{order.customer_phone}</p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <p className="text-gray-500 text-sm">Địa chỉ nhận hàng</p>
                <button
                  type="button"
                  onClick={() => void copyCustomerAddress(order.customer_address)}
                  disabled={!order.customer_address?.trim()}
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
                {order.customer_address?.trim() || <span className="text-gray-400 italic">Chưa có địa chỉ</span>}
              </p>
              <p className="text-sm mt-2">
                {STATUS_TEXTS[order.status]} / {PAYMENT_TEXTS[order.payment_status] || order.payment_status}
              </p>
            </div>
          </div>
          <div className="rounded-lg border border-amber-200 bg-amber-50/70 p-4 mb-4">
            <p className="text-sm font-semibold text-amber-900 mb-3">Thanh toán</p>
            <dl className="grid gap-2 text-sm">
              <div className="flex flex-wrap justify-between gap-x-4 gap-y-1">
                <dt className="text-gray-600">Tổng đơn</dt>
                <dd className="font-semibold text-gray-900 tabular-nums">{formatVnd(parseMoney(order.total_amount))}</dd>
              </div>
              {adminOrderExpectsDeposit(order) ? (
                <div className="flex flex-wrap justify-between gap-x-4 gap-y-1 items-baseline">
                  <dt className="text-gray-600 shrink-0">Đặt cọc</dt>
                  <dd className="font-medium text-gray-900 text-right tabular-nums">
                    <span>Cần: {formatVnd(depositRequiredDisplay(order))}</span>
                    <span className="text-gray-400 font-normal mx-1.5">·</span>
                    <span className={parseMoney(order.deposit_paid) > 0 ? 'text-emerald-700' : undefined}>
                      Đã cọc: {formatVnd(parseMoney(order.deposit_paid))}
                    </span>
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
                  {adminOrderExpectsDeposit(order) && (
                    <span className="text-gray-500 font-normal hidden sm:inline"> (sau cọc)</span>
                  )}
                </dt>
                <dd className="font-semibold text-red-700 tabular-nums">{formatVnd(amountDueOnDelivery(order))}</dd>
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
                {(order.items || []).map((item) => {
                  const href = productPublicUrl(item.product_slug);
                  const rawImageUrl = orderItemImageLink(item);
                  const skuLabel = orderItemSkuLabel(item);
                  return (
                    <tr key={item.id} className="border-b align-top">
                      <td className="py-2 pr-2 align-middle">
                        {rawImageUrl ? (
                          <a
                            href={rawImageUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            title="Mở ảnh biến thể"
                            className="inline-block rounded-lg ring-offset-2 hover:ring-2 hover:ring-blue-300"
                          >
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                              src={orderItemImageUrl(item.product_image)}
                              alt=""
                              className="block w-32 h-32 shrink-0 aspect-square rounded-lg object-cover border border-gray-100 bg-gray-50"
                              width={128}
                              height={128}
                              referrerPolicy="no-referrer"
                            />
                          </a>
                        ) : (
                          /* eslint-disable-next-line @next/next/no-img-element */
                          <img
                            src={orderItemImageUrl(item.product_image)}
                            alt=""
                            className="block w-32 h-32 shrink-0 aspect-square rounded-lg object-cover border border-gray-100 bg-gray-50"
                            width={128}
                            height={128}
                            referrerPolicy="no-referrer"
                          />
                        )}
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
                          {skuLabel ? <p>Mã SP (SKU): {skuLabel}</p> : null}
                          <OrderItemVariantMeta item={item} className="space-y-0.5" />
                          {externalLinkLine('Link Trung Quốc', item.product_url)}
                          {href ? (
                            externalLinkLine('Link shop', href)
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
          <div className="mb-4 rounded-lg border border-blue-100 bg-blue-50/60 p-4">
            <h3 className="font-semibold text-blue-900 mb-2">
              {shipmentTimeline?.timeline_variant === 'vn_domestic'
                ? 'Đóng gói & giao hàng từ kho Việt Nam'
                : 'Lịch trình 188.com.vn TQ → VN'}
            </h3>
            {shipmentLoading ? (
              <p className="text-sm text-gray-500">Đang tải lịch trình…</p>
            ) : shipmentTimeline?.events?.length ? (
              <ul className="space-y-2 mb-4">
                {shipmentTimeline.events.map((ev) => (
                  <li key={ev.step_key} className="flex items-start gap-2 text-sm">
                    <span
                      className={`mt-1 h-2 w-2 shrink-0 rounded-full ${
                        ev.status === 'completed' ? 'bg-green-500' : ev.status === 'active' ? 'bg-[#ea580c]' : 'bg-gray-300'
                      }`}
                    />
                    <span className={ev.status === 'active' ? 'font-medium text-[#ea580c]' : 'text-gray-700'}>{ev.title}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-gray-500 mb-4">Chưa có lịch trình (đơn chưa đặt cọc hoặc chưa khởi tạo).</p>
            )}
            {shipmentTimeline?.ems_tracking?.available ? (
              <div className="mb-4 rounded-lg border border-indigo-100 bg-white p-3">
                <p className="text-sm font-semibold text-indigo-900">Hành trình EMS</p>
                {shipmentTimeline.ems_tracking.current_status_description ? (
                  <p className="mt-1 text-xs text-indigo-700">Mới nhất: {shipmentTimeline.ems_tracking.current_status_description}</p>
                ) : null}
                {shipmentTimeline.ems_tracking.error ? (
                  <p className="mt-2 text-xs text-amber-800">{shipmentTimeline.ems_tracking.error}</p>
                ) : shipmentTimeline.ems_tracking.events.length ? (
                  <ul className="mt-2 space-y-1.5">
                    {shipmentTimeline.ems_tracking.events.slice(0, 5).map((ev, idx) => (
                      <li key={`${ev.description}-${ev.traced_at || idx}`} className="text-xs text-gray-700">
                        <span className="font-medium">{ev.description}</span>
                        {ev.traced_at ? (
                          <span className="text-gray-500"> — {new Date(ev.traced_at).toLocaleString('vi-VN')}</span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-2 text-xs text-gray-500">Chưa có cập nhật từ EMS.</p>
                )}
              </div>
            ) : null}
            {shipmentTimeline?.waiting_admin_at_customs ? (
              <div className="rounded-lg border border-amber-200 bg-white p-3 space-y-3">
                <p className="text-sm text-amber-900">188.com.vn đang xử lý thủ tục cửa khẩu</p>
                <p className="text-xs text-amber-800/80">
                  Khi hàng đã thông quan và chuyển về shop, bấm bên dưới để cập nhật lịch trình cho khách.
                </p>
                <button
                  type="button"
                  disabled={clearCustomsBusy}
                  onClick={() => void handleClearCustoms()}
                  className="px-4 py-2 bg-[#ea580c] text-white rounded-lg text-sm font-medium hover:bg-[#c2410c] disabled:opacity-60"
                >
                  {clearCustomsBusy ? 'Đang xử lý…' : '188.com.vn: Đã thông quan — hàng về shop'}
                </button>
              </div>
            ) : null}
            {shipmentTimeline?.timeline_variant === 'vn_domestic' && shipmentTimeline.current_step_key === 'vn_picking' ? (
              <div className="rounded-lg border border-sky-200 bg-white p-3 space-y-3">
                <p className="text-sm text-sky-900">Kho Việt Nam: lấy và kiểm tra hàng</p>
                <p className="text-xs text-sky-800/80">
                  Kiểm đúng SKU, size, màu, số lượng và tình trạng sản phẩm trước khi đóng gói.
                </p>
                <button
                  type="button"
                  disabled={startPackingBusy}
                  onClick={() => void handleStartVietnamPacking()}
                  className="px-4 py-2 bg-[#ea580c] text-white rounded-lg text-sm font-medium hover:bg-[#c2410c] disabled:opacity-60"
                >
                  {startPackingBusy ? 'Đang xử lý…' : 'Bắt đầu soạn hàng'}
                </button>
              </div>
            ) : null}
            {shipmentTimeline?.waiting_admin_domestic_delivery ? (
              <div className="rounded-lg border border-emerald-200 bg-white p-3 space-y-3">
                <p className="text-sm text-emerald-900">
                  {shipmentTimeline.timeline_variant === 'vn_domestic'
                    ? 'Hàng đã kiểm tra — đóng gói & gửi shipper'
                    : 'Hàng đã về shop — đóng gói & gửi shipper'}
                </p>
                <p className="text-xs text-emerald-800/80">
                  Sau khi nhân viên đóng hàng và bàn giao cho shipper, xác nhận bên dưới để mở nút «Đã nhận hàng» cho khách.
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <label className="block text-xs">
                    <span className="text-gray-600">Đơn vị giao nội địa (tuỳ chọn)</span>
                    <input
                      value={shippingProvider}
                      onChange={(e) => setShippingProvider(e.target.value)}
                      placeholder="VD: EMS, Viettel Post, GHN…"
                      className="mt-1 w-full rounded border border-gray-200 px-2 py-1.5 text-sm"
                    />
                  </label>
                  <label className="block text-xs">
                    <span className="text-gray-600">Mã vận đơn VN (tuỳ chọn)</span>
                    <input
                      value={trackingNumber}
                      onChange={(e) => setTrackingNumber(e.target.value)}
                      placeholder="VD: EM123456789VN"
                      className="mt-1 w-full rounded border border-gray-200 px-2 py-1.5 text-sm"
                    />
                  </label>
                </div>
                <button
                  type="button"
                  disabled={markOutForConfirmBusy}
                  onClick={() => void handleMarkOutForCustomerConfirm()}
                  className="px-4 py-2 bg-[#ea580c] text-white rounded-lg text-sm font-medium hover:bg-[#c2410c] disabled:opacity-60"
                >
                  {markOutForConfirmBusy
                    ? 'Đang xử lý…'
                    : shipmentTimeline.timeline_variant === 'vn_domestic'
                      ? 'Đã đóng gói & bàn giao shipper'
                      : '188.com.vn: Đóng hàng & gửi shipper'}
                </button>
              </div>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2 pt-4 border-t">
            {order.status === 'waiting_deposit' && depositRequiredDisplay(order) > 0 && onRequestDepositConfirm ? (
              <button
                type="button"
                onClick={() => onRequestDepositConfirm(order)}
                className="px-4 py-2 bg-[#ea580c] text-white rounded-lg hover:bg-[#c2410c]"
              >
                Xác nhận cọc
              </button>
            ) : null}
            {(order.status === 'deposit_paid' || order.status === 'confirmed' || order.status === 'processing') &&
            !shipmentTimeline?.events?.length ? (
              <div className="w-full rounded-lg border border-amber-200 bg-amber-50 p-3">
                <label className="block text-sm font-medium text-amber-900">
                  Ghi đè trạng thái khi timeline bị thiếu
                  <textarea
                    value={overrideReason}
                    onChange={(event) => setOverrideReason(event.target.value)}
                    placeholder="Lý do bắt buộc; nội dung được lưu vào nhật ký đơn"
                    className="mt-2 min-h-20 w-full rounded-lg border border-amber-200 bg-white px-3 py-2 text-sm text-gray-900"
                  />
                </label>
                <button
                  type="button"
                  disabled={overrideBusy}
                  onClick={() => void handleOverrideShipping()}
                  className="mt-2 rounded-lg bg-amber-700 px-4 py-2 text-sm font-medium text-white hover:bg-amber-800 disabled:opacity-60"
                >
                  {overrideBusy ? 'Đang lưu…' : 'Ghi đè sang đang giao'}
                </button>
              </div>
            ) : null}
            {order.status === 'delivered' && (
              <button
                type="button"
                onClick={() => void handleUpdateStatus('completed')}
                className="px-4 py-2 bg-[#ea580c] text-white rounded-lg hover:bg-[#c2410c]"
              >
                Hoàn thành
              </button>
            )}
            {!['cancelled', 'completed', 'returned'].includes(order.status) && (
              <button
                type="button"
                onClick={() => void handleUpdateStatus('cancelled')}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
              >
                Hủy đơn hàng
              </button>
            )}
            {parseMoney(order.deposit_paid) > 0 &&
              !['cancelled', 'completed', 'returned'].includes(order.status) &&
              order.payment_status !== 'refunded' && (
                <button
                  type="button"
                  onClick={() => void handleRefundDeposit()}
                  className="px-4 py-2 bg-red-50 text-red-700 border border-red-200 rounded-lg hover:bg-red-100"
                >
                  Duyệt hoàn cọc
                </button>
              )}
            {['shipping', 'delivered', 'completed'].includes(order.status) && (
              <button
                type="button"
                onClick={() => void handleApproveReturn()}
                className="px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700"
              >
                Xác nhận đơn hoàn đã trả shop
              </button>
            )}
            <button type="button" onClick={onClose} className="px-4 py-2 border rounded-lg hover:bg-gray-50">
              Đóng
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
