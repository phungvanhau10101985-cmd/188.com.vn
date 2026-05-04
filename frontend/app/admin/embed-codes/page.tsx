'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { adminSiteEmbedAPI, type SiteEmbedCodeAdmin } from '@/lib/admin-api';

const PLATFORM_LABEL: Record<string, string> = {
  google: 'Google',
  facebook: 'Facebook / Meta',
  tiktok: 'TikTok',
  zalo: 'Zalo',
  nanoai: 'NanoAI',
  other: 'Khác',
};

const PLACEMENT_LABEL: Record<string, string> = {
  head: 'Trong head (đầu trang)',
  body_open: 'Đầu thân body',
  body_close: 'Cuối body (trước khi đóng)',
};

/** Người dùng chỉ nhập một mã/ID — backend dựng sẵn HTML/JS */
const ID_HINT: Record<string, Record<string, string>> = {
  google: {
    ga4: 'Chỉ nhập Measurement ID (ví dụ G-XXXXXXXXXX). Không dán nguyên đoạn <script>.',
    gtm: 'Chỉ nhập Container ID (ví dụ GTM-XXXXXXX). Hệ thống chèn đủ fragment head + noscript.',
    ads:
      'Mã AW-XXXXXXXX — dùng cho chuyển đổi và tiếp thị lại động Retail (Merchant Center trong Google Ads). Chỉ cần một mã đang bật nếu dùng cùng đích.',
    search_console:
      'Chỉ nhập chuỗi xác minh của Google Search Console — hoặc bật "Dán full HTML/meta" nếu dán cả thẻ.',
    merchant_center:
      'Merchant Center (xác minh website): trong Cài đặt chương trình / Xác minh URL, chọn Thẻ HTML — chỉ dán mã trong thuộc tính content (hoặc dán cả thẻ <meta> rồi bật chế độ full HTML).',
  },
  facebook: {
    pixel:
      'Pixel Meta — remarketing động / Advantage+ catalogue; chỉ nhập Pixel ID; sự kiện sản phẩm bổ sung bằng fbq trên trang.',
    domain: 'Chỉ nhập giá trị content trong Meta domain verification.',
    chat: 'Chỉ nhập Page ID (số) cho plugin chat.',
    capi_token:
      'Conversion API: Access Token Events Manager (Facebook). Không lộ HTML; ghép Pixel + API máy chủ.',
  },
  tiktok: {
    pixel: 'TikTok Pixel ID trong Events Manager — remarketing động / catalogue; gửi ttq.track từ trang là bước bổ sung.',
    capi_token:
      'TikTok Events API access token — chỉ máy chủ; khuyến nghị dùng cùng Pixel Web.',
  },
  zalo: {
    chat: 'Chỉ nhập OA ID (Official Account ID, thường là chữ số dài).',
    other: 'Nếu cần iframe/script tùy biến, bật dán full HTML bên dưới.',
  },
  nanoai: {
    embed: 'Dán mã nhúng (script/widget) từ bảng điều khiển NanoAI — vị trí chèn theo “Vị trí chèn” bên dưới.',
  },
};

function platformOrder(p: string): number {
  const i = ['google', 'facebook', 'tiktok', 'zalo', 'nanoai', 'other'].indexOf(p.toLowerCase());
  return i === -1 ? 99 : i;
}

type FormState = {
  platform: string;
  category: string;
  title: string;
  placement: string;
  content: string;
  hint: string;
  is_active: boolean;
  sort_order: number;
  /** Dán đầy đủ HTML (chỉ dùng cho mục mở rộng) */
  useFullHtml?: boolean;
};

function emptyForm(): FormState {
  return {
    platform: 'google',
    category: 'custom',
    title: '',
    placement: 'head',
    content: '',
    hint: '',
    is_active: true,
    sort_order: 500,
    useFullHtml: false,
  };
}

function looksHtml(s: string) {
  const t = (s || '').trim();
  return t.startsWith('<') || /<script|<meta|<noscript|<iframe/i.test(t);
}

type FieldKind = 'id' | 'capi' | 'html';

function classifyField(platform: string, category: string, contentSnap: string, useFullHtml?: boolean): FieldKind {
  const p = (platform || '').toLowerCase();
  const c = (category || '').toLowerCase();
  if (p === 'nanoai') return 'html';
  if ((p === 'facebook' || p === 'tiktok') && c === 'capi_token') return 'capi';
  if (useFullHtml || looksHtml(contentSnap || '')) return 'html';

  const idMatrix: Record<string, string[]> = {
    google: ['ga4', 'gtm', 'ads', 'search_console', 'merchant_center'],
    facebook: ['pixel', 'domain', 'chat'],
    tiktok: ['pixel'],
    zalo: ['chat'],
  };
  const row = idMatrix[p];
  if (row && row.includes(c)) return 'id';
  return 'html';
}

function hintLine(platform: string, category: string): string | null {
  return ID_HINT[platform.toLowerCase()]?.[category.toLowerCase()] ?? null;
}

export default function AdminEmbedCodesPage() {
  const [list, setList] = useState<SiteEmbedCodeAdmin[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingSnapshot, setEditingSnapshot] = useState<SiteEmbedCodeAdmin | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);

  const showToast = (type: 'ok' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 4000);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await adminSiteEmbedAPI.getAll();
      setList(data);
    } catch {
      showToast('err', 'Không tải được danh sách mã nhúng');
    } finally {
      setLoading(false);
    }
  }, []);

  /** Ẩn mục NanoAI try_on (đã bỏ khỏi preset; có thể còn bản ghi DB cũ cho đến khi API xóa khi start). */
  const listForDisplay = useMemo(
    () =>
      list.filter(
        (row) => !(row.platform?.toLowerCase() === 'nanoai' && row.category?.toLowerCase() === 'try_on'),
      ),
    [list],
  );

  useEffect(() => {
    load();
  }, [load]);

  const grouped = useMemo(() => {
    const buckets = new Map<string, SiteEmbedCodeAdmin[]>();
    for (const row of listForDisplay) {
      const k = row.platform?.toLowerCase() || 'other';
      const arr = buckets.get(k) ?? [];
      arr.push(row);
      buckets.set(k, arr);
    }
    for (const [, arr] of buckets) {
      arr.sort((a, b) => (a.sort_order !== b.sort_order ? a.sort_order - b.sort_order : a.id - b.id));
    }
    return [...buckets.entries()].sort(([a], [b]) => platformOrder(a) - platformOrder(b));
  }, [listForDisplay]);

  const openAdd = () => {
    setEditingId(null);
    setEditingSnapshot(null);
    setForm(emptyForm());
    setShowForm(true);
  };

  const openEdit = (row: SiteEmbedCodeAdmin) => {
    setEditingId(row.id);
    setEditingSnapshot(row);
    const ufh =
      classifyField(row.platform, row.category, row.content || '', false) === 'html';
    setForm({
      platform: row.platform || 'google',
      category: row.category || 'custom',
      title: row.title,
      placement: row.placement || 'head',
      content: row.content || '',
      hint: row.hint || '',
      is_active: row.is_active,
      sort_order: row.sort_order,
      useFullHtml:
        ufh || (row.category || '').toLowerCase() === 'other' || (row.platform || '').toLowerCase() === 'other',
    });
    setShowForm(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.title.trim()) {
      showToast('err', 'Vui lòng nhập tiêu đề');
      return;
    }
    const isCapi =
      ['facebook', 'tiktok'].includes(form.platform?.toLowerCase() ?? '') &&
      form.category?.toLowerCase() === 'capi_token';
    const emptyBody = !(form.content || '').trim();
    const keepCapiSecret =
      editingId != null && isCapi && !!editingSnapshot?.secret_configured && emptyBody;

    if (form.is_active && emptyBody && !keepCapiSecret) {
      showToast('err', 'Mục đang bật: nhập mã / ID / HTML hoặc tắt mục.');
      return;
    }

    const common = {
      platform: form.platform.trim() || 'other',
      category: form.category.trim() || 'custom',
      title: form.title.trim(),
      placement: form.placement,
      is_active: form.is_active,
      sort_order: form.sort_order,
      hint: form.hint.trim() || undefined,
    };

    try {
      if (editingId != null) {
        const patch: Partial<SiteEmbedCodeAdmin> = {
          ...common,
        };
        if (!keepCapiSecret) {
          patch.content = form.content;
        }
        await adminSiteEmbedAPI.update(editingId, patch);
      } else {
        await adminSiteEmbedAPI.create({
          ...common,
          content: form.content,
        });
      }
      showToast('ok', 'Đã lưu');
      setShowForm(false);
      load();
    } catch (err) {
      showToast('err', (err as Error)?.message || 'Lỗi lưu');
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm('Xóa mục mã nhúng này?')) return;
    try {
      await adminSiteEmbedAPI.delete(id);
      showToast('ok', 'Đã xóa');
      load();
    } catch {
      showToast('err', 'Không xóa được');
    }
  };

  const fk = classifyField(form.platform, form.category, form.content, !!form.useFullHtml);
  const hint = hintLine(form.platform, form.category);

  return (
      <>
      <div className="p-6 max-w-5xl">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Mã nhúng và thẻ quảng cáo</h1>
        <p className="text-gray-600 mb-3">
          GA4 / GTM / Google Ads AW- (bao gồm tiếp thị động Retail), Pixel Meta và TikTok (remarketing động catalogue), Zalo OA:{' '}
          <strong className="font-medium">chỉ cần mã một dòng</strong> — không cần dán base code đầy đủ.
          Tokens Conversion API Facebook / TikTok chỉ máy chủ, không trong HTML public.
        </p>
        <p className="text-gray-500 text-sm mb-4">
          API máy chủ Meta (Conversion API — cần <code>FACEBOOK_CAPI_INGEST_SECRET</code> trên backend):{' '}
          <span className="font-mono text-xs">POST /api/v1/embed-codes/facebook/capi/send-event</span> với{' '}
          <span className="font-mono">Authorization: Bearer {'<bí_mật>'}</span>.
        </p>
        <div className="rounded-xl border border-amber-200 bg-amber-50 text-amber-950 text-sm px-4 py-3 mb-6">
          <p className="font-medium mb-1">Vị trí chèn sau khi dựng sẵn</p>
          <ul className="list-disc pl-5 space-y-1 text-amber-900/90">
            <li><span className="font-medium">Trong head</span> — GA4, GTM (phần script), Ads, Pixel, meta xác minh.</li>
            <li><span className="font-medium">Đầu body</span> — GTM auto thêm iframe noscript vào đây (một khối ô nhớ duy nhất).</li>
            <li><span className="font-medium">Cuối body</span> — Zalo/Facebook Chat plugin.</li>
          </ul>
        </div>

        <button
          type="button"
          onClick={openAdd}
          className="mb-6 px-4 py-2.5 bg-slate-900 text-white rounded-lg hover:bg-slate-800 text-sm font-medium"
        >
          + Thêm mục mã nhúng
        </button>

        {toast && (
          <div
            className={`fixed top-24 right-6 z-[60] px-4 py-2 rounded-lg shadow-lg text-white text-sm ${
              toast.type === 'ok' ? 'bg-emerald-600' : 'bg-red-600'
            }`}
          >
            {toast.msg}
          </div>
        )}

        {loading ? (
          <p className="text-gray-500">Đang tải...</p>
        ) : listForDisplay.length === 0 ? (
          <p className="text-gray-500">Chưa có dữ liệu. Nhấn &quot;Thêm mục&quot; hoặc khởi động lại API để tạo mẫu.</p>
        ) : (
          <div className="space-y-8">
            {grouped.map(([platform, rows]) => (
              <section key={platform}>
                <h2 className="text-lg font-semibold text-gray-800 border-b border-gray-200 pb-2 mb-3">
                  {PLATFORM_LABEL[platform] || platform}
                </h2>
                <div className="border border-gray-200 rounded-xl overflow-hidden bg-white divide-y divide-gray-100">
                  {rows.map((row) => {
                    const ck = classifyField(row.platform, row.category, row.content || '');
                    const capiMasked =
                      ['facebook', 'tiktok'].includes(row.platform?.toLowerCase() ?? '') &&
                      row.category?.toLowerCase() === 'capi_token' &&
                      row.secret_configured;
                    return (
                      <div key={row.id} className="px-4 py-3 flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2 mb-1">
                            <span className="font-medium text-gray-900">{row.title}</span>
                            <span
                              className={`text-xs px-2 py-0.5 rounded-full ${
                                row.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-gray-100 text-gray-600'
                              }`}
                            >
                              {row.is_active ? 'Bật' : 'Tắt'}
                            </span>
                            <span className="text-xs text-gray-500 font-mono">{PLACEMENT_LABEL[row.placement] || row.placement}</span>
                            {row.category && row.category !== 'custom' && (
                              <span className="text-xs px-2 py-0.5 rounded bg-gray-50 text-gray-600">{row.category}</span>
                            )}
                            {ck === 'id' ? (
                              <span className="text-xs px-2 py-0.5 rounded bg-blue-50 text-blue-800">Chỉ mã</span>
                            ) : ck === 'capi' ? (
                              <span className="text-xs px-2 py-0.5 rounded bg-purple-50 text-purple-800">Máy chủ</span>
                            ) : null}
                          </div>
                          <p className="text-xs text-gray-500 line-clamp-2 font-mono">
                            {capiMasked
                              ? 'Token Conversion API đã lưu (không hiển thị)'
                              : (row.content || '').trim()
                                ? `${(row.content || '').trim().slice(0, 140)}${(row.content || '').trim().length > 140 ? '…' : ''}`
                                : 'Chưa nhập — không hiển thị / không gửi CAPI'}
                          </p>
                          {row.hint && <p className="text-xs text-slate-500 mt-1">{row.hint}</p>}
                        </div>
                        <div className="flex gap-3 shrink-0">
                          <button type="button" onClick={() => openEdit(row)} className="text-blue-600 hover:underline text-sm">
                            Sửa
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDelete(row.id)}
                            className="text-red-600 hover:underline text-sm"
                          >
                            Xóa
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" role="dialog">
          <div className="bg-white rounded-2xl shadow-xl max-w-xl w-full max-h-[92vh] overflow-y-auto">
            <div className="sticky top-0 bg-white border-b border-gray-100 px-6 py-4 flex items-start justify-between gap-4">
              <h2 className="text-lg font-bold text-gray-900">
                {editingId != null ? 'Sửa mã nhúng' : 'Thêm mã nhúng'}
              </h2>
              <button type="button" onClick={() => setShowForm(false)} className="p-2 rounded-lg text-gray-500 hover:bg-gray-100" aria-label="Đóng">
                ×
              </button>
            </div>
            <form onSubmit={handleSubmit} className="px-6 py-5 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-800 mb-1">Nền tảng</label>
                <select
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                  value={form.platform}
                  onChange={(e) => setForm((f) => ({ ...f, platform: e.target.value }))}
                >
                  <option value="google">Google</option>
                  <option value="facebook">Facebook / Meta</option>
                  <option value="tiktok">TikTok</option>
                  <option value="zalo">Zalo</option>
                  <option value="nanoai">NanoAI</option>
                  <option value="other">Khác</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-800 mb-1">Loại (keyword nội bộ)</label>
                <input
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono"
                  placeholder="ga4, gtm, ads, pixel, capi_token…"
                  value={form.category}
                  onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-800 mb-1">Tiêu đề hiển thị *</label>
                <input
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                  required
                  value={form.title}
                  onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-800 mb-1">Vị trí chèn</label>
                <select
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                  value={form.placement}
                  onChange={(e) => setForm((f) => ({ ...f, placement: e.target.value }))}
                >
                  <option value="head">{PLACEMENT_LABEL.head}</option>
                  <option value="body_open">{PLACEMENT_LABEL.body_open}</option>
                  <option value="body_close">{PLACEMENT_LABEL.body_close}</option>
                </select>
              </div>

              {fk !== 'html' && (
                <label className="flex items-start gap-2 text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={!!form.useFullHtml}
                    onChange={(e) => setForm((f) => ({ ...f, useFullHtml: e.target.checked }))}
                  />
                  <span>Dán full HTML / script đầy đủ (nâng cao — vô hiệu hóa chế độ &quot;chỉ mã&quot;)</span>
                </label>
              )}

              {hint && fk !== 'html' && !form.useFullHtml && (
                <p className="text-xs text-slate-600 bg-slate-50 border border-slate-100 rounded-lg px-3 py-2">{hint}</p>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-800 mb-1">
                  {fk === 'capi'
                    ? 'Access Token Conversion API *'
                    : fk === 'html' || form.useFullHtml
                      ? 'Mã HTML / JavaScript đầy đủ'
                      : 'Chỉ nhập mã / ID (một dòng)'}
                </label>
                {fk === 'capi' ? (
                  <input
                    type="password"
                    autoComplete="new-password"
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono"
                    placeholder={
                      editingId && editingSnapshot?.secret_configured
                        ? '(để trống nếu giữ nguyên token đã lưu)'
                        : 'Dán access token Meta'
                    }
                    value={form.content}
                    onChange={(e) => setForm((f) => ({ ...f, content: e.target.value }))}
                  />
                ) : fk === 'html' || form.useFullHtml ? (
                  <textarea
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-xs font-mono min-h-[180px]"
                    placeholder="&lt;script&gt;...&lt;/script&gt; hoặc &lt;meta ... /&gt;"
                    value={form.content}
                    onChange={(e) => setForm((f) => ({ ...f, content: e.target.value }))}
                  />
                ) : (
                  <input
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono"
                    placeholder={
                      classifyField(form.platform, form.category, '') === 'id'
                        ? 'Ví dụ: GTM-XXX, G-XXX, Pixel ID …'
                        : ''
                    }
                    value={form.content}
                    onChange={(e) => setForm((f) => ({ ...f, content: e.target.value }))}
                  />
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-800 mb-1">Gợi ý (chỉ admin)</label>
                <input
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                  value={form.hint}
                  onChange={(e) => setForm((f) => ({ ...f, hint: e.target.value }))}
                />
              </div>

              <div className="flex flex-wrap gap-6 items-center">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={form.is_active}
                    onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
                  />
                  Đang bật
                </label>
                <div className="flex items-center gap-2 text-sm">
                  <span>Thứ tự</span>
                  <input
                    type="number"
                    className="w-24 rounded-lg border border-gray-300 px-2 py-1"
                    value={form.sort_order}
                    onChange={(e) => setForm((f) => ({ ...f, sort_order: Number(e.target.value) || 0 }))}
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button type="button" className="px-4 py-2 rounded-lg border border-gray-300 text-sm" onClick={() => setShowForm(false)}>
                  Hủy
                </button>
                <button type="submit" className="px-4 py-2 rounded-lg bg-slate-900 text-white text-sm font-medium">
                  Lưu
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      </>
  );
}
