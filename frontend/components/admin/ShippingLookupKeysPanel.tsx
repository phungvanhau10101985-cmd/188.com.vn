'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  adminIntegrationsAPI,
  type AdminShippingLookupKeyCreated,
  type AdminShippingLookupKeyRow,
} from '@/lib/admin-api';

function formatCreatedAt(iso: string): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('vi-VN');
}

async function copyText(value: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    return false;
  }
}

export default function ShippingLookupKeysPanel() {
  const [keys, setKeys] = useState<AdminShippingLookupKeyRow[]>([]);
  const [envKeyCount, setEnvKeyCount] = useState(0);
  const [configured, setConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [label, setLabel] = useState('');
  const [pastedToken, setPastedToken] = useState('');
  const [showPaste, setShowPaste] = useState(false);
  const [saving, setSaving] = useState(false);
  const [created, setCreated] = useState<AdminShippingLookupKeyCreated | null>(null);
  const [banner, setBanner] = useState<{ variant: 'ok' | 'error'; text: string } | null>(null);
  const [pendingRevokeId, setPendingRevokeId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const out = await adminIntegrationsAPI.listShippingLookupKeys();
      setKeys(Array.isArray(out.keys) ? out.keys : []);
      setEnvKeyCount(Number(out.env_key_count) || 0);
      setConfigured(Boolean(out.configured));
    } catch (e) {
      setError((e as Error)?.message || 'Không tải được danh sách key');
      setKeys([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = label.trim();
    if (!name) {
      setBanner({ variant: 'error', text: 'Nhập tên đối tác / nhãn key.' });
      return;
    }
    setSaving(true);
    setBanner(null);
    try {
      const token = pastedToken.trim();
      const row = await adminIntegrationsAPI.createShippingLookupKey(
        token ? { label: name, token } : { label: name },
      );
      setCreated(row);
      setLabel('');
      setPastedToken('');
      setShowPaste(false);
      setBanner({
        variant: 'ok',
        text: token
          ? `Đã gắn nhãn «${row.label}». Key có hiệu lực ngay.`
          : `Đã cấp key «${row.label}». Sao chép ngay — gửi cho đối tác.`,
      });
      await load();
    } catch (err) {
      setBanner({ variant: 'error', text: (err as Error)?.message || 'Không tạo được key' });
    } finally {
      setSaving(false);
    }
  };

  const onCopyCreated = async () => {
    if (!created?.token) return;
    const ok = await copyText(created.token);
    setBanner({
      variant: ok ? 'ok' : 'error',
      text: ok ? 'Đã sao chép key vào clipboard.' : 'Không sao chép được — hãy bôi đen và copy thủ công.',
    });
  };

  const onCopyExisting = async (id: string) => {
    setBusyId(id);
    setBanner(null);
    try {
      const row = await adminIntegrationsAPI.revealShippingLookupKey(id);
      const ok = await copyText(row.token);
      setCreated(row);
      setBanner({
        variant: ok ? 'ok' : 'error',
        text: ok ? `Đã sao chép key «${row.label}».` : 'Không sao chép được — key hiện bên dưới, copy thủ công.',
      });
    } catch (err) {
      setBanner({ variant: 'error', text: (err as Error)?.message || 'Không lấy được key' });
    } finally {
      setBusyId(null);
    }
  };

  const onRevoke = async (id: string) => {
    setBusyId(id);
    setBanner(null);
    try {
      await adminIntegrationsAPI.revokeShippingLookupKey(id);
      if (created?.id === id) setCreated(null);
      setPendingRevokeId(null);
      setBanner({ variant: 'ok', text: 'Đã thu hồi key. Đối tác dùng key này sẽ nhận 401.' });
      await load();
    } catch (err) {
      setBanner({ variant: 'error', text: (err as Error)?.message || 'Không thu hồi được' });
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section
      className="mb-6 rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
      aria-labelledby="shipping-lookup-keys-heading"
    >
      <h3 id="shipping-lookup-keys-heading" className="text-sm font-semibold text-gray-900">
        Cấp API key cho đối tác
      </h3>
      <p className="mt-1 text-xs text-gray-600">
        Key có hiệu lực ngay, không cần restart. Gửi key cho chatbot / CS / kho — không nhúng lên frontend khách.
        {configured ? (
          <span className="ml-1 text-emerald-800">API đang bật.</span>
        ) : (
          <span className="ml-1 text-amber-800">Chưa có key — API trả 503.</span>
        )}
      </p>

      <form onSubmit={onCreate} className="mt-4 space-y-3">
        <div>
          <label htmlFor="shipping-key-label" className="block text-xs font-medium text-gray-700 mb-1">
            Tên đối tác / nhãn
          </label>
          <input
            id="shipping-key-label"
            type="text"
            maxLength={80}
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Ví dụ: NanoAI, CS nội bộ"
            className="w-full max-w-md rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            autoComplete="off"
          />
        </div>
        {showPaste ? (
          <div>
            <label htmlFor="shipping-key-paste" className="block text-xs font-medium text-gray-700 mb-1">
              Dán key có sẵn (tuỳ chọn)
            </label>
            <input
              id="shipping-key-paste"
              type="text"
              value={pastedToken}
              onChange={(e) => setPastedToken(e.target.value)}
              placeholder="Dán token đang dùng (ví dụ key trong .env)"
              className="w-full max-w-md rounded-md border border-gray-300 px-3 py-2 text-sm font-mono focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              autoComplete="off"
            />
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setShowPaste(true)}
            className="text-xs text-blue-700 underline"
          >
            Gắn nhãn key đang có sẵn
          </button>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="submit"
            disabled={saving}
            className="rounded-md bg-blue-700 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800 disabled:opacity-60"
          >
            {saving ? 'Đang cấp…' : pastedToken.trim() ? 'Gắn nhãn key' : 'Tạo và cấp key'}
          </button>
        </div>
      </form>

      {banner ? (
        <div
          className={`mt-3 rounded-lg px-4 py-3 text-sm ${
            banner.variant === 'ok'
              ? 'border border-emerald-200 bg-emerald-50 text-emerald-900'
              : 'border border-red-200 bg-red-50 text-red-800'
          }`}
          role="status"
        >
          {banner.text}
        </div>
      ) : null}

      {created?.token ? (
        <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
          <p className="font-medium">Key «{created.label}» — sao chép gửi đối tác</p>
          <code className="mt-2 block break-all rounded bg-white/80 px-2 py-2 text-xs">{created.token}</code>
          <button
            type="button"
            onClick={() => void onCopyCreated()}
            className="mt-2 rounded-md bg-amber-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-900"
          >
            Sao chép key
          </button>
        </div>
      ) : null}

      {error ? (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}{' '}
          <button type="button" onClick={() => void load()} className="underline font-medium">
            Thử lại
          </button>
        </div>
      ) : null}

      {loading ? (
        <p className="mt-4 text-xs text-gray-500">Đang tải danh sách key…</p>
      ) : keys.length === 0 ? (
        <p className="mt-4 text-xs text-gray-500">Chưa cấp key trên form này.</p>
      ) : (
        <div className="mt-4 overflow-x-auto rounded-md border border-gray-200">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50 text-left text-gray-600">
                <th className="px-3 py-2 font-medium">Đối tác</th>
                <th className="px-3 py-2 font-medium">Key</th>
                <th className="px-3 py-2 font-medium">Cấp lúc</th>
                <th className="px-3 py-2 font-medium"> </th>
              </tr>
            </thead>
            <tbody>
              {keys.map((row) => (
                <tr key={row.id} className="border-b border-gray-100 last:border-0">
                  <td className="px-3 py-2">{row.label}</td>
                  <td className="px-3 py-2 font-mono text-xs text-gray-700">••••{row.last4}</td>
                  <td className="px-3 py-2 text-xs text-gray-600 whitespace-nowrap">
                    {formatCreatedAt(row.created_at)}
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    {pendingRevokeId === row.id ? (
                      <span className="inline-flex flex-wrap items-center gap-2 text-xs">
                        <span>Thu hồi «{row.label}»?</span>
                        <button
                          type="button"
                          disabled={busyId === row.id}
                          onClick={() => void onRevoke(row.id)}
                          className="font-medium text-red-700 underline disabled:opacity-60"
                        >
                          Xác nhận
                        </button>
                        <button
                          type="button"
                          onClick={() => setPendingRevokeId(null)}
                          className="text-gray-600 underline"
                        >
                          Hủy
                        </button>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-3">
                        <button
                          type="button"
                          disabled={busyId === row.id}
                          onClick={() => void onCopyExisting(row.id)}
                          className="text-xs font-medium text-blue-700 underline disabled:opacity-60"
                        >
                          Sao chép
                        </button>
                        <button
                          type="button"
                          disabled={busyId === row.id}
                          onClick={() => setPendingRevokeId(row.id)}
                          className="text-xs font-medium text-red-700 underline disabled:opacity-60"
                        >
                          Thu hồi
                        </button>
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {envKeyCount > 0 ? (
        <p className="mt-3 text-xs text-gray-500">
          Còn {envKeyCount} key trong <code className="bg-gray-100 px-1 rounded">SHIPPING_LOOKUP_API_KEY</code>{' '}
          (.env) — vẫn hoạt động, không hiện trên danh sách này. Muốn gắn nhãn thì dùng «Gắn nhãn key đang có sẵn».
        </p>
      ) : null}
    </section>
  );
}
