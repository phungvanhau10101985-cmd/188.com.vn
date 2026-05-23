'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { apiClient } from '@/lib/api-client';
import { useToast } from '@/components/ToastProvider';
import AffiliateLinkConverter from '@/components/affiliate/AffiliateLinkConverter';

function fmt(amount: number) {
  return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(amount || 0);
}

function bucketLabel(bucket?: string | null) {
  if (bucket === 'withdrawable') return 'Có thể rút';
  if (bucket === 'pending') return 'Chờ giao hàng';
  if (bucket === 'both') return 'Chờ giao → Có thể rút';
  return null;
}

export default function WalletPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const { pushToast } = useToast();
  const [loading, setLoading] = useState(true);
  const [affiliate, setAffiliate] = useState<Awaited<ReturnType<typeof apiClient.getAffiliateMe>> | null>(null);
  const [transactions, setTransactions] = useState<Awaited<ReturnType<typeof apiClient.getWalletTransactions>>>([]);
  const [referredOrders, setReferredOrders] = useState<Awaited<ReturnType<typeof apiClient.getAffiliateReferredOrders>>>([]);
  const [referredOrdersLoading, setReferredOrdersLoading] = useState(false);
  const [referredOrdersSkip, setReferredOrdersSkip] = useState(0);
  const [referredOrdersHasMore, setReferredOrdersHasMore] = useState(false);
  const REFERRED_ORDERS_PAGE = 20;
  const [withdrawAmount, setWithdrawAmount] = useState('');
  const [withdrawing, setWithdrawing] = useState(false);
  const [copied, setCopied] = useState(false);
  const [applying, setApplying] = useState(false);
  const [socialLinksText, setSocialLinksText] = useState('');
  const [applicationNote, setApplicationNote] = useState('');

  const loadReferredOrders = useCallback(async (skip = 0, append = false) => {
    setReferredOrdersLoading(true);
    try {
      const rows = await apiClient.getAffiliateReferredOrders(skip, REFERRED_ORDERS_PAGE);
      setReferredOrders((prev) => (append ? [...prev, ...rows] : rows));
      setReferredOrdersSkip(skip + rows.length);
      setReferredOrdersHasMore(rows.length >= REFERRED_ORDERS_PAGE);
    } catch (err: any) {
      pushToast({
        title: 'Không tải được đơn giới thiệu',
        description: err?.message || 'Vui lòng thử lại',
        variant: 'error',
      });
    } finally {
      setReferredOrdersLoading(false);
    }
  }, [pushToast]);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [me, txs] = await Promise.all([
        apiClient.getAffiliateMe(),
        apiClient.getWalletTransactions(0, 30),
      ]);
      setAffiliate(me);
      setTransactions(txs);
      if (me.affiliate_status === 'approved') {
        await loadReferredOrders(0, false);
      } else {
        setReferredOrders([]);
        setReferredOrdersHasMore(false);
      }
    } catch (err: any) {
      pushToast({
        title: 'Không tải được ví',
        description: err?.message || 'Vui lòng thử lại',
        variant: 'error',
      });
    } finally {
      setLoading(false);
    }
  }, [pushToast, loadReferredOrders]);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/auth/login?redirect=/vi-dien-tu');
    }
  }, [isAuthenticated, isLoading, router]);

  useEffect(() => {
    if (!isLoading && isAuthenticated) void reload();
  }, [isAuthenticated, isLoading, reload]);

  const copyLink = async () => {
    if (!affiliate?.referral_link) return;
    try {
      await navigator.clipboard.writeText(affiliate.referral_link);
      setCopied(true);
      pushToast({ title: 'Đã copy link affiliate', variant: 'success', durationMs: 2000 });
      setTimeout(() => setCopied(false), 2000);
    } catch {
      pushToast({ title: 'Không copy được link', variant: 'error' });
    }
  };

  const handleWithdraw = async () => {
    const amount = Number(String(withdrawAmount).replace(/\D/g, ''));
    if (!amount || amount <= 0) {
      pushToast({ title: 'Nhập số tiền hợp lệ', variant: 'info' });
      return;
    }
    setWithdrawing(true);
    try {
      await apiClient.requestWalletWithdraw(amount);
      pushToast({ title: 'Đã gửi yêu cầu rút tiền', description: 'Admin sẽ duyệt trong thời gian sớm nhất.', variant: 'success' });
      setWithdrawAmount('');
      await reload();
    } catch (err: any) {
      pushToast({ title: 'Không thể rút tiền', description: err?.message || 'Vui lòng thử lại', variant: 'error' });
    } finally {
      setWithdrawing(false);
    }
  };

  const submitApplication = async () => {
    const social_links = socialLinksText
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);
    if (social_links.length === 0) {
      pushToast({ title: 'Nhập ít nhất một link mạng xã hội', variant: 'info' });
      return;
    }
    setApplying(true);
    try {
      await apiClient.submitAffiliateApplication({
        social_links,
        note: applicationNote.trim() || null,
      });
      pushToast({
        title: 'Đã gửi yêu cầu affiliate',
        description: 'Admin sẽ đánh giá hồ sơ và phê duyệt nếu phù hợp.',
        variant: 'success',
      });
      setSocialLinksText('');
      setApplicationNote('');
      await reload();
    } catch (err: any) {
      pushToast({ title: 'Không gửi được yêu cầu', description: err?.message || 'Vui lòng thử lại', variant: 'error' });
    } finally {
      setApplying(false);
    }
  };

  if (isLoading || loading) {
    return (
      <div className="min-h-[40vh] flex items-center justify-center">
        <div className="animate-spin w-10 h-10 border-4 border-[#ea580c] border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!affiliate) {
    return (
      <div className="bg-white rounded-xl border border-gray-100 p-6 text-center text-sm text-gray-600">
        Không tải được thông tin ví.{' '}
        <button type="button" onClick={() => void reload()} className="text-[#ea580c] underline font-medium">
          Thử lại
        </button>
      </div>
    );
  }

  const isApprovedAffiliate = affiliate.affiliate_status === 'approved';
  const application = affiliate.affiliate_application;

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
        <div className="bg-gradient-to-r from-[#ea580c] to-[#c2410c] text-white px-5 py-6">
          <h1 className="text-xl font-bold">Ví Affiliate</h1>
          <p className="text-sm text-white/90 mt-1">
            Hoa hồng {affiliate.commission_percent}% khi bạn bè mua qua link của bạn
          </p>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <div className="rounded-lg bg-white/15 px-3 py-2">
              <p className="text-xs text-white/80">Có thể rút</p>
              <p className="text-lg font-bold">{fmt(Number(affiliate.balance))}</p>
            </div>
            <div className="rounded-lg bg-white/15 px-3 py-2">
              <p className="text-xs text-white/80">Chờ giao hàng</p>
              <p className="text-lg font-bold">{fmt(Number(affiliate.pending_balance))}</p>
            </div>
          </div>
        </div>

        <div className="p-5 space-y-4">
          {!affiliate.affiliate_enabled ? (
            <div className="rounded-lg border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm text-yellow-800">
              Chương trình affiliate đang tạm tắt. Link của bạn vẫn xem được nhưng đơn mới sẽ chưa phát sinh hoa hồng.
            </div>
          ) : null}

          {isApprovedAffiliate ? (
            <div>
              <p className="text-sm font-medium text-gray-800 mb-2">Link affiliate của bạn</p>
              <div className="flex flex-col sm:flex-row gap-2">
                <input
                  readOnly
                  value={affiliate.referral_link}
                  className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm bg-gray-50"
                />
                <button
                  type="button"
                  onClick={() => void copyLink()}
                  className="rounded-lg bg-[#ea580c] text-white px-4 py-2 text-sm font-semibold hover:bg-[#c2410c]"
                >
                  {copied ? 'Đã copy' : 'Copy link'}
                </button>
              </div>
              <p className="text-xs text-gray-500 mt-2">
                Mã: <strong>{affiliate.referral_code}</strong> · Đơn giới thiệu: {affiliate.total_orders_referred} · Cookie:{' '}
                {affiliate.ref_cookie_days} ngày
              </p>
              <div className="mt-4">
                <AffiliateLinkConverter referralCode={affiliate.referral_code} />
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-orange-100 bg-orange-50 p-4 space-y-3">
              <div>
                <h2 className="font-semibold text-gray-900">Đăng ký làm affiliate</h2>
                <p className="text-sm text-gray-700 mt-1">
                  Tính năng affiliate cần được admin phê duyệt. Vui lòng gửi link mạng xã hội cá nhân để shop đánh giá.
                </p>
              </div>
              {application ? (
                <div className="rounded-lg bg-white/80 border border-orange-100 px-3 py-2 text-sm text-gray-700">
                  Trạng thái hồ sơ: <strong>{application.status === 'pending' ? 'Đang chờ duyệt' : 'Đã từ chối'}</strong>
                  {application.admin_note ? <p className="mt-1 text-red-600">Ghi chú admin: {application.admin_note}</p> : null}
                </div>
              ) : null}
              {application?.status !== 'pending' ? (
                <div className="space-y-3">
                  <label className="block">
                    <span className="text-sm font-medium text-gray-800">Link mạng xã hội cá nhân</span>
                    <textarea
                      value={socialLinksText}
                      onChange={(event) => setSocialLinksText(event.target.value)}
                      rows={4}
                      placeholder={'Mỗi dòng một link, ví dụ:\nhttps://facebook.com/...\nhttps://tiktok.com/@...'}
                      className="mt-1 w-full rounded-lg border border-orange-200 px-3 py-2 text-sm"
                    />
                  </label>
                  <label className="block">
                    <span className="text-sm font-medium text-gray-800">Ghi chú thêm (tuỳ chọn)</span>
                    <textarea
                      value={applicationNote}
                      onChange={(event) => setApplicationNote(event.target.value)}
                      rows={3}
                      placeholder="Bạn có thể mô tả kênh, tệp khách hàng, cách bạn dự định giới thiệu sản phẩm..."
                      className="mt-1 w-full rounded-lg border border-orange-200 px-3 py-2 text-sm"
                    />
                  </label>
                  <button
                    type="button"
                    disabled={applying}
                    onClick={() => void submitApplication()}
                    className="rounded-lg bg-[#ea580c] px-4 py-2 text-sm font-semibold text-white hover:bg-[#c2410c] disabled:opacity-60"
                  >
                    {applying ? 'Đang gửi…' : application ? 'Gửi lại hồ sơ' : 'Gửi yêu cầu xét duyệt'}
                  </button>
                </div>
              ) : null}
            </div>
          )}

          {affiliate.commission_policy ? (
            <div className="rounded-lg border border-gray-100 bg-gray-50 px-4 py-3 text-sm text-gray-700">
              {affiliate.commission_policy}
            </div>
          ) : null}

          {isApprovedAffiliate ? (
            <>
              <div className="rounded-lg border border-orange-100 bg-orange-50 px-4 py-3 text-sm text-gray-700">
                <strong>Có thể rút</strong> = đơn đã giao thành công.{' '}
                <strong>Chờ giao hàng</strong> = hoa hồng đã ghi nhận (sau đặt cọc hoặc khi đặt đơn không cọc) nhưng chưa rút được.
                Số dư ví có thể <strong>dùng mua hàng tại giỏ hàng</strong> hoặc{' '}
                <Link href="/tai-khoan-ngan-hang" className="text-[#ea580c] underline font-medium">
                  rút về ngân hàng
                </Link>{' '}
                (tối thiểu {fmt(Number(affiliate.min_withdrawal))}).
              </div>

              <div className="border-t border-gray-100 pt-4">
                <div className="mb-4 rounded-lg border border-green-200 bg-green-50 px-4 py-3">
                  <div className="flex flex-wrap items-end justify-between gap-3">
                    <div>
                      <p className="text-xs font-medium text-green-800">Số tiền có thể rút</p>
                      <p className="text-2xl font-bold text-green-900">{fmt(Number(affiliate.balance))}</p>
                    </div>
                    {Number(affiliate.pending_balance) > 0 ? (
                      <div className="text-right">
                        <p className="text-xs text-orange-700">Chờ giao hàng</p>
                        <p className="text-sm font-semibold text-orange-800">{fmt(Number(affiliate.pending_balance))}</p>
                      </div>
                    ) : null}
                  </div>
                </div>
                <label htmlFor="withdraw-amount" className="block text-sm font-medium text-gray-800 mb-2">
                  Rút tiền về ngân hàng
                </label>
                <div className="flex flex-col sm:flex-row gap-2">
                  <input
                    id="withdraw-amount"
                    inputMode="numeric"
                    value={withdrawAmount}
                    onChange={(e) => setWithdrawAmount(e.target.value)}
                    placeholder={`Tối thiểu ${fmt(Number(affiliate.min_withdrawal))}`}
                    className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  />
                  {Number(affiliate.balance) >= Number(affiliate.min_withdrawal) ? (
                    <button
                      type="button"
                      onClick={() => setWithdrawAmount(String(Math.floor(Number(affiliate.balance))))}
                      className="rounded-lg border border-green-300 bg-green-50 px-4 py-2 text-sm font-semibold text-green-800 hover:bg-green-100"
                    >
                      Rút tối đa
                    </button>
                  ) : null}
                  <button
                    type="button"
                    disabled={withdrawing || Number(affiliate.balance) < Number(affiliate.min_withdrawal)}
                    onClick={() => void handleWithdraw()}
                    className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-semibold hover:bg-gray-50 disabled:opacity-60"
                  >
                    {withdrawing ? 'Đang gửi…' : 'Gửi yêu cầu rút'}
                  </button>
                </div>
                {Number(affiliate.balance) > 0 && Number(affiliate.balance) < Number(affiliate.min_withdrawal) ? (
                  <p className="text-xs text-orange-600 mt-2">
                    Số dư chưa đủ mức rút tối thiểu ({fmt(Number(affiliate.min_withdrawal))}).
                  </p>
                ) : null}
                <p className="text-xs text-gray-500 mt-2">
                  Cần cập nhật{' '}
                  <Link href="/tai-khoan-ngan-hang" className="text-[#ea580c] underline">
                    tài khoản ngân hàng
                  </Link>{' '}
                  trước khi rút.
                </p>
              </div>
            </>
          ) : null}
        </div>
      </div>

      {isApprovedAffiliate ? (
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
          <div className="flex items-center justify-between gap-3 mb-3">
            <h2 className="font-semibold text-gray-900">Đơn giới thiệu</h2>
            <button
              type="button"
              onClick={() => void loadReferredOrders(0, false)}
              disabled={referredOrdersLoading}
              className="text-xs text-[#ea580c] underline font-medium disabled:opacity-60"
            >
              Làm mới
            </button>
          </div>
          <p className="text-xs text-gray-500 mb-4">
            Chỉ hiển thị mã đơn, trạng thái và hoa hồng — không hiện họ tên, SĐT, email hay địa chỉ khách.
          </p>
          {referredOrdersLoading && referredOrders.length === 0 ? (
            <div className="py-8 flex justify-center">
              <div className="animate-spin w-8 h-8 border-4 border-[#ea580c] border-t-transparent rounded-full" />
            </div>
          ) : referredOrders.length === 0 ? (
            <p className="text-sm text-gray-500">Chưa có đơn nào qua link của bạn.</p>
          ) : (
            <>
              <div className="hidden md:block overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-gray-500 border-b border-gray-100">
                      <th className="py-2 pr-3 font-medium">Ngày</th>
                      <th className="py-2 pr-3 font-medium">Mã đơn</th>
                      <th className="py-2 pr-3 font-medium">Người mua</th>
                      <th className="py-2 pr-3 font-medium">Sản phẩm</th>
                      <th className="py-2 pr-3 font-medium">Trạng thái đơn</th>
                      <th className="py-2 pr-3 font-medium">Hoa hồng</th>
                      <th className="py-2 font-medium">Trạng thái HH</th>
                    </tr>
                  </thead>
                  <tbody>
                    {referredOrders.map((row) => (
                      <tr key={row.order_id} className="border-b border-gray-50 align-top">
                        <td className="py-3 pr-3 text-gray-500 whitespace-nowrap">
                          {row.order_created_at ? new Date(row.order_created_at).toLocaleDateString('vi-VN') : '—'}
                        </td>
                        <td className="py-3 pr-3 font-medium text-gray-900">{row.order_code || `#${row.order_id}`}</td>
                        <td className="py-3 pr-3 text-gray-700">{row.buyer_label}</td>
                        <td className="py-3 pr-3 text-gray-600 max-w-[180px] truncate" title={row.product_summary}>
                          {row.product_summary}
                        </td>
                        <td className="py-3 pr-3 text-gray-700">{row.order_status_label}</td>
                        <td className="py-3 pr-3 font-semibold text-gray-900">{fmt(Number(row.commission_amount))}</td>
                        <td className="py-3">
                          <span
                            className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                              row.withdrawable
                                ? 'bg-green-100 text-green-800'
                                : row.commission_status === 'cancelled'
                                  ? 'bg-gray-100 text-gray-600'
                                  : row.commission_status === 'awaiting_deposit'
                                    ? 'bg-yellow-100 text-yellow-800'
                                    : 'bg-orange-100 text-orange-800'
                            }`}
                          >
                            {row.commission_status_label}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <ul className="md:hidden divide-y divide-gray-100">
                {referredOrders.map((row) => (
                  <li key={row.order_id} className="py-3 space-y-1 text-sm">
                    <p className="text-xs text-gray-400">
                      {row.order_created_at ? new Date(row.order_created_at).toLocaleString('vi-VN') : ''}
                    </p>
                    <div className="flex items-start justify-between gap-2">
                      <p className="font-semibold text-gray-900">{row.order_code || `#${row.order_id}`}</p>
                      <span
                        className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${
                          row.withdrawable
                            ? 'bg-green-100 text-green-800'
                            : row.commission_status === 'cancelled'
                              ? 'bg-gray-100 text-gray-600'
                              : row.commission_status === 'awaiting_deposit'
                                ? 'bg-yellow-100 text-yellow-800'
                                : 'bg-orange-100 text-orange-800'
                        }`}
                      >
                        {row.commission_status_label}
                      </span>
                    </div>
                    <p className="text-gray-600">{row.buyer_label} · {row.order_status_label}</p>
                    <p className="text-gray-500 truncate">{row.product_summary}</p>
                    <p className="font-semibold text-gray-900">Hoa hồng: {fmt(Number(row.commission_amount))}</p>
                  </li>
                ))}
              </ul>
              {referredOrdersHasMore ? (
                <div className="mt-4 text-center">
                  <button
                    type="button"
                    disabled={referredOrdersLoading}
                    onClick={() => void loadReferredOrders(referredOrdersSkip, true)}
                    className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50 disabled:opacity-60"
                  >
                    {referredOrdersLoading ? 'Đang tải…' : 'Xem thêm'}
                  </button>
                </div>
              ) : null}
            </>
          )}
        </div>
      ) : null}

      <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
        <h2 className="font-semibold text-gray-900 mb-1">Lịch sử ví</h2>
        <p className="text-xs text-gray-500 mb-4">
          Mỗi giao dịch hiển thị số dư sau thay đổi: <strong>Có thể rút</strong> và <strong>Chờ giao hàng</strong>.
        </p>
        {transactions.length === 0 ? (
          <p className="text-sm text-gray-500">Chưa có giao dịch.</p>
        ) : (
          <>
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-gray-500 border-b border-gray-100">
                    <th className="py-2 pr-3 font-medium">Thời gian</th>
                    <th className="py-2 pr-3 font-medium">Loại</th>
                    <th className="py-2 pr-3 font-medium">Đơn / Sản phẩm</th>
                    <th className="py-2 pr-3 font-medium">Trạng thái đơn</th>
                    <th className="py-2 pr-3 font-medium text-right">Số tiền</th>
                    <th className="py-2 font-medium text-right">Số dư sau</th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.map((tx) => {
                    const bucket = bucketLabel(tx.affects_bucket);
                    return (
                      <tr key={tx.id} className="border-b border-gray-50 align-top">
                        <td className="py-3 pr-3 text-gray-500 whitespace-nowrap">
                          {tx.created_at ? new Date(tx.created_at).toLocaleString('vi-VN') : '—'}
                        </td>
                        <td className="py-3 pr-3">
                          <p className="font-medium text-gray-800">{tx.tx_type_label || tx.tx_type}</p>
                          {bucket ? (
                            <span className="mt-1 inline-flex rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                              {bucket}
                            </span>
                          ) : null}
                        </td>
                        <td className="py-3 pr-3 text-gray-600 max-w-[220px]">
                          {tx.order_code ? (
                            <p className="font-medium text-gray-800">#{tx.order_code}</p>
                          ) : null}
                          {tx.product_summary ? (
                            <p className="truncate" title={tx.product_summary}>
                              {tx.product_summary}
                            </p>
                          ) : (
                            <p className="text-gray-400">{tx.description || '—'}</p>
                          )}
                        </td>
                        <td className="py-3 pr-3 text-gray-700">{tx.order_status_label || '—'}</td>
                        <td
                          className={`py-3 pr-3 text-right font-semibold whitespace-nowrap ${
                            Number(tx.amount) >= 0 ? 'text-green-600' : 'text-red-600'
                          }`}
                        >
                          {Number(tx.amount) >= 0 ? '+' : ''}
                          {fmt(Number(tx.amount))}
                        </td>
                        <td className="py-3 text-right text-xs text-gray-600 whitespace-nowrap">
                          <p>Rút: {fmt(Number(tx.balance_after))}</p>
                          <p>Chờ: {fmt(Number(tx.pending_after))}</p>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <ul className="md:hidden divide-y divide-gray-100">
              {transactions.map((tx) => {
                const bucket = bucketLabel(tx.affects_bucket);
                return (
                  <li key={tx.id} className="py-3 space-y-1 text-sm">
                    <p className="text-xs text-gray-400">
                      {tx.created_at ? new Date(tx.created_at).toLocaleString('vi-VN') : ''}
                    </p>
                    <div className="flex items-start justify-between gap-2">
                      <p className="font-medium text-gray-800">{tx.tx_type_label || tx.tx_type}</p>
                      <span
                        className={`shrink-0 font-semibold ${
                          Number(tx.amount) >= 0 ? 'text-green-600' : 'text-red-600'
                        }`}
                      >
                        {Number(tx.amount) >= 0 ? '+' : ''}
                        {fmt(Number(tx.amount))}
                      </span>
                    </div>
                    {bucket ? <p className="text-xs text-gray-500">{bucket}</p> : null}
                    {tx.order_code ? <p className="text-gray-700">Đơn #{tx.order_code}</p> : null}
                    {tx.product_summary ? (
                      <p className="text-gray-500 truncate">{tx.product_summary}</p>
                    ) : tx.description ? (
                      <p className="text-gray-500">{tx.description}</p>
                    ) : null}
                    {tx.order_status_label ? (
                      <p className="text-gray-600">Trạng thái đơn: {tx.order_status_label}</p>
                    ) : null}
                    <p className="text-xs text-gray-500">
                      Sau GD — Rút: {fmt(Number(tx.balance_after))} · Chờ: {fmt(Number(tx.pending_after))}
                    </p>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
