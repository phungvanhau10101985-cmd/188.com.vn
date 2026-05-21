'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { apiClient } from '@/lib/api-client';
import { useToast } from '@/components/ToastProvider';

function fmt(amount: number) {
  return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(amount || 0);
}

export default function WalletPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const { pushToast } = useToast();
  const [loading, setLoading] = useState(true);
  const [affiliate, setAffiliate] = useState<Awaited<ReturnType<typeof apiClient.getAffiliateMe>> | null>(null);
  const [transactions, setTransactions] = useState<any[]>([]);
  const [withdrawAmount, setWithdrawAmount] = useState('');
  const [withdrawing, setWithdrawing] = useState(false);
  const [copied, setCopied] = useState(false);
  const [applying, setApplying] = useState(false);
  const [socialLinksText, setSocialLinksText] = useState('');
  const [applicationNote, setApplicationNote] = useState('');

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [me, txs] = await Promise.all([
        apiClient.getAffiliateMe(),
        apiClient.getWalletTransactions(0, 30),
      ]);
      setAffiliate(me);
      setTransactions(txs);
    } catch (err: any) {
      pushToast({
        title: 'Không tải được ví',
        description: err?.message || 'Vui lòng thử lại',
        variant: 'error',
      });
    } finally {
      setLoading(false);
    }
  }, [pushToast]);

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
              <p className="text-xs text-white/80">Khả dụng</p>
              <p className="text-lg font-bold">{fmt(Number(affiliate.balance))}</p>
            </div>
            <div className="rounded-lg bg-white/15 px-3 py-2">
              <p className="text-xs text-white/80">Đang chờ duyệt</p>
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
                Số dư ví có thể <strong>dùng mua hàng tại giỏ hàng</strong> hoặc{' '}
                <Link href="/tai-khoan-ngan-hang" className="text-[#ea580c] underline font-medium">
                  rút về ngân hàng
                </Link>{' '}
                (tối thiểu {fmt(Number(affiliate.min_withdrawal))}).
              </div>

              <div className="border-t border-gray-100 pt-4">
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
                  <button
                    type="button"
                    disabled={withdrawing}
                    onClick={() => void handleWithdraw()}
                    className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-semibold hover:bg-gray-50 disabled:opacity-60"
                  >
                    {withdrawing ? 'Đang gửi…' : 'Gửi yêu cầu rút'}
                  </button>
                </div>
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

      <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
        <h2 className="font-semibold text-gray-900 mb-3">Lịch sử ví</h2>
        {transactions.length === 0 ? (
          <p className="text-sm text-gray-500">Chưa có giao dịch.</p>
        ) : (
          <ul className="divide-y divide-gray-100">
            {transactions.map((tx) => (
              <li key={tx.id} className="py-3 flex items-start justify-between gap-3 text-sm">
                <div>
                  <p className="font-medium text-gray-800">{tx.description || tx.tx_type}</p>
                  <p className="text-xs text-gray-500">
                    {tx.created_at ? new Date(tx.created_at).toLocaleString('vi-VN') : ''}
                  </p>
                </div>
                <span className={`font-semibold ${Number(tx.amount) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {Number(tx.amount) >= 0 ? '+' : ''}
                  {fmt(Number(tx.amount))}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
