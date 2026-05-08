'use client';

import { useCallback, useEffect, useState } from 'react';
import { adminProductAPI, type AdminImport1688CookieSettings } from '@/lib/admin-api';
import { getApiBaseUrl } from '@/lib/api-base';

export default function AdminImport1688SettingsPage() {
  const [settings, setSettings] = useState<AdminImport1688CookieSettings | null>(null);
  const [cookieText, setCookieText] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const [apiBase, setApiBase] = useState('');
  const [restartStatus, setRestartStatus] = useState<{
    type: 'idle' | 'running' | 'ok' | 'err';
    message: string;
  }>({ type: 'idle', message: '' });
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);

  const showToast = (type: 'ok' | 'err', msg: string, persistMs = 4500) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), persistMs);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await adminProductAPI.getImport1688CookieSettings();
      setSettings(data);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Không tải được cấu hình 1688';
      showToast('err', `Không tải được cấu hình 1688: ${msg}. API: ${getApiBaseUrl()}`, 12000);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setApiBase(getApiBaseUrl());
    load();
  }, [load]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    const value = cookieText.trim();
    if (!value) {
      showToast('err', 'Vui lòng dán cookie 1688 trước khi lưu');
      return;
    }
    setSaving(true);
    try {
      const data = await adminProductAPI.saveImport1688CookieSettings(value);
      setSettings(data);
      setCookieText('');
      showToast('ok', data.message || 'Đã lưu cookie 1688');
    } catch (err) {
      showToast('err', err instanceof Error ? err.message : 'Lưu cookie thất bại', 9000);
    } finally {
      setSaving(false);
    }
  };

  const handleRestart = async () => {
    setRestarting(true);
    setRestartStatus({ type: 'running', message: 'Đang gửi lệnh restart API backend...' });
    try {
      const res = await adminProductAPI.restartBackendApi();
      setRestartStatus({
        type: 'running',
        message: res.message || 'Đã gửi lệnh restart. Đang chờ API khởi động lại...',
      });

      let lastError = '';
      for (let i = 0; i < 18; i += 1) {
        await new Promise((resolve) => setTimeout(resolve, i < 3 ? 2500 : 5000));
        try {
          const data = await adminProductAPI.getImport1688CookieSettings();
          setSettings(data);
          setRestartStatus({ type: 'ok', message: 'Restart API backend thành công. API đã phản hồi lại.' });
          showToast('ok', 'Restart API backend thành công', 7000);
          setRestarting(false);
          return;
        } catch (err) {
          lastError = err instanceof Error ? err.message : String(err);
          setRestartStatus({
            type: 'running',
            message: `Đang chờ API khởi động lại... (${i + 1}/18)`,
          });
        }
      }

      setRestartStatus({
        type: 'err',
        message: `Chưa xác nhận được API đã lên lại. Lỗi cuối: ${lastError || 'timeout'}`,
      });
      showToast('err', 'Chưa xác nhận được restart API thành công', 9000);
      setRestarting(false);
    } catch (err) {
      setRestarting(false);
      setRestartStatus({
        type: 'err',
        message: err instanceof Error ? err.message : 'Restart API thất bại',
      });
      showToast('err', err instanceof Error ? err.message : 'Restart API thất bại', 9000);
    }
  };

  return (
    <div className="p-6">
      <div className="mb-6 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Cấu hình Import 1688</h1>
          <p className="mt-1 text-sm text-gray-600">
            Dán cookie tài khoản 1688 đã đăng nhập để backend dùng Playwright đọc trang sản phẩm.
          </p>
          {apiBase ? (
            <p className="mt-1 text-xs text-gray-500">
              API đang dùng: <code className="rounded bg-gray-100 px-1 py-0.5">{apiBase}</code>
            </p>
          ) : null}
        </div>
        <a
          href="/admin/products#import-1688"
          className="inline-flex items-center justify-center rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white hover:bg-orange-700"
        >
          Mở import sản phẩm
        </a>
      </div>

      {toast ? (
        <div
          className={`mb-4 rounded-lg border px-4 py-3 text-sm ${
            toast.type === 'ok'
              ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
              : 'border-red-200 bg-red-50 text-red-700'
          }`}
        >
          {toast.msg}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <form onSubmit={handleSave} className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <div className="mb-4">
            <h2 className="text-lg font-semibold text-gray-900">Nhập cookie 1688</h2>
            <p className="mt-1 text-sm text-gray-600">
              Hỗ trợ JSON export từ Cookie-Editor hoặc chuỗi dạng <code>a=b; c=d</code>. Cookie sẽ được lưu vào
              <code className="mx-1 rounded bg-gray-100 px-1 py-0.5 text-xs">backend/1688-cookies.json</code>.
            </p>
          </div>

          <textarea
            value={cookieText}
            onChange={(e) => setCookieText(e.target.value)}
            rows={14}
            placeholder='Dán cookie JSON hoặc chuỗi "a=b; c=d" tại đây...'
            className="w-full rounded-lg border border-gray-300 px-3 py-2 font-mono text-xs leading-relaxed focus:outline-none focus:ring-2 focus:ring-orange-300"
          />

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-gray-500">
              Không commit file cookie. Sau khi lưu, bạn có thể import ngay; restart dùng để đồng bộ process trên server.
            </p>
            <button
              type="submit"
              disabled={saving || !cookieText.trim()}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-70"
            >
              {saving ? 'Đang lưu...' : 'Lưu cookie'}
            </button>
          </div>
        </form>

        <aside className="space-y-4">
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <h2 className="text-lg font-semibold text-gray-900">Trạng thái</h2>
            {loading ? (
              <p className="mt-3 text-sm text-gray-500">Đang tải...</p>
            ) : (
              <div className="mt-3 space-y-2 text-sm text-gray-700">
                <p>
                  <span className="font-medium">Import 1688:</span>{' '}
                  {settings?.enabled ? 'Đang bật' : 'Đang tắt'}
                </p>
                <p>
                  <span className="font-medium">Cookie:</span>{' '}
                  {settings?.has_cookie ? `${settings.cookie_count} cookie` : 'Chưa có'}
                </p>
                <p className="break-all">
                  <span className="font-medium">File:</span> {settings?.cookie_file || 'Chưa cấu hình'}
                </p>
                {settings?.cookie_names?.length ? (
                  <div>
                    <p className="font-medium">Tên cookie đã nhận:</p>
                    <p className="mt-1 max-h-28 overflow-y-auto rounded bg-gray-50 p-2 font-mono text-xs text-gray-600">
                      {settings.cookie_names.join(', ')}
                    </p>
                  </div>
                ) : null}
              </div>
            )}
          </div>

          <div className="rounded-xl border border-amber-200 bg-amber-50 p-5">
            <h2 className="text-lg font-semibold text-amber-950">Restart API backend</h2>
            <p className="mt-2 text-sm text-amber-900">
              Nút này làm process API thoát sau khi trả response. Chỉ bấm khi backend đang chạy dưới PM2/systemd/Docker có tự restart.
            </p>
            <button
              type="button"
              onClick={handleRestart}
              disabled={restarting}
              className="mt-4 w-full rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-70"
            >
              {restarting ? 'Đang restart...' : 'Restart API backend'}
            </button>
            {restartStatus.type !== 'idle' ? (
              <div
                className={`mt-3 rounded-lg border px-3 py-2 text-sm ${
                  restartStatus.type === 'ok'
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                    : restartStatus.type === 'err'
                      ? 'border-red-200 bg-red-50 text-red-700'
                      : 'border-amber-200 bg-white/70 text-amber-900'
                }`}
              >
                {restartStatus.message}
              </div>
            ) : null}
          </div>

          <div className="rounded-xl border border-sky-200 bg-sky-50 p-5 text-sm text-sky-900">
            <p className="font-semibold">Cách lấy cookie nhanh</p>
            <p className="mt-2">
              Đăng nhập 1688 trên Chrome, mở trang sản phẩm, vượt captcha nếu có, dùng extension Cookie-Editor export cookie domain
              <code className="mx-1 rounded bg-white/70 px-1 py-0.5 text-xs">1688.com</code> rồi dán vào ô bên trái.
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}
