'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { apiClient } from '@/lib/api-client';
import { useToast } from '@/components/ToastProvider';
import Button from '@/components/ui/Button';

export default function UserBankAccountPage() {
  const { pushToast } = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [sendingOtp, setSendingOtp] = useState(false);
  const [otpSentTo, setOtpSentTo] = useState('');
  const [otp, setOtp] = useState('');
  const [form, setForm] = useState({
    bank_name: '',
    bank_account: '',
    account_holder: '',
  });

  const updateForm = (key: keyof typeof form, value: string) => {
    setForm((f) => ({ ...f, [key]: value }));
    setOtpSentTo('');
    setOtp('');
  };

  useEffect(() => {
    let active = true;
    apiClient
      .getAffiliateBankAccount()
      .then((row) => {
        if (!active || !row) return;
        setForm({
          bank_name: row.bank_name || '',
          bank_account: row.bank_account || '',
          account_holder: row.account_holder || '',
        });
      })
      .catch(() => {})
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const requestOtp = async () => {
    setSendingOtp(true);
    try {
      const res = await apiClient.requestAffiliateBankAccountOtp(form);
      setOtp('');
      setOtpSentTo(res.email);
      pushToast({
        title: 'Đã gửi OTP xác minh',
        description: `Nhập mã đã gửi tới ${res.email}. Mã có hiệu lực ${res.expires_in_minutes} phút.`,
        variant: 'success',
      });
    } catch (err: any) {
      pushToast({
        title: 'Không gửi được OTP',
        description: err?.message || 'Vui lòng thử lại',
        variant: 'error',
      });
    } finally {
      setSendingOtp(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!otpSentTo) {
      await requestOtp();
      return;
    }

    if (!otp.trim()) {
      pushToast({ title: 'Nhập mã OTP để xác minh', variant: 'info' });
      return;
    }

    setSaving(true);
    try {
      await apiClient.saveAffiliateBankAccount({ ...form, otp: otp.trim() });
      pushToast({ title: 'Đã lưu tài khoản ngân hàng', variant: 'success' });
      setOtp('');
      setOtpSentTo('');
    } catch (err: any) {
      pushToast({
        title: 'Không lưu được',
        description: err?.message || 'Vui lòng thử lại',
        variant: 'error',
      });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-[30vh] flex items-center justify-center">
        <div className="animate-spin w-10 h-10 border-4 border-[#ea580c] border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5 max-w-xl">
      <h1 className="text-xl font-bold text-gray-900">Tài khoản ngân hàng</h1>
      <p className="text-sm text-gray-600 mt-1 mb-5">
        Dùng để nhận tiền rút từ{' '}
        <Link href="/vi-dien-tu" className="text-[#ea580c] underline font-medium">
          Ví Affiliate
        </Link>
        . Vì đây là thông tin nhận tiền, mỗi lần thêm/sửa cần xác minh OTP qua email.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="bank_name" className="block text-sm font-medium text-gray-700 mb-1">
            Ngân hàng
          </label>
          <input
            id="bank_name"
            required
            value={form.bank_name}
            onChange={(e) => updateForm('bank_name', e.target.value)}
            placeholder="VD: Vietcombank"
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label htmlFor="bank_account" className="block text-sm font-medium text-gray-700 mb-1">
            Số tài khoản
          </label>
          <input
            id="bank_account"
            required
            value={form.bank_account}
            onChange={(e) => updateForm('bank_account', e.target.value)}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label htmlFor="account_holder" className="block text-sm font-medium text-gray-700 mb-1">
            Chủ tài khoản
          </label>
          <input
            id="account_holder"
            required
            value={form.account_holder}
            onChange={(e) => updateForm('account_holder', e.target.value)}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
          />
        </div>
        {otpSentTo ? (
          <div className="rounded-lg border border-orange-100 bg-orange-50 px-4 py-3">
            <label htmlFor="bank_otp" className="block text-sm font-medium text-gray-800 mb-1">
              Mã OTP đã gửi tới {otpSentTo}
            </label>
            <div className="flex flex-col sm:flex-row gap-2">
              <input
                id="bank_otp"
                required
                inputMode="numeric"
                maxLength={8}
                value={otp}
                onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))}
                placeholder="Nhập mã OTP"
                className="flex-1 rounded-lg border border-orange-200 px-3 py-2 text-sm"
              />
              <button
                type="button"
                disabled={sendingOtp}
                onClick={() => void requestOtp()}
                className="rounded-lg border border-orange-200 px-4 py-2 text-sm font-semibold text-orange-700 hover:bg-white disabled:opacity-60"
              >
                Gửi lại mã
              </button>
            </div>
            <p className="mt-2 text-xs text-gray-600">
              Nếu bạn thay đổi thông tin ngân hàng, hệ thống sẽ yêu cầu gửi OTP mới.
            </p>
          </div>
        ) : null}
        <Button
          type="submit"
          variant="primary"
          disabled={saving || sendingOtp}
          loading={saving || sendingOtp}
          className="w-full sm:w-auto"
        >
          {otpSentTo ? 'Xác minh & lưu tài khoản' : 'Gửi OTP xác minh'}
        </Button>
      </form>
    </div>
  );
}
