'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { adminNanoAiInboxAPI } from '@/lib/admin-api';

function safeHttpUrl(raw: string): string | null {
  const t = (raw || '').trim();
  if (!t) return null;
  let parsed: URL;
  try {
    parsed = new URL(t);
  } catch {
    return null;
  }
  if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') return null;
  if (!parsed.hostname) return null;
  return parsed.toString();
}

export default function AdminNanoAiInboxPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedUrl, setSavedUrl] = useState('');
  const [draft, setDraft] = useState('');
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);

  const showToast = (type: 'ok' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 4000);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await adminNanoAiInboxAPI.get();
      const url = (data.url || '').trim();
      setSavedUrl(url);
      setDraft(url);
    } catch {
      showToast('err', 'Không tải được link hội thoại');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async () => {
    const url = safeHttpUrl(draft);
    if (draft.trim() && !url) {
      showToast('err', 'Link cần bắt đầu bằng http:// hoặc https://');
      return;
    }
    setSaving(true);
    try {
      const saved = await adminNanoAiInboxAPI.save(url || '');
      const next = (saved.url || '').trim();
      setSavedUrl(next);
      setDraft(next);
      showToast('ok', next ? 'Đã lưu link hội thoại' : 'Đã xóa link hội thoại');
    } catch (err) {
      showToast('err', (err as Error)?.message || 'Lỗi lưu');
    } finally {
      setSaving(false);
    }
  };

  const draftUrl = safeHttpUrl(draft);
  const savedHref = safeHttpUrl(savedUrl);
  const draftDirty = (draftUrl || '') !== (savedHref || '');

  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Xem hội thoại</h1>
      <p className="text-gray-600 mb-4 text-sm leading-relaxed">
        Dán link hộp thư shop trên NanoAI (ví dụ trang inbox theo partner). Sau khi lưu, bấm{' '}
        <span className="font-medium text-gray-800">Mở hội thoại</span> để mở đúng link đó trong tab mới.
        Link này chỉ dùng trong quản trị, không hiện trên site khách.
      </p>

      {toast && (
        <div
          className={`mb-4 px-4 py-2 rounded-lg text-white text-sm ${
            toast.type === 'ok' ? 'bg-emerald-600' : 'bg-red-600'
          }`}
          role="status"
        >
          {toast.msg}
        </div>
      )}

      {loading ? (
        <p className="text-gray-500">Đang tải...</p>
      ) : (
        <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900 mb-1">Link shop chat NanoAI</h2>
          <p className="text-xs text-gray-500 mb-3">
            Lấy từ NanoAI, dạng{' '}
            <code className="text-[11px] bg-gray-100 px-1 rounded break-all">
              https://nanoai.vn/dashboard/messaging/inbox?partner=…
            </code>
          </p>
          <label className="block text-sm font-medium text-gray-800 mb-1" htmlFor="nanoai-inbox-url">
            Link hội thoại
          </label>
          <input
            id="nanoai-inbox-url"
            type="url"
            inputMode="url"
            autoComplete="off"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm mb-4"
            placeholder="https://nanoai.vn/dashboard/messaging/inbox?partner=…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => void save()}
              disabled={saving}
              className="px-4 py-2 rounded-lg bg-slate-900 text-white text-sm font-medium hover:bg-slate-800 disabled:opacity-60"
            >
              {saving ? 'Đang lưu...' : 'Lưu link'}
            </button>
            {draftUrl ? (
              <a
                href={draftUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex px-4 py-2 rounded-lg bg-[#ea580c] text-white text-sm font-medium hover:bg-[#c2410c]"
              >
                Mở hội thoại
              </a>
            ) : (
              <button
                type="button"
                onClick={() =>
                  showToast(
                    'err',
                    draft.trim()
                      ? 'Link cần bắt đầu bằng http:// hoặc https://'
                      : 'Dán link hộp thư NanoAI rồi bấm Mở hội thoại.',
                  )
                }
                className="px-4 py-2 rounded-lg bg-[#ea580c] text-white text-sm font-medium hover:bg-[#c2410c]"
              >
                Mở hội thoại
              </button>
            )}
          </div>
          {savedHref ? (
            <p className="mt-3 text-xs text-gray-500 break-all">
              Đang lưu:{' '}
              <a href={savedHref} target="_blank" rel="noopener noreferrer" className="text-[#ea580c] hover:underline">
                {savedHref}
              </a>
              {draftDirty ? ' — ô nhập đang khác link đã lưu. Bấm Lưu link nếu muốn giữ bản mới.' : ''}
            </p>
          ) : (
            <p className="mt-3 text-xs text-gray-500">
              {draftUrl
                ? 'Link trong ô chưa được lưu. Bấm Lưu link để lần sau vẫn mở được.'
                : 'Chưa lưu link. Dán URL rồi bấm Lưu link.'}
            </p>
          )}
          <p className="mt-4 text-xs text-gray-500">
            Mã widget chat trên site vẫn cấu hình ở{' '}
            <Link href="/admin/chat-embeds" className="text-[#ea580c] font-medium hover:underline">
              Chat & MXH
            </Link>
            .
          </p>
        </section>
      )}
    </div>
  );
}
