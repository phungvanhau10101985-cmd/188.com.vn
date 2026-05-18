'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import {
  adminFeatureTestAPI,
  type AdminBirthdayPromoTestSettings,
} from '@/lib/admin-api';
import {
  BIRTHDAY_DISCOUNT_PERCENT,
  BIRTHDAY_OFFER_DAYS_BEFORE_MAX,
} from '@/lib/birthday-discount';

export default function AdminFeatureTestPage() {
  const [settings, setSettings] = useState<AdminBirthdayPromoTestSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [testEmail, setTestEmail] = useState('');

  const expiresAt = settings?.birthday_promo_expires_at
    ? new Date(settings.birthday_promo_expires_at)
    : null;
  const expiresAtLabel =
    expiresAt && !Number.isNaN(expiresAt.getTime())
      ? expiresAt.toLocaleString('vi-VN')
      : null;

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await adminFeatureTestAPI.getBirthdayPromoSettings();
        if (!active) return;
        setSettings(data);
        setTestEmail(data.test_email || data.admin_email || '');
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : 'Không tải được cài đặt test.');
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, []);

  const updateBirthdayTest = async (enabled: boolean) => {
    try {
      setSaving(true);
      setError(null);
      setMessage(null);
      const email = testEmail.trim();
      if (enabled && !email) {
        setError('Vui lòng nhập email tài khoản test.');
        return;
      }
      const data = await adminFeatureTestAPI.updateBirthdayPromoSettings(enabled, email);
      setSettings(data);
      setTestEmail(data.test_email || email);
      const emailNote = data.test_email_sent
        ? ` Email CMSN test đã gửi tới ${data.test_email || email}.`
        : data.test_email_error
          ? ` Bật test thành công nhưng chưa gửi được email test: ${data.test_email_error}`
          : '';
      setMessage(
        data.birthday_promo_enabled
          ? `Đã bật test CMSN trong ${data.test_duration_minutes || 10} phút. Tài khoản web đăng nhập bằng email ${data.test_email || email} sẽ chạy giống khách thật trong tuần sinh nhật.${emailNote}`
          : 'Đã tắt test CMSN.'
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không lưu được cài đặt test.');
    } finally {
      setSaving(false);
    }
  };

  const enabled = settings?.birthday_promo_enabled === true;

  return (
    <div className="mx-auto max-w-5xl p-4 md:p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Test & thử nghiệm tính năng</h1>
        <p className="mt-1 text-sm text-gray-600">
          Bật tính năng test để tài khoản admin xem website giống trạng thái thực tế của chương trình.
        </p>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}
      {message && (
        <div className="mb-4 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
          {message}
        </div>
      )}

      <section className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm sm:p-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="inline-flex rounded-full bg-pink-50 px-3 py-1 text-xs font-semibold text-pink-700">
              CMSN khách hàng
            </div>
            <h2 className="mt-3 text-lg font-bold text-gray-900">
              Giả lập tuần lễ sinh nhật
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-600">
              Nhập email tài khoản test, sau đó bật test. Tài khoản web đăng nhập bằng email này sẽ chạy
              giống khách thật 100% trong chương trình CMSN: nhận email, thấy banner, giá web giảm{' '}
              {BIRTHDAY_DISCOUNT_PERCENT}% và cart/order cũng giảm thật. Test tự tắt sau 10 phút.
            </p>
          </div>

          <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap">
            <button
              type="button"
              onClick={() => updateBirthdayTest(true)}
              disabled={loading || saving}
              className="inline-flex min-h-[44px] w-full min-w-0 items-center justify-center rounded-lg bg-[#ea580c] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#c2410c] disabled:opacity-60 sm:min-h-0 sm:w-auto sm:min-w-[9rem]"
            >
              {saving ? 'Đang lưu...' : enabled ? 'Lưu test' : 'Bật test'}
            </button>
            {enabled && (
              <button
                type="button"
                onClick={() => updateBirthdayTest(false)}
                disabled={loading || saving}
                className="inline-flex min-h-[44px] w-full min-w-0 items-center justify-center rounded-lg bg-red-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60 sm:min-h-0 sm:w-auto sm:min-w-[7rem]"
              >
                Tắt test
              </button>
            )}
          </div>
        </div>

        <div className="mt-5">
          <label htmlFor="birthday-test-email" className="block text-sm font-semibold text-gray-900">
            Email tài khoản test
          </label>
          <p className="mt-1 text-xs text-gray-500">
            Dùng email của tài khoản khách bạn sẽ đăng nhập trên web để test CMSN.
          </p>
          <input
            id="birthday-test-email"
            type="email"
            value={testEmail}
            onChange={(e) => setTestEmail(e.target.value)}
            disabled={saving}
            className="mt-2 w-full max-w-xl rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-[#ea580c] focus:outline-none focus:ring-2 focus:ring-orange-100"
            placeholder="test@example.com"
          />
        </div>

        <div className="mt-5 grid gap-3 rounded-xl bg-gray-50 p-4 text-sm text-gray-700 md:grid-cols-3">
          <div>
            <p className="text-xs font-semibold uppercase text-gray-500">Trạng thái</p>
            <p className={enabled ? 'font-bold text-green-700' : 'font-bold text-gray-900'}>
              {loading ? 'Đang tải...' : enabled ? 'Đang bật' : 'Đang tắt'}
            </p>
            {enabled && expiresAtLabel ? (
              <p className="mt-0.5 text-xs text-gray-500">Tự tắt lúc {expiresAtLabel}</p>
            ) : null}
          </div>
          <div>
            <p className="text-xs font-semibold uppercase text-gray-500">Email test</p>
            <p className={settings?.can_apply_on_web ? 'font-bold text-green-700' : 'font-bold text-amber-700'}>
              {settings?.test_email || testEmail || 'Chưa nhập email test'}
            </p>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase text-gray-500">Giảm giá test</p>
            <p className="font-bold text-gray-900">{BIRTHDAY_DISCOUNT_PERCENT}%</p>
          </div>
        </div>

        <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
          Để test đúng như khách thật, hãy đăng nhập web bằng đúng email test ở trên. Khi bật test, email CMSN
          test sẽ được gửi ngay tới email này nếu SMTP đang cấu hình. Chương trình test tự hết hiệu lực sau 10 phút.
        </div>

        <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:gap-3">
          <Link
            href="/"
            className="inline-flex min-h-[44px] w-full items-center justify-center rounded-lg bg-gray-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-gray-800 sm:min-h-0 sm:w-auto"
          >
            Mở trang chủ để test giá
          </Link>
          <Link
            href="/cart"
            className="inline-flex min-h-[44px] w-full items-center justify-center rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50 sm:min-h-0 sm:w-auto"
          >
            Mở giỏ hàng để test thanh toán
          </Link>
        </div>
      </section>
    </div>
  );
}
