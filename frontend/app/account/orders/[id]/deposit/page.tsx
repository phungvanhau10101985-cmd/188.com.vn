'use client';

import { useState, useEffect, useMemo, useRef } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { apiClient } from '@/lib/api-client';
import type { BankAccountInfo } from '@/lib/api-client';
import { useToast } from '@/components/ToastProvider';
import { buildQrFromTemplate } from '@/lib/deposit-qr';

interface Order {
  id: number;
  order_code: string;
  customer_phone?: string;
  deposit_amount?: number | string;
  deposit_paid?: number | string;
  remaining_amount?: number | string;
  total_amount?: number | string;
  subtotal?: number | string;
  shipping_fee?: number | string;
  discount_amount?: number | string;
  status: string;
  requires_deposit?: boolean;
}

function orderMoney(
  order: Order,
  key: 'total_amount' | 'deposit_amount' | 'deposit_paid' | 'remaining_amount'
): number {
  const v = order[key];
  if (v == null) return 0;
  if (typeof v === 'number') return Number.isFinite(v) ? v : 0;
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

// --- Helper Components ---

const InfoRow = ({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) => (
  <div className="flex justify-between items-center text-sm">
    <span className="text-gray-500">{label}</span>
    <span className={`font-medium text-gray-800 ${valueClass}`}>{value}</span>
  </div>
);

const CopyButton = ({ textToCopy, children }: { textToCopy: string; children: React.ReactNode }) => {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 2000);
    return () => clearTimeout(timer);
  }, [copied]);

  const handleCopy = () => {
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      navigator.clipboard.writeText(textToCopy);
      setCopied(true);
    }
  };

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="shrink-0 px-4 py-2 bg-orange-600 text-white text-sm font-semibold rounded-lg hover:bg-orange-700 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
    >
      {copied ? (
        <>
          <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" /></svg>
          <span>Đã chép</span>
        </>
      ) : (
        children
      )}
    </button>
  );
};


// --- Main Component ---

export default function OrderDepositPage() {
  const params = useParams();
  const id = Number(params?.id);
  const [order, setOrder] = useState<Order | null>(null);
  const [bankAccounts, setBankAccounts] = useState<BankAccountInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedAccount, setSelectedAccount] = useState<BankAccountInfo | null>(null);
  const [depositOption, setDepositOption] = useState<'30' | '100'>('30');
  const [updatingDeposit, setUpdatingDeposit] = useState(false);
  const [sepayInfo, setSepayInfo] = useState<{
    enabled: boolean;
    transfer_content: string;
    qr_image_url?: string | null;
    register_webhook_url?: string | null;
    bank_code?: string | null;
    account_number?: string | null;
  } | null>(null);
  const { pushToast } = useToast();
  const prevStatusRef = useRef<string | null>(null);

  const formatVnd = (n: number) => new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(n);
  
  // Nội dung CK: từ API (trùng `des` QR + webhook). Fallback hiển thị SEVQR + mã đơn (mặc định backend).
  const transferContent = useMemo(() => {
    if (sepayInfo?.transfer_content) return sepayInfo.transfer_content;
    if (!order) return '';
    const code = (order.order_code || '').trim();
    return code ? `SEVQR ${code}` : '';
  }, [order, sepayInfo?.transfer_content]);

  const qrValue = useMemo(() => {
    if (sepayInfo?.enabled && sepayInfo.qr_image_url) return sepayInfo.qr_image_url;
    if (!order || !selectedAccount) return '';
    const tpl = selectedAccount.qr_template_url;
    const bankId = (selectedAccount.bank_code || selectedAccount.bank_short_name || '').trim();
    if (tpl && bankId) {
      const built = buildQrFromTemplate(tpl, {
        bank_acc: selectedAccount.account_number,
        bank_id: bankId,
        amount: order.deposit_amount ?? 0,
        des: transferContent,
      });
      if (built) return built;
    }
    return `https://img.vietqr.io/image/${selectedAccount.bank_short_name}-${selectedAccount.account_number}-compact2.png?amount=${order.deposit_amount}&addInfo=${encodeURIComponent(transferContent)}&accountName=${encodeURIComponent(selectedAccount.account_holder || '')}`;
  }, [sepayInfo, order, selectedAccount, transferContent]);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    apiClient
      .getOrder(id)
      .then(setOrder)
      .catch(() => setOrder(null))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    if (!id || !order || order.status !== 'waiting_deposit' || !order.requires_deposit) {
      setSepayInfo(null);
      return;
    }
    apiClient
      .getOrderSepayDepositInfo(id)
      .then(setSepayInfo)
      .catch(() => setSepayInfo(null));
  }, [id, order?.id, order?.status, order?.requires_deposit]);

  useEffect(() => {
    if (!order) return;
    const t = (order as { deposit_type?: string }).deposit_type ?? '';
    setDepositOption(t === 'percent_100' ? '100' : '30');
  }, [order]);

  useEffect(() => {
    if (!order) return;
    const wasWaiting = prevStatusRef.current === 'waiting_deposit';
    const nowDone = order.status === 'deposit_paid' || order.status === 'confirmed';
    if (wasWaiting && nowDone) {
      pushToast({
        title: 'Đã xác nhận thanh toán cọc',
        description: 'Cảm ơn quý khách. Email xác nhận đã được gửi tới hộp thư của bạn (nếu có).',
        variant: 'success',
        durationMs: 6000,
      });
    }
    prevStatusRef.current = order.status;
  }, [order, pushToast]);

  useEffect(() => {
    if (!id || !order || order.status !== 'waiting_deposit' || !order.requires_deposit) return;
    const iv = setInterval(() => {
      apiClient
        .getOrder(id)
        .then((o) => setOrder(o as Order))
        .catch(() => {});
    }, 4000);
    return () => clearInterval(iv);
  }, [id, order?.status, order?.requires_deposit]);

  useEffect(() => {
    if (order?.requires_deposit && order?.status === 'waiting_deposit') {
      apiClient.getBankAccounts()
        .then(accounts => {
          setBankAccounts(accounts);
          if (accounts.length > 0) {
            setSelectedAccount(accounts[0]);
          }
        })
        .catch(() => setBankAccounts([]));
    }
  }, [order]);

  const handleDepositTypeChange = async (option: '30' | '100') => {
    if (!order || order.status !== 'waiting_deposit' || option === depositOption) return;
    setUpdatingDeposit(true);
    try {
      await apiClient.updateOrderDepositType(order.id, option === '100' ? 'percent_100' : 'percent_30');
      setDepositOption(option);
      const updated = await apiClient.getOrder(order.id);
      setOrder(updated as Order);
      try {
        const s = await apiClient.getOrderSepayDepositInfo(order.id);
        setSepayInfo(s);
      } catch {
        setSepayInfo(null);
      }
      pushToast({ title: 'Đã cập nhật mức cọc', variant: 'success', durationMs: 2500 });
    } catch (e) {
      pushToast({ title: 'Không thể đổi mức cọc', description: (e as Error).message || 'Vui lòng thử lại', variant: 'error', durationMs: 3000 });
    } finally {
      setUpdatingDeposit(false);
    }
  };

  // --- Render Logic ---

  if (loading) {
    return (
      <div className="min-h-[50vh] flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-orange-500 border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-gray-600 mt-4">Đang tải thông tin đơn hàng...</p>
        </div>
      </div>
    );
  }

  if (!order) {
    return (
      <div className="py-16 text-center bg-gray-50">
        <p className="text-gray-600 text-lg">Không tìm thấy đơn hàng.</p>
        <Link href="/account/orders" className="text-orange-600 hover:underline mt-4 inline-block font-medium">
          Quay lại danh sách đơn hàng
        </Link>
      </div>
    );
  }

  if (!order.requires_deposit) {
    return (
      <div className="py-16 text-center bg-gray-50 px-4">
        <p className="text-gray-600 text-lg">Đơn hàng này không yêu cầu đặt cọc.</p>
        <Link href={`/account/orders/${order.id}`} className="text-orange-600 hover:underline mt-4 inline-block font-medium">
          Xem chi tiết đơn hàng
        </Link>
      </div>
    );
  }

  const depositConfirmed = order.status === 'deposit_paid' || order.status === 'confirmed';

  if (depositConfirmed) {
    const statusLabel = order.status === 'confirmed' ? 'Đã xác nhận đơn (cọc 100%)' : 'Đã đặt cọc';
    return (
      <div className="bg-gray-50 min-h-0 pt-0 pb-6 md:pb-8">
        <div className="mx-auto px-3 sm:px-4 max-w-2xl">
          <div className="bg-white rounded-xl shadow-md border border-gray-200 overflow-hidden">
            <div className="bg-gradient-to-r from-emerald-600 to-teal-600 text-white px-4 py-5 md:px-6">
              <div className="flex items-start gap-3">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white/20" aria-hidden>
                  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                </span>
                <div>
                  <h1 className="text-lg md:text-xl font-bold">Xác nhận đơn hàng</h1>
                  <p className="text-emerald-50 text-sm mt-1">
                    Cảm ơn quý khách đã thanh toán đặt cọc. Chúng tôi đã ghi nhận và gửi email xác nhận tới bạn.
                  </p>
                </div>
              </div>
            </div>
            <div className="p-4 md:p-6 space-y-4">
              <div className="rounded-lg border border-emerald-100 bg-emerald-50/80 px-4 py-3 text-sm text-emerald-950">
                <p className="font-semibold">Mã đơn: #{order.order_code}</p>
                <p className="mt-1">Trạng thái: <strong>{statusLabel}</strong></p>
                <p className="mt-1 tabular-nums">
                  Số tiền cọc đã nhận:{' '}
                  <strong>
                    {formatVnd(
                      orderMoney(order, 'deposit_paid') > 0
                        ? orderMoney(order, 'deposit_paid')
                        : orderMoney(order, 'deposit_amount')
                    )}
                  </strong>
                  {order.status === 'deposit_paid' && (
                    <span className="block text-emerald-900/90 mt-0.5 text-xs">
                      Số còn lại khi nhận hàng: {formatVnd(orderMoney(order, 'remaining_amount'))}
                    </span>
                  )}
                </p>
              </div>
              <p className="text-sm text-gray-600 leading-relaxed">
                Đội ngũ 188.com.vn sẽ xử lý đơn và liên hệ khi cần. Quý khách có thể theo dõi tiến độ trong mục chi tiết đơn hàng.
              </p>
              <div className="flex flex-col sm:flex-row gap-2 pt-2">
                <Link
                  href={`/account/orders/${order.id}`}
                  className="inline-flex justify-center items-center px-4 py-2.5 rounded-lg bg-orange-600 text-white text-sm font-semibold hover:bg-orange-700"
                >
                  Xem chi tiết đơn hàng
                </Link>
                <Link
                  href="/account/orders"
                  className="inline-flex justify-center items-center px-4 py-2.5 rounded-lg border border-gray-300 text-gray-800 text-sm font-medium hover:bg-gray-50"
                >
                  Danh sách đơn hàng
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (order.status !== 'waiting_deposit') {
    return (
      <div className="py-16 text-center bg-gray-50 px-4">
        <p className="text-gray-600 text-lg">Đơn hàng không ở trạng thái chờ cọc.</p>
        <Link href={`/account/orders/${order.id}`} className="text-orange-600 hover:underline mt-4 inline-block font-medium">
          Xem chi tiết đơn hàng
        </Link>
      </div>
    );
  }

  return (
    <div className="bg-gray-50 min-h-0 pt-0 pb-3 md:pb-4">
      <div className="mx-auto px-0 sm:px-1 max-w-5xl">
        <div className="bg-white rounded-xl shadow-md border border-gray-200 overflow-hidden">
          {/* Header */}
          <div className="bg-gradient-to-r from-orange-600 to-amber-500 text-white px-4 py-3 md:px-5">
            <h1 className="text-lg md:text-xl font-bold leading-tight">Thanh toán cọc đơn hàng</h1>
            <p className="text-orange-100 text-xs md:text-sm mt-0.5">Mã đơn: #{order.order_code}</p>
          </div>

          {/* Tóm tắt tiền — gọn, một khối */}
          <div className="px-3 py-2.5 md:px-5 md:py-3 bg-amber-50/90 border-b border-amber-100/90">
            <div className="rounded-lg border border-amber-200/70 bg-white/80 grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-amber-100 overflow-hidden">
              <div className="px-3 py-2 text-center sm:text-left">
                <p className="text-[10px] sm:text-xs text-amber-900/70 font-medium uppercase tracking-wide">Tổng đơn</p>
                <p className="text-base sm:text-lg font-bold text-gray-900 tabular-nums leading-tight">
                  {formatVnd(orderMoney(order, 'total_amount'))}
                </p>
                <p className="text-[10px] text-gray-500 mt-0.5 hidden sm:block">Gồm ship nếu có</p>
              </div>
              <div className="px-3 py-2 text-center sm:text-left bg-orange-50/40">
                <p className="text-[10px] sm:text-xs text-orange-900/80 font-medium uppercase tracking-wide">Cần cọc</p>
                <p className="text-base sm:text-lg font-bold text-orange-600 tabular-nums leading-tight">
                  {formatVnd(orderMoney(order, 'deposit_amount'))}
                </p>
                <p className="text-[10px] text-orange-800/80 mt-0.5 hidden sm:block">Chuyển khoản ngay</p>
              </div>
              <div className="px-3 py-2 text-center sm:text-left">
                <p className="text-[10px] sm:text-xs text-amber-900/70 font-medium uppercase tracking-wide">Khi nhận hàng</p>
                <p className="text-base sm:text-lg font-bold text-gray-900 tabular-nums leading-tight">
                  {formatVnd(orderMoney(order, 'remaining_amount'))}
                </p>
                <p className="text-[10px] text-gray-500 mt-0.5 hidden sm:block">Còn lại sau cọc</p>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-0 lg:divide-x lg:divide-gray-100">
            {/* Cột trái: mức cọc + chọn NH + STK + nội dung CK (lấp khoảng trắng) */}
            <div className="lg:col-span-5 p-3 md:p-4 space-y-3 order-2 lg:order-1 border-t lg:border-t-0 border-gray-100">
              <div className="rounded-lg border border-gray-200 p-3 bg-white">
                <p className="text-gray-800 font-semibold text-sm mb-2">Chọn mức cọc</p>
                <div className="flex flex-wrap gap-4">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="deposit_option"
                      checked={depositOption === '30'}
                      onChange={() => handleDepositTypeChange('30')}
                      disabled={updatingDeposit}
                      className="text-orange-600"
                    />
                    <span className="text-gray-800">Cọc 30%</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="deposit_option"
                      checked={depositOption === '100'}
                      onChange={() => handleDepositTypeChange('100')}
                      disabled={updatingDeposit}
                      className="text-orange-600"
                    />
                    <span className="text-gray-800">Cọc 100%</span>
                  </label>
                </div>
                {updatingDeposit && <p className="text-xs text-orange-600 mt-1.5">Đang cập nhật...</p>}
              </div>

              <div>
                <p className="text-gray-800 font-semibold text-sm mb-2">Ngân hàng thụ hưởng</p>

                <div className="md:hidden mb-2">
                  <select
                    onChange={(e) => setSelectedAccount(bankAccounts.find(acc => acc.id === Number(e.target.value)) || null)}
                    className="w-full py-2 px-3 border border-gray-200 rounded-lg bg-white text-gray-900 text-sm"
                    aria-label="Chọn ngân hàng"
                  >
                    {bankAccounts.map(acc => (
                      <option key={acc.id} value={acc.id}>{acc.bank_name} — {acc.account_number}</option>
                    ))}
                  </select>
                </div>

                <div className="hidden md:flex flex-wrap gap-1.5 mb-2">
                  {bankAccounts.map(acc => (
                    <button
                      key={acc.id}
                      type="button"
                      onClick={() => setSelectedAccount(acc)}
                      className={`px-2.5 py-1.5 text-sm rounded-lg border transition-colors ${
                        selectedAccount?.id === acc.id
                          ? 'bg-orange-600 text-white border-orange-600 shadow-sm'
                          : 'bg-white text-gray-700 border-gray-200 hover:border-orange-300'
                      }`}
                    >
                      {acc.bank_short_name || acc.bank_name}
                    </button>
                  ))}
                </div>

                {sepayInfo?.enabled && sepayInfo.account_number && (
                  <div className="mb-2 p-2 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-950 leading-snug">
                    QR SePay: <span className="font-mono font-semibold">{sepayInfo.bank_code} · {sepayInfo.account_number}</span>
                    {selectedAccount && selectedAccount.account_number !== sepayInfo.account_number && (
                      <span className="block mt-0.5 text-amber-900">Chuyển đúng STK trên QR.</span>
                    )}
                  </div>
                )}

                <div className="rounded-lg bg-blue-50/90 border border-blue-100 px-3 py-2">
                  <p className="text-blue-900 text-xs leading-snug">
                    Quét QR bên phải → đối chiếu STK và nội dung CK ngay dưới. SePay xác nhận nhanh; không thì shop đối soát tay.
                  </p>
                </div>
              </div>

              <div className="space-y-3 min-w-0">
                {selectedAccount ? (
                  <div className="rounded-lg border border-gray-200 bg-white p-3 space-y-1.5">
                    <InfoRow label="Ngân hàng" value={selectedAccount.bank_name} />
                    <InfoRow label="Số tài khoản" value={selectedAccount.account_number} valueClass="font-mono" />
                    <InfoRow label="Chủ tài khoản" value={selectedAccount.account_holder} />
                    {selectedAccount.branch ? <InfoRow label="Chi nhánh" value={selectedAccount.branch} /> : null}
                    <div className="pt-1">
                      <CopyButton textToCopy={selectedAccount.account_number}>
                        <span className="text-sm">Chép STK</span>
                      </CopyButton>
                    </div>
                  </div>
                ) : null}

                {transferContent ? (
                  <div className="rounded-lg border border-gray-200 bg-white p-3">
                    <p className="text-gray-800 font-semibold text-sm mb-1.5">Nội dung chuyển khoản</p>
                    <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                      <span className="font-mono text-sm md:text-base font-bold text-gray-900 bg-gray-100 px-3 py-2 rounded-lg border border-gray-100 flex-1 min-w-0 break-all">
                        {transferContent}
                      </span>
                      <CopyButton textToCopy={transferContent}>
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path d="M7 9a2 2 0 012-2h6a2 2 0 012 2v6a2 2 0 01-2 2H9a2 2 0 01-2-2V9z" /><path d="M5 3a2 2 0 00-2 2v6a2 2 0 002 2V5h6a2 2 0 00-2-2H5z" /></svg>
                        <span>Chép</span>
                      </CopyButton>
                    </div>
                    <p className="text-[11px] text-gray-500 mt-1.5 leading-snug">
                      Ghi đúng nội dung để xác nhận tự động (SePay).
                    </p>
                  </div>
                ) : null}
              </div>

              {sepayInfo?.enabled && sepayInfo.register_webhook_url && (
                <p className="text-[11px] text-gray-500 leading-snug">
                  Webhook: <span className="font-mono break-all">{sepayInfo.register_webhook_url}</span>
                </p>
              )}
            </div>

            {/* Cột phải: chỉ QR */}
            <div className="lg:col-span-7 p-3 md:p-4 order-1 lg:order-2 bg-gray-50/50 lg:bg-white flex flex-col items-center justify-start">
              <p className="text-gray-800 font-semibold text-sm mb-3 w-full text-center lg:text-left">Mã QR chuyển khoản</p>
              {qrValue ? (
                <>
                  <div className="rounded-xl bg-white p-2 md:p-3 shadow border border-gray-200">
                    <img
                      src={qrValue}
                      alt="Mã QR chuyển khoản"
                      className="w-[min(100%,240px)] h-[min(100%,240px)] sm:w-64 sm:h-64 md:w-72 md:h-72 object-contain"
                      width={288}
                      height={288}
                    />
                  </div>
                  <p className="text-[11px] text-gray-500 mt-1.5 text-center max-w-[280px] leading-snug">
                    Quét mã bằng app ngân hàng.
                  </p>
                </>
              ) : (
                <p className="text-sm text-gray-500 text-center py-8">Chọn tài khoản để hiển thị mã QR.</p>
              )}
            </div>
          </div>

          <div className="p-3 md:p-4 bg-gray-50 border-t border-gray-100">
            <Link
              href="/account/orders"
              className="block w-full max-w-md mx-auto py-2.5 text-center text-sm font-semibold rounded-lg bg-gray-800 text-white hover:bg-gray-900 transition-colors"
            >
              Quay lại danh sách đơn hàng
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
