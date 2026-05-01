'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import AdminLayout from '@/components/admin/AdminLayout';
import { adminSiteEmbedAPI, type SiteEmbedCodeAdmin } from '@/lib/admin-api';

const NANO_PRESET = {
  platform: 'nanoai',
  category: 'embed',
  title: 'NanoAI — Chat / widget nhúng',
  placement: 'body_close' as const,
  sort_order: 84,
  hint: 'Dán mã nhúng (script/widget) từ bảng điều khiển NanoAI — thường là một hoặc nhiều thẻ script.',
};

const ZALO_PRESET = {
  platform: 'zalo',
  category: 'chat',
  title: 'Zalo — Chat / Widget Official Account',
  placement: 'body_close' as const,
  sort_order: 90,
  hint: 'Chỉ nhập OA ID (chuỗi số của Official Account).',
};

const FB_CHAT_PRESET = {
  platform: 'facebook',
  category: 'chat',
  title: 'Meta — Chat Plugin (Facebook)',
  placement: 'body_close' as const,
  sort_order: 80,
  hint: 'Chỉ nhập Page ID (số) cho plugin chat.',
};

function pickRows(list: SiteEmbedCodeAdmin[]) {
  const nano = list.find(
    (r) => r.platform?.toLowerCase() === 'nanoai' && r.category?.toLowerCase() === 'embed',
  );
  const zalo = list.find(
    (r) => r.platform?.toLowerCase() === 'zalo' && r.category?.toLowerCase() === 'chat',
  );
  const fbChat = list.find(
    (r) => r.platform?.toLowerCase() === 'facebook' && r.category?.toLowerCase() === 'chat',
  );
  return { nano, zalo, fbChat };
}

export default function AdminChatEmbedsPage() {
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);

  const [nanoId, setNanoId] = useState<number | null>(null);
  const [nanoContent, setNanoContent] = useState('');
  const [nanoActive, setNanoActive] = useState(true);

  const [zaloId, setZaloId] = useState<number | null>(null);
  const [zaloOaid, setZaloOaid] = useState('');
  const [zaloActive, setZaloActive] = useState(true);

  const [fbId, setFbId] = useState<number | null>(null);
  const [fbPageId, setFbPageId] = useState('');
  const [fbActive, setFbActive] = useState(true);

  const [saving, setSaving] = useState<string | null>(null);

  const showToast = (type: 'ok' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 4000);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const list = await adminSiteEmbedAPI.getAll();
      const { nano, zalo, fbChat } = pickRows(list);
      setNanoId(nano?.id ?? null);
      setNanoContent(nano?.content ?? '');
      setNanoActive(nano?.is_active ?? true);
      setZaloId(zalo?.id ?? null);
      setZaloOaid(zalo?.content ?? '');
      setZaloActive(zalo?.is_active ?? true);
      setFbId(fbChat?.id ?? null);
      setFbPageId(fbChat?.content ?? '');
      setFbActive(fbChat?.is_active ?? true);
    } catch {
      setToast({ type: 'err', msg: 'Không tải được cấu hình' });
      setTimeout(() => setToast(null), 4000);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const saveNano = async () => {
    if (nanoActive && !(nanoContent || '').trim()) {
      showToast('err', 'Đang bật NanoAI: cần dán mã nhúng hoặc tắt mục.');
      return;
    }
    setSaving('nano');
    try {
      if (nanoId != null) {
        await adminSiteEmbedAPI.update(nanoId, {
          content: nanoContent,
          is_active: nanoActive,
          placement: 'body_close',
        });
      } else {
        const row = await adminSiteEmbedAPI.create({
          ...NANO_PRESET,
          content: nanoContent,
          is_active: nanoActive,
        });
        setNanoId(row.id);
      }
      showToast('ok', 'Đã lưu mã nhúng NanoAI');
      await load();
    } catch (err) {
      showToast('err', (err as Error)?.message || 'Lỗi lưu');
    } finally {
      setSaving(null);
    }
  };

  const saveZalo = async () => {
    if (zaloActive && !(zaloOaid || '').trim()) {
      showToast('err', 'Đang bật Zalo: nhập OA ID hoặc tắt mục.');
      return;
    }
    setSaving('zalo');
    try {
      if (zaloId != null) {
        await adminSiteEmbedAPI.update(zaloId, {
          content: zaloOaid.trim(),
          is_active: zaloActive,
          placement: 'body_close',
        });
      } else {
        const row = await adminSiteEmbedAPI.create({
          ...ZALO_PRESET,
          content: zaloOaid.trim(),
          is_active: zaloActive,
        });
        setZaloId(row.id);
      }
      showToast('ok', 'Đã lưu cấu hình Zalo');
      await load();
    } catch (err) {
      showToast('err', (err as Error)?.message || 'Lỗi lưu');
    } finally {
      setSaving(null);
    }
  };

  const saveFb = async () => {
    if (fbActive && !(fbPageId || '').trim()) {
      showToast('err', 'Đang bật Facebook chat: nhập Page ID hoặc tắt mục.');
      return;
    }
    setSaving('fb');
    try {
      if (fbId != null) {
        await adminSiteEmbedAPI.update(fbId, {
          content: fbPageId.trim(),
          is_active: fbActive,
          placement: 'body_close',
        });
      } else {
        const row = await adminSiteEmbedAPI.create({
          ...FB_CHAT_PRESET,
          content: fbPageId.trim(),
          is_active: fbActive,
        });
        setFbId(row.id);
      }
      showToast('ok', 'Đã lưu cấu hình Facebook chat');
      await load();
    } catch (err) {
      showToast('err', (err as Error)?.message || 'Lỗi lưu');
    } finally {
      setSaving(null);
    }
  };

  return (
    <AdminLayout>
      <div className="p-6 max-w-3xl">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Nhúng chat: NanoAI, Zalo, Facebook</h1>
        <p className="text-gray-600 mb-4 text-sm leading-relaxed">
          Các mã được chèn cuối trang (trước khi đóng <code className="text-xs bg-gray-100 px-1 rounded">&lt;body&gt;</code>),
          cùng hệ thống với{' '}
          <Link href="/admin/embed-codes" className="text-[#ea580c] font-medium hover:underline">
            Mã nhúng đầy đủ
          </Link>
          . Sau khi lưu, khách xem site sẽ thấy widget tương ứng khi mục đang bật.
        </p>

        {toast && (
          <div
            className={`mb-4 px-4 py-2 rounded-lg text-white text-sm ${
              toast.type === 'ok' ? 'bg-emerald-600' : 'bg-red-600'
            }`}
          >
            {toast.msg}
          </div>
        )}

        {loading ? (
          <p className="text-gray-500">Đang tải...</p>
        ) : (
          <div className="space-y-6">
            <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <h2 className="text-lg font-semibold text-gray-900 mb-1">Mã nhúng chat NanoAI</h2>
              <p className="text-xs text-gray-500 mb-3">
                Dán nguyên đoạn script/widget do NanoAI cung cấp (có thể gồm nhiều thẻ).
              </p>
              <textarea
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-xs font-mono min-h-[140px] mb-3"
                placeholder="&lt;script&gt;...&lt;/script&gt;"
                value={nanoContent}
                onChange={(e) => setNanoContent(e.target.value)}
              />
              <label className="flex items-center gap-2 text-sm mb-3">
                <input
                  type="checkbox"
                  checked={nanoActive}
                  onChange={(e) => setNanoActive(e.target.checked)}
                />
                Đang bật hiển thị trên site
              </label>
              <button
                type="button"
                onClick={() => void saveNano()}
                disabled={saving === 'nano'}
                className="px-4 py-2 rounded-lg bg-slate-900 text-white text-sm font-medium hover:bg-slate-800 disabled:opacity-60"
              >
                {saving === 'nano' ? 'Đang lưu...' : 'Lưu NanoAI'}
              </button>
            </section>

            <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <h2 className="text-lg font-semibold text-gray-900 mb-1">Mã nhúng Zalo (OA Chat)</h2>
              <p className="text-xs text-gray-500 mb-3">
                Chỉ nhập OA ID (Official Account ID — chuỗi số). Để dán full HTML tùy biến, dùng trang mã nhúng đầy đủ.
              </p>
              <input
                type="text"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono mb-3"
                placeholder="Ví dụ: 1234567890123456789"
                value={zaloOaid}
                onChange={(e) => setZaloOaid(e.target.value)}
              />
              <label className="flex items-center gap-2 text-sm mb-3">
                <input
                  type="checkbox"
                  checked={zaloActive}
                  onChange={(e) => setZaloActive(e.target.checked)}
                />
                Đang bật hiển thị trên site
              </label>
              <button
                type="button"
                onClick={() => void saveZalo()}
                disabled={saving === 'zalo'}
                className="px-4 py-2 rounded-lg bg-slate-900 text-white text-sm font-medium hover:bg-slate-800 disabled:opacity-60"
              >
                {saving === 'zalo' ? 'Đang lưu...' : 'Lưu Zalo'}
              </button>
            </section>

            <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <h2 className="text-lg font-semibold text-gray-900 mb-1">Mã nhúng Facebook (Chat plugin)</h2>
              <p className="text-xs text-gray-500 mb-3">
                Chỉ nhập Page ID (số) của Fanpage cho Customer Chat Plugin.
              </p>
              <input
                type="text"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono mb-3"
                placeholder="Ví dụ: 123456789012345"
                value={fbPageId}
                onChange={(e) => setFbPageId(e.target.value)}
              />
              <label className="flex items-center gap-2 text-sm mb-3">
                <input
                  type="checkbox"
                  checked={fbActive}
                  onChange={(e) => setFbActive(e.target.checked)}
                />
                Đang bật hiển thị trên site
              </label>
              <button
                type="button"
                onClick={() => void saveFb()}
                disabled={saving === 'fb'}
                className="px-4 py-2 rounded-lg bg-slate-900 text-white text-sm font-medium hover:bg-slate-800 disabled:opacity-60"
              >
                {saving === 'fb' ? 'Đang lưu...' : 'Lưu Facebook'}
              </button>
            </section>
          </div>
        )}
      </div>
    </AdminLayout>
  );
}
