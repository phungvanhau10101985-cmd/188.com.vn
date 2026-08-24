'use client';

import { useCallback, useEffect, useState } from 'react';
import { adminBankAPI, type AdminSepayHmacSecretStatus } from '@/lib/admin-api';

function sourceLabel(source: AdminSepayHmacSecretStatus['source']): string {
  if (source === 'admin') return 'Đã lưu trên form quản trị';
  if (source === 'env') return 'Đang dùng key trong .env server';
  return 'Chưa có Secret Key';
}

export default function SepayHmacSecretPanel() {
  const [status, setStatus] = useState<AdminSepayHmacSecretStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [secret, setSecret] = useState('');
  const [saving, setSaving] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [pendingClear, setPendingClear] = useState(false);
  const [banner, setBanner] = useState<{ variant: 'ok' | 'error'; text: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const out = await adminBankAPI.getSepayHmacSecret();
      setStatus(out);
    } catch (e) {
      setBanner({ variant: 'error', text: (e as Error)?.message || 'Không tải được cấu hình HMAC' });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onSave = async (e: React.FormEvent) => {
    e.preventDefault();
    const value = secret.trim();
    if (value.length < 8) {
      setBanner({ variant: 'error', text: 'Secret Key phải dài ít nhất 8 ký tự.' });
      return;
    }
    setSaving(true);
    setBanner(null);
    try {
      const out = await adminBankAPI.saveSepayHmacSecret(value);
      setStatus(out);
      setSecret('');
      setBanner({ variant: 'ok', text: 'Đã lưu Secret Key. Webhook dùng key này ngay, không cần restart.' });
    } catch (err) {
      setBanner({ variant: 'error', text: (err as Error)?.message || 'Không lưu được Secret Key' });
    } finally {
      setSaving(false);
    }
  };

  const onClear = async () => {
    setClearing(true);
    setBanner(null);
    try {
      const out = await adminBankAPI.clearSepayHmacSecret();
      setStatus(out);
      setPendingClear(false);
      setBanner({
        variant: 'ok',
        text: out.env_configured
          ? 'Đã xóa key trên form. Webhook sẽ dùng SEPAY_SECRET_KEY trong .env nếu có.'
          : 'Đã xóa Secret Key trên form.',
      });
    } catch (err) {
      setBanner({ variant: 'error', text: (err as Error)?.message || 'Không xóa được Secret Key' });
    } finally {
      setClearing(false);
    }
  };

  return (
    <section
      className="mb-8 rounded-xl border border-gray-200 bg-white p-5 shadow-sm"
      aria-labelledby="sepay-hmac-heading"
    >
      <h2 id="sepay-hmac-heading" className="text-lg font-semibold text-gray-900">
        Cấu hình HMAC-SHA256
      </h2>
      <p className="mt-2 text-sm text-gray-600 max-w-3xl">
        SePay sẽ ký dữ liệu bằng HMAC-SHA256 và gửi chữ ký trong header{' '}
        <code className="bg-gray-100 px-1 rounded text-xs">X-SePay-Signature</code>. Secret key không bao giờ rời khỏi
        máy chủ SePay — dán bản sao Secret Key từ dashboard SePay vào đây để server tự tính lại chữ ký.
      </p>

      {loading ? (
        <p className="mt-4 text-sm text-gray-500">Đang tải cấu hình…</p>
      ) : (
        <p className="mt-3 text-sm">
          {status?.configured ? (
            <span className="inline-flex items-center rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-900">
              {sourceLabel(status.source)}
              {status.last4 ? ` · ••••${status.last4}` : ''}
            </span>
          ) : (
            <span className="inline-flex items-center rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-950">
              Chưa có Secret Key
            </span>
          )}
        </p>
      )}

      {banner && (
        <div
          className={`mt-4 rounded-lg px-4 py-3 text-sm ${
            banner.variant === 'ok'
              ? 'border border-emerald-200 bg-emerald-50 text-emerald-900'
              : 'border border-red-200 bg-red-50 text-red-700'
          }`}
          role="status"
        >
          {banner.text}{' '}
          {banner.variant === 'error' ? (
            <button type="button" onClick={() => void load()} className="underline font-medium">
              Thử lại
            </button>
          ) : null}
        </div>
      )}

      <form onSubmit={onSave} className="mt-5 space-y-3 max-w-xl">
        <div>
          <label htmlFor="sepay-hmac-secret" className="block text-sm font-medium text-gray-800 mb-1">
            Secret Key
          </label>
          <input
            id="sepay-hmac-secret"
            type="password"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            placeholder="whsec_..."
            autoComplete="new-password"
            className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm font-mono text-gray-900 focus:ring-2 focus:ring-orange-500/30 focus:border-orange-500"
          />
          <p className="mt-1.5 text-xs text-gray-500">
            Copy từ my.sepay.vn → Webhooks → Cấu hình HMAC-SHA256. Không hiện lại giá trị đầy đủ sau khi lưu.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
          >
            {saving ? 'Đang lưu…' : 'Lưu Secret Key'}
          </button>
          {status?.admin_configured ? (
            pendingClear ? (
              <>
                <button
                  type="button"
                  disabled={clearing}
                  onClick={() => void onClear()}
                  className="rounded-lg border border-red-300 bg-red-50 px-4 py-2.5 text-sm font-medium text-red-800 hover:bg-red-100 disabled:opacity-60"
                >
                  {clearing ? 'Đang xóa…' : 'Xác nhận xóa key trên form'}
                </button>
                <button
                  type="button"
                  onClick={() => setPendingClear(false)}
                  className="text-sm text-gray-600 underline"
                >
                  Hủy
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={() => setPendingClear(true)}
                className="text-sm text-red-700 underline"
              >
                Xóa key đã lưu trên form
              </button>
            )
          ) : null}
        </div>
      </form>

      <details className="mt-6 text-sm text-gray-700">
        <summary className="cursor-pointer font-medium text-gray-900 hover:text-slate-700">
          Hướng dẫn xác thực trên server
        </summary>
        <div className="mt-3 space-y-2 text-gray-600 max-w-3xl">
          <p>Server 188.com.vn đã tự xác thực webhook theo đúng spec SePay:</p>
          <ol className="list-decimal pl-5 space-y-1.5">
            <li>
              SePay ghép <code className="bg-gray-100 px-1 rounded text-xs">{'{timestamp}.{raw_body}'}</code> rồi ký
              HMAC-SHA256 bằng Secret Key.
            </li>
            <li>
              Kết quả gửi qua header{' '}
              <code className="bg-gray-100 px-1 rounded text-xs">X-SePay-Signature: sha256=&lt;hex&gt;</code> và{' '}
              <code className="bg-gray-100 px-1 rounded text-xs">X-SePay-Timestamp</code>.
            </li>
            <li>Server tính lại chữ ký với key đã lưu. Khớp → nhận giao dịch; khác → 401.</li>
            <li>IP allowlist SePay vẫn là lớp phụ khi request chưa có chữ ký.</li>
          </ol>
          <p className="text-xs text-gray-500">
            Chỉ bật chữ ký HMAC trên dashboard SePay sau khi code đã lên server và đã lưu Secret Key ở đây.
          </p>
        </div>
      </details>
    </section>
  );
}
