'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import {
  adminFeatureTestAPI,
  type AdminBirthdayPromoTestSettings,
  type AdminSiteSaleTestSettings,
} from '@/lib/admin-api';
import {
  BIRTHDAY_DISCOUNT_PERCENT,
} from '@/lib/birthday-discount';

function currentMonthSaleHint() {
  const month = new Date().getMonth() + 1;
  const pct = month % 2 === 1 ? 6 : 8;
  return `${pct}% (tháng ${month})`;
}

export default function AdminFeatureTestPage() {
  const [birthdaySettings, setBirthdaySettings] = useState<AdminBirthdayPromoTestSettings | null>(null);
  const [siteSaleSettings, setSiteSaleSettings] = useState<AdminSiteSaleTestSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingBirthday, setSavingBirthday] = useState(false);
  const [savingSiteSale, setSavingSiteSale] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [siteSaleError, setSiteSaleError] = useState<string | null>(null);
  const [birthdayMessage, setBirthdayMessage] = useState<string | null>(null);
  const [siteSaleMessage, setSiteSaleMessage] = useState<string | null>(null);
  const [testEmail, setTestEmail] = useState('');
  const [siteSalePhase, setSiteSalePhase] = useState<'teaser' | 'active'>('active');

  const birthdayExpiresAt = birthdaySettings?.birthday_promo_expires_at
    ? new Date(birthdaySettings.birthday_promo_expires_at)
    : null;
  const birthdayExpiresAtLabel =
    birthdayExpiresAt && !Number.isNaN(birthdayExpiresAt.getTime())
      ? birthdayExpiresAt.toLocaleString('vi-VN')
      : null;

  const siteSaleExpiresAt = siteSaleSettings?.site_sale_test_expires_at
    ? new Date(siteSaleSettings.site_sale_test_expires_at)
    : null;
  const siteSaleExpiresAtLabel =
    siteSaleExpiresAt && !Number.isNaN(siteSaleExpiresAt.getTime())
      ? siteSaleExpiresAt.toLocaleString('vi-VN')
      : null;

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError(null);
      setSiteSaleError(null);

      let email = '';

      try {
        const birthdayData = await adminFeatureTestAPI.getBirthdayPromoSettings();
        if (!active) return;
        setBirthdaySettings(birthdayData);
        email = birthdayData.test_email || birthdayData.admin_email || email;
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : 'Không tải được cài đặt test CMSN.');
        }
      }

      try {
        const siteSaleData = await adminFeatureTestAPI.getSiteSaleSettings();
        if (!active) return;
        setSiteSaleSettings(siteSaleData);
        email = siteSaleData.test_email || siteSaleData.admin_email || email;
        setSiteSalePhase(siteSaleData.site_sale_test_phase || 'active');
      } catch (err) {
        if (active) {
          setSiteSaleError(
            err instanceof Error
              ? `${err.message} Cần deploy code mới và restart backend (pm2 restart backend).`
              : 'Không tải được cài đặt test Sale lịch.',
          );
        }
      }

      if (active) {
        setTestEmail(email);
        setLoading(false);
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, []);

  const updateBirthdayTest = async (enabled: boolean) => {
    try {
      setSavingBirthday(true);
      setError(null);
      setBirthdayMessage(null);
      const email = testEmail.trim();
      if (enabled && !email) {
        setError('Vui lòng nhập email tài khoản test.');
        return;
      }
      const data = await adminFeatureTestAPI.updateBirthdayPromoSettings(enabled, email);
      setBirthdaySettings(data);
      setTestEmail(data.test_email || email);
      const emailNote = data.test_email_sent
        ? ` Email CMSN test đã gửi tới ${data.test_email || email}.`
        : data.test_email_error
          ? ` Bật test thành công nhưng chưa gửi được email test: ${data.test_email_error}`
          : '';
      setBirthdayMessage(
        data.birthday_promo_enabled
          ? `Đã bật test CMSN trong ${data.test_duration_minutes || 10} phút. Tài khoản web đăng nhập bằng email ${data.test_email || email} sẽ chạy giống khách thật trong tuần sinh nhật.${emailNote}`
          : 'Đã tắt test CMSN.'
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không lưu được cài đặt test CMSN.');
    } finally {
      setSavingBirthday(false);
    }
  };

  const updateSiteSaleTest = async (enabled: boolean) => {
    try {
      setSavingSiteSale(true);
      setSiteSaleError(null);
      setSiteSaleMessage(null);
      const email = testEmail.trim();
      if (enabled && !email) {
        setError('Vui lòng nhập email tài khoản test.');
        return;
      }
      const data = await adminFeatureTestAPI.updateSiteSaleSettings(
        enabled,
        siteSalePhase,
        email,
      );
      setSiteSaleSettings(data);
      setTestEmail(data.test_email || email);
      setSiteSalePhase(data.site_sale_test_phase || siteSalePhase);
      const phaseLabel = data.site_sale_test_phase === 'teaser' ? 'teaser (sắp giảm)' : 'active (đang giảm)';
      if (enabled && !data.site_sale_test_enabled) {
        setSiteSaleError(
          `Backend trả về trạng thái tắt ngay sau khi bật (hết hạn: ${data.site_sale_test_expires_at ?? '—'}). ` +
            'Thường do backend trên server chưa deploy bản sửa timezone — chạy deploy code mới rồi `pm2 restart backend`.',
        );
        setSiteSaleMessage(null);
        return;
      }
      setSiteSaleMessage(
        data.site_sale_test_enabled
          ? `Đã bật test Sale lịch (${phaseLabel}) trong ${data.test_duration_minutes || 10} phút. Tài khoản web đăng nhập bằng email ${data.test_email || email} sẽ thấy banner, badge và giá giảm giống ngày sale thật.`
          : 'Đã tắt test Sale lịch.'
      );
    } catch (err) {
      setSiteSaleError(err instanceof Error ? err.message : 'Không lưu được cài đặt test Sale lịch.');
    } finally {
      setSavingSiteSale(false);
    }
  };

  const birthdayEnabled = birthdaySettings?.birthday_promo_enabled === true;
  const siteSaleEnabled = siteSaleSettings?.site_sale_test_enabled === true;

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

      <div className="mb-6 rounded-xl border border-gray-200 bg-gray-50 p-4">
        <label htmlFor="shared-test-email" className="block text-sm font-semibold text-gray-900">
          Email tài khoản test (dùng chung)
        </label>
        <p className="mt-1 text-xs text-gray-500">
          Dùng email của tài khoản khách bạn sẽ đăng nhập trên web để test CMSN hoặc Sale lịch.
        </p>
        <input
          id="shared-test-email"
          type="email"
          value={testEmail}
          onChange={(e) => setTestEmail(e.target.value)}
          disabled={savingBirthday || savingSiteSale}
          className="mt-2 w-full max-w-xl rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-[#ea580c] focus:outline-none focus:ring-2 focus:ring-orange-100"
          placeholder="test@example.com"
        />
      </div>

      {birthdayMessage && (
        <div className="mb-4 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
          {birthdayMessage}
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
              Bật test để tài khoản web đăng nhập bằng email test chạy giống khách thật trong chương trình CMSN:
              nhận email, thấy banner, giá web giảm {BIRTHDAY_DISCOUNT_PERCENT}% và cart/order cũng giảm thật.
              Test tự tắt sau 10 phút.
            </p>
          </div>

          <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap">
            <button
              type="button"
              onClick={() => updateBirthdayTest(true)}
              disabled={loading || savingBirthday}
              className="inline-flex min-h-[44px] w-full min-w-0 items-center justify-center rounded-lg bg-[#ea580c] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#c2410c] disabled:opacity-60 sm:min-h-0 sm:w-auto sm:min-w-[9rem]"
            >
              {savingBirthday ? 'Đang lưu...' : birthdayEnabled ? 'Lưu test' : 'Bật test'}
            </button>
            {birthdayEnabled && (
              <button
                type="button"
                onClick={() => updateBirthdayTest(false)}
                disabled={loading || savingBirthday}
                className="inline-flex min-h-[44px] w-full min-w-0 items-center justify-center rounded-lg bg-red-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60 sm:min-h-0 sm:w-auto sm:min-w-[7rem]"
              >
                Tắt test
              </button>
            )}
          </div>
        </div>

        <div className="mt-5 grid gap-3 rounded-xl bg-gray-50 p-4 text-sm text-gray-700 md:grid-cols-3">
          <div>
            <p className="text-xs font-semibold uppercase text-gray-500">Trạng thái</p>
            <p className={birthdayEnabled ? 'font-bold text-green-700' : 'font-bold text-gray-900'}>
              {loading ? 'Đang tải...' : birthdayEnabled ? 'Đang bật' : 'Đang tắt'}
            </p>
            {birthdayEnabled && birthdayExpiresAtLabel ? (
              <p className="mt-0.5 text-xs text-gray-500">Tự tắt lúc {birthdayExpiresAtLabel}</p>
            ) : null}
          </div>
          <div>
            <p className="text-xs font-semibold uppercase text-gray-500">Email test</p>
            <p className={birthdaySettings?.can_apply_on_web ? 'font-bold text-green-700' : 'font-bold text-amber-700'}>
              {birthdaySettings?.test_email || testEmail || 'Chưa nhập email test'}
            </p>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase text-gray-500">Giảm giá test</p>
            <p className="font-bold text-gray-900">{BIRTHDAY_DISCOUNT_PERCENT}%</p>
          </div>
        </div>

        <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
          Khi bật test CMSN, email test sẽ được gửi ngay nếu SMTP đang cấu hình. Đăng nhập web bằng đúng email test ở trên.
        </div>
      </section>

      {siteSaleMessage && (
        <div className="mt-4 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
          {siteSaleMessage}
        </div>
      )}

      {siteSaleError && (
        <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {siteSaleError}
        </div>
      )}

      <section className="mt-6 rounded-2xl border border-gray-200 bg-white p-4 shadow-sm sm:p-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="inline-flex rounded-full bg-orange-50 px-3 py-1 text-xs font-semibold text-orange-700">
              Sale lịch site-wide
            </div>
            <h2 className="mt-3 text-lg font-bold text-gray-900">
              Giả lập ngày sale (6/6, 8/8…)
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-600">
              Có 2 chế độ test — chọn trước khi bật (hoặc bấm Lưu test khi đang bật để đổi phase):
              <strong className="font-semibold text-gray-800"> Teaser</strong> giả lập giai đoạn chờ sale
              (T-3 → T-1, banner countdown, giá chưa giảm);
              <strong className="font-semibold text-gray-800"> Active</strong> giả lập đúng ngày sale
              (giá giảm thật trên web, giỏ hàng và checkout). Test tự tắt sau 10 phút.
            </p>
          </div>

          <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap">
            <button
              type="button"
              onClick={() => updateSiteSaleTest(true)}
              disabled={loading || savingSiteSale}
              className="inline-flex min-h-[44px] w-full min-w-0 items-center justify-center rounded-lg bg-[#ea580c] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#c2410c] disabled:opacity-60 sm:min-h-0 sm:w-auto sm:min-w-[9rem]"
            >
              {savingSiteSale ? 'Đang lưu...' : siteSaleEnabled ? 'Lưu test' : 'Bật test'}
            </button>
            {siteSaleEnabled && (
              <button
                type="button"
                onClick={() => updateSiteSaleTest(false)}
                disabled={loading || savingSiteSale}
                className="inline-flex min-h-[44px] w-full min-w-0 items-center justify-center rounded-lg bg-red-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60 sm:min-h-0 sm:w-auto sm:min-w-[7rem]"
              >
                Tắt test
              </button>
            )}
          </div>
        </div>

        <div className="mt-5">
          <p className="text-sm font-semibold text-gray-900">Phase test</p>
          <p className="mt-1 text-xs text-gray-500">
            Teaser: giống khách đang chờ sale (3 ngày trước ngày sale) — banner, badge, giá gốc + tiết kiệm dự kiến.
            Active: giống đúng ngày sale — giá giảm thật, cart/checkout áp dụng giảm.
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setSiteSalePhase('teaser')}
              disabled={savingSiteSale}
              className={`rounded-lg border px-4 py-2 text-sm font-semibold ${
                siteSalePhase === 'teaser'
                  ? 'border-orange-500 bg-orange-50 text-orange-800'
                  : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
              }`}
            >
              Teaser — chờ sale (T-3)
            </button>
            <button
              type="button"
              onClick={() => setSiteSalePhase('active')}
              disabled={savingSiteSale}
              className={`rounded-lg border px-4 py-2 text-sm font-semibold ${
                siteSalePhase === 'active'
                  ? 'border-orange-500 bg-orange-50 text-orange-800'
                  : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
              }`}
            >
              Active — đang sale
            </button>
          </div>
        </div>

        <div className="mt-5 grid gap-3 rounded-xl bg-gray-50 p-4 text-sm text-gray-700 md:grid-cols-4">
          <div>
            <p className="text-xs font-semibold uppercase text-gray-500">Trạng thái</p>
            <p className={siteSaleEnabled ? 'font-bold text-green-700' : 'font-bold text-gray-900'}>
              {loading ? 'Đang tải...' : siteSaleEnabled ? 'Đang bật' : 'Đang tắt'}
            </p>
            {siteSaleEnabled && siteSaleExpiresAtLabel ? (
              <p className="mt-0.5 text-xs text-gray-500">Tự tắt lúc {siteSaleExpiresAtLabel}</p>
            ) : null}
          </div>
          <div>
            <p className="text-xs font-semibold uppercase text-gray-500">Phase</p>
            <p className="font-bold text-gray-900">
              {siteSaleSettings?.site_sale_test_phase === 'teaser' ? 'Teaser' : 'Active'}
            </p>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase text-gray-500">Email test</p>
            <p className={siteSaleSettings?.can_apply_on_web ? 'font-bold text-green-700' : 'font-bold text-amber-700'}>
              {siteSaleSettings?.test_email || testEmail || 'Chưa nhập email test'}
            </p>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase text-gray-500">Giảm giá test</p>
            <p className="font-bold text-gray-900">{currentMonthSaleHint()}</p>
          </div>
        </div>

        <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
          Feed Google/Meta không bị ảnh hưởng bởi test — chỉ tài khoản web đăng nhập bằng email test mới thấy sale giả lập.
          Nhãn sự kiện sẽ có tiền tố [Test] trên banner.
        </div>
      </section>

      <div className="mt-6 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:gap-3">
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
        <Link
          href="/admin/promotions#site-sale"
          className="inline-flex min-h-[44px] w-full items-center justify-center rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50 sm:min-h-0 sm:w-auto"
        >
          Cấu hình sale site-wide (Khuyến mãi)
        </Link>
      </div>
    </div>
  );
}
