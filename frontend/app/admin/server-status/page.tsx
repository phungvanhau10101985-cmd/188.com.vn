'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { adminServerStatusAPI, type ServerStatusSnapshot } from '@/lib/admin-api';

const POLL_MS = 20_000;

function formatDt(iso: string | null | undefined): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString('vi-VN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function formatMb(value: number | null | undefined): string {
  if (value == null) return 'không đọc được';
  return `${Math.round(value)}MB`;
}

function formatPct(value: number | null | undefined): string {
  if (value == null) return 'chưa có mẫu';
  return `${Math.round(value)}%`;
}

export default function AdminServerStatusPage() {
  const [data, setData] = useState<ServerStatusSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [visible, setVisible] = useState(true);
  const requestRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return;
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    try {
      const next = await adminServerStatusAPI.get(controller.signal);
      if (controller.signal.aborted) return;
      setData(next);
      setError(null);
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof Error ? err.message : 'Không tải được trạng thái máy');
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    let timer: number | undefined;
    const stop = () => {
      if (timer) window.clearInterval(timer);
      timer = undefined;
      requestRef.current?.abort();
    };
    const start = () => {
      stop();
      if (document.visibilityState !== 'visible') {
        setVisible(false);
        return;
      }
      setVisible(true);
      void load();
      timer = window.setInterval(() => void load(), POLL_MS);
    };
    const onVisibility = () => start();
    document.addEventListener('visibilitychange', onVisibility);
    start();
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      stop();
    };
  }, [load]);

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">Trạng thái máy</h1>
        <p className="mt-1 text-sm text-gray-600">
          Chỉ cập nhật khi trang này đang mở. Đóng trang hoặc chuyển tab thì ngừng hỏi server.
          {data ? ` Lần đo ${formatDt(data.checked_at)}.` : ''}
        </p>
      </div>

      {!visible && (
        <p className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-700">
          Tab đang ẩn. Đã ngừng đo.
        </p>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}{' '}
          <button type="button" onClick={() => void load()} className="font-medium underline">
            Thử lại
          </button>
        </div>
      )}

      {loading && !data && <p className="text-sm text-gray-600">Đang đọc trạng thái…</p>}

      {data && (
        <>
          <section className="rounded-lg border border-gray-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-gray-900">Máy</h2>
            <p className="mt-2 text-sm text-gray-800">
              RAM trống {formatMb(data.host.mem_available_mb)} / {formatMb(data.host.mem_total_mb)}. Đã dùng{' '}
              {formatPct(data.host.ram_used_pct)}. CPU {formatPct(data.host.cpu_used_pct)}. Ngưỡng bản địa hóa{' '}
              {data.host.min_available_mb}MB trống.
            </p>
          </section>

          <section className="rounded-lg border border-gray-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-gray-900">Cảnh báo</h2>
            {data.warnings.length === 0 ? (
              <p className="mt-2 text-sm text-green-800">Máy rảnh. Không có cảnh báo.</p>
            ) : (
              <ul className="mt-2 space-y-2">
                {data.warnings.map((item) => (
                  <li
                    key={item.text}
                    className={
                      item.level === 'error'
                        ? 'rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800'
                        : 'rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900'
                    }
                  >
                    {item.text}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="rounded-lg border border-gray-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-gray-900">Việc nặng</h2>
            <ul className="mt-2 space-y-3">
              {data.jobs.map((job) => (
                <li key={job.key}>
                  <p className="text-sm font-medium text-gray-900">
                    {job.name}
                    <span className={job.running ? 'ml-2 text-blue-700' : 'ml-2 text-gray-500'}>
                      {job.running ? 'đang chạy' : 'không chạy'}
                    </span>
                  </p>
                  <p className="text-sm text-gray-700">{job.detail}</p>
                </li>
              ))}
            </ul>
          </section>

          <section className="rounded-lg border border-gray-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-gray-900">Log gần đây</h2>
            {data.logs.length === 0 ? (
              <p className="mt-2 text-sm text-gray-600">Không có lỗi mới trong 6 giờ.</p>
            ) : (
              <ul className="mt-2 space-y-2">
                {data.logs.map((row) => (
                  <li key={`${row.at}-${row.text}`} className="text-sm text-gray-800">
                    <span className="text-gray-500">{formatDt(row.at)} </span>
                    {row.text}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
