'use client';

import { Suspense, useCallback, useEffect, useId, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { adminSiteErrorsAPI, type SiteErrorItem, type SiteErrorList } from '@/lib/admin-api';

const SOURCE_LABEL: Record<string, string> = {
  server: 'API',
  web: 'Trình duyệt',
  web_server: 'Server web',
};

function formatDt(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'short' });
}

function sourceBadge(source: string): string {
  if (source === 'server') return 'bg-red-100 text-red-800';
  if (source === 'web_server') return 'bg-orange-100 text-orange-800';
  return 'bg-slate-100 text-slate-700';
}

export default function AdminErrorsPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-slate-500">Đang tải…</div>}>
      <AdminErrorsBody />
    </Suspense>
  );
}

function AdminErrorsBody() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const focusId = Number(searchParams.get('id') || '') || null;
  const [days, setDays] = useState(7);
  const [source, setSource] = useState('');
  const [status, setStatus] = useState('open');
  const [query, setQuery] = useState('');
  const [draftQuery, setDraftQuery] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState<SiteErrorList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<SiteErrorItem | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);
  const detailReq = useRef(0);
  const titleId = useId();

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    adminSiteErrorsAPI
      .list({ days, source, status, q: query, page })
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Không tải được danh sách lỗi');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [days, source, status, query, page]);

  useEffect(() => load(), [load]);

  const openDetail = useCallback((id: number) => {
    const req = ++detailReq.current;
    setDetailLoading(true);
    setDetailError(null);
    setSelected(null);
    adminSiteErrorsAPI
      .get(id)
      .then((row) => {
        if (req === detailReq.current) setSelected(row);
      })
      .catch((err: unknown) => {
        if (req !== detailReq.current) return;
        setDetailError(err instanceof Error ? err.message : 'Không tải được chi tiết');
      })
      .finally(() => {
        if (req === detailReq.current) setDetailLoading(false);
      });
  }, []);

  useEffect(() => {
    if (focusId) openDetail(focusId);
  }, [focusId, openDetail]);

  const closeDetail = useCallback(() => {
    detailReq.current += 1;
    setSelected(null);
    setDetailError(null);
    setDetailLoading(false);
  }, []);

  useEffect(() => {
    if (!selected && !detailLoading && !detailError) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeDetail();
    };
    window.addEventListener('keydown', onKey);
    closeRef.current?.focus();
    return () => window.removeEventListener('keydown', onKey);
  }, [selected, detailLoading, detailError, closeDetail]);

  const markResolved = async (resolved: boolean) => {
    if (!selected) return;
    setSaving(true);
    setDetailError(null);
    try {
      const row = await adminSiteErrorsAPI.setResolved(selected.id, resolved);
      setSelected(row);
      load();
    } catch (err: unknown) {
      setDetailError(err instanceof Error ? err.message : 'Không lưu được trạng thái');
    } finally {
      setSaving(false);
    }
  };

  const summary = data?.summary;
  const totalPages = Math.max(1, Math.ceil((data?.total || 0) / (data?.page_size || 40)));

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <h1 className="text-2xl font-bold text-slate-900">Quản lý lỗi</h1>
      <p className="mt-2 max-w-3xl text-sm text-slate-600">
        Ghi lại lỗi trên trình duyệt và log server (mức ERROR). Khi log server có lỗi, hệ thống gửi email cho admin —
        mỗi lỗi tối đa một lần trong ngày (giờ Việt Nam).
      </p>

      <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        <SummaryCard label="Lỗi hôm nay" value={summary?.today_errors} />
        <SummaryCard label="Số lần hôm nay" value={summary?.today_occurrences} />
        <SummaryCard label="Email đã gửi hôm nay" value={summary?.today_emails} />
        <SummaryCard label="Chưa xử lý" value={summary?.open_count} />
      </div>

      <form
        className="mt-5 flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          setPage(1);
          setQuery(draftQuery.trim());
        }}
      >
        <label className="text-sm text-slate-700">
          Khoảng
          <select
            value={days}
            onChange={(event) => {
              setPage(1);
              setDays(Number(event.target.value));
            }}
            className="mt-1 block rounded-lg border border-slate-300 bg-white px-3 py-2"
          >
            <option value={1}>Hôm nay</option>
            <option value={7}>7 ngày</option>
            <option value={30}>30 ngày</option>
          </select>
        </label>
        <label className="text-sm text-slate-700">
          Nguồn
          <select
            value={source}
            onChange={(event) => {
              setPage(1);
              setSource(event.target.value);
            }}
            className="mt-1 block rounded-lg border border-slate-300 bg-white px-3 py-2"
          >
            <option value="">Tất cả</option>
            <option value="server">API</option>
            <option value="web_server">Server web</option>
            <option value="web">Trình duyệt</option>
          </select>
        </label>
        <label className="text-sm text-slate-700">
          Trạng thái
          <select
            value={status}
            onChange={(event) => {
              setPage(1);
              setStatus(event.target.value);
            }}
            className="mt-1 block rounded-lg border border-slate-300 bg-white px-3 py-2"
          >
            <option value="open">Chưa xử lý</option>
            <option value="done">Đã xử lý</option>
            <option value="all">Tất cả</option>
          </select>
        </label>
        <label className="min-w-[12rem] flex-1 text-sm text-slate-700">
          Tìm nội dung hoặc đường dẫn
          <input
            value={draftQuery}
            onChange={(event) => setDraftQuery(event.target.value)}
            className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2"
            placeholder="Ví dụ: checkout, ValueError"
          />
        </label>
        <button type="submit" className="rounded-lg bg-[#ea580c] px-4 py-2 text-sm font-medium text-white hover:bg-[#c2410c]">
          Lọc
        </button>
        <button
          type="button"
          onClick={() => load()}
          className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Làm mới
        </button>
      </form>

      {error ? (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}{' '}
          <button type="button" onClick={() => load()} className="font-medium underline">
            Thử lại
          </button>
        </div>
      ) : null}

      {loading ? <p className="mt-6 text-sm text-slate-500">Đang tải danh sách lỗi…</p> : null}

      {!loading && !error && (data?.items.length || 0) === 0 ? (
        <p className="mt-6 rounded-lg border border-dashed border-slate-300 bg-white px-4 py-8 text-center text-sm text-slate-500">
          Không có lỗi trong khoảng này.
        </p>
      ) : null}

      {!loading && (data?.items.length || 0) > 0 ? (
        <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2 font-medium">Thời điểm</th>
                <th className="px-3 py-2 font-medium">Nguồn</th>
                <th className="px-3 py-2 font-medium">Nội dung</th>
                <th className="px-3 py-2 font-medium">Số lần</th>
                <th className="px-3 py-2 font-medium">Email</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((item) => (
                <tr key={item.id} className="border-t border-slate-100 align-top">
                  <td className="whitespace-nowrap px-3 py-3 text-slate-600">{formatDt(item.last_seen_at)}</td>
                  <td className="px-3 py-3">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${sourceBadge(item.source)}`}>
                      {SOURCE_LABEL[item.source] || item.source}
                    </span>
                  </td>
                  <td className="px-3 py-3">
                    <button
                      type="button"
                      onClick={() => {
                        if (focusId === item.id) openDetail(item.id);
                        else router.replace(`/admin/errors?id=${item.id}`, { scroll: false });
                      }}
                      className="text-left font-medium text-slate-900 underline-offset-2 hover:underline"
                    >
                      {item.message}
                    </button>
                    {item.path ? <div className="mt-1 text-xs text-slate-500">{item.path}</div> : null}
                  </td>
                  <td className="px-3 py-3 tabular-nums">{item.occurrence_count}</td>
                  <td className="px-3 py-3 text-xs text-slate-600">
                    {item.source === 'web' ? 'Không gửi' : item.email_sent_at ? `Đã gửi ${formatDt(item.email_sent_at)}` : 'Chưa gửi'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {totalPages > 1 ? (
        <div className="mt-4 flex items-center justify-between text-sm">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage((value) => Math.max(1, value - 1))}
            className="rounded-lg border border-slate-300 px-3 py-1.5 disabled:opacity-40"
          >
            Trước
          </button>
          <span className="text-slate-500">
            Trang {page}/{totalPages}
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => setPage((value) => value + 1)}
            className="rounded-lg border border-slate-300 px-3 py-1.5 disabled:opacity-40"
          >
            Sau
          </button>
        </div>
      ) : null}

      {selected || detailLoading || detailError ? (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center" onClick={closeDetail}>
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            className="max-h-[85vh] w-full max-w-3xl overflow-y-auto rounded-2xl bg-white p-5 shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <h2 id={titleId} className="text-lg font-semibold text-slate-900">
                Chi tiết lỗi
              </h2>
              <button
                ref={closeRef}
                type="button"
                onClick={closeDetail}
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
                aria-label="Đóng chi tiết lỗi"
              >
                Đóng
              </button>
            </div>
            {detailLoading ? <p className="mt-4 text-sm text-slate-500">Đang tải chi tiết…</p> : null}
            {detailError ? (
              <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {detailError}
              </div>
            ) : null}
            {selected ? (
              <div className="mt-4 space-y-3 text-sm text-slate-700">
                <p className="whitespace-pre-wrap break-words font-medium text-slate-900">{selected.message}</p>
                <p>
                  <span className="text-slate-500">Nguồn:</span> {SOURCE_LABEL[selected.source] || selected.source}
                  {selected.logger_name ? ` · ${selected.logger_name}` : ''}
                  {selected.exc_type ? ` · ${selected.exc_type}` : ''}
                </p>
                <p>
                  <span className="text-slate-500">Đường dẫn:</span> {selected.method} {selected.path || '—'}
                </p>
                <p>
                  <span className="text-slate-500">Lần đầu:</span> {formatDt(selected.first_seen_at)} ·{' '}
                  <span className="text-slate-500">Lần cuối:</span> {formatDt(selected.last_seen_at)} ·{' '}
                  <span className="text-slate-500">Số lần:</span> {selected.occurrence_count}
                </p>
                <p>
                  <span className="text-slate-500">Email admin:</span>{' '}
                  {selected.source === 'web'
                    ? 'Lỗi trình duyệt không gửi email'
                    : selected.email_sent_at
                      ? `Đã gửi ${formatDt(selected.email_sent_at)}`
                      : 'Chưa gửi trong ngày này'}
                </p>
                {selected.client_ip ? (
                  <p>
                    <span className="text-slate-500">IP:</span> {selected.client_ip}
                  </p>
                ) : null}
                {selected.detail ? (
                  <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-slate-950 p-3 text-xs text-slate-100">
                    {selected.detail}
                  </pre>
                ) : (
                  <p className="text-slate-500">Không có stack.</p>
                )}
                <div className="flex gap-2">
                  {selected.resolved ? (
                    <button
                      type="button"
                      disabled={saving}
                      onClick={() => markResolved(false)}
                      className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium disabled:opacity-50"
                    >
                      Mở lại
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled={saving}
                      onClick={() => markResolved(true)}
                      className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                    >
                      {saving ? 'Đang lưu…' : 'Đánh dấu đã xử lý'}
                    </button>
                  )}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">
        {value == null ? '—' : value.toLocaleString('vi-VN')}
      </div>
    </div>
  );
}
