'use client';

import Link from 'next/link';
import { useCallback, useMemo, useRef, useState } from 'react';
import { adminShippingAPI, type EmsShippingImportResult, type EmsShippingImportRow } from '@/lib/admin-api';

const SYNC_LABELS: Record<string, string> = {
  matched: 'Khớp',
  in_progress: 'Đang xử lý',
  mismatch: 'Lệch trạng thái',
  order_not_found: 'Không có đơn shop',
  ems_not_found: 'Không tra được EMS',
  parse_error: 'Lỗi dữ liệu',
};

const SYNC_BADGE: Record<string, string> = {
  matched: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  in_progress: 'bg-blue-100 text-blue-800 border-blue-200',
  mismatch: 'bg-amber-100 text-amber-900 border-amber-200',
  order_not_found: 'bg-red-100 text-red-800 border-red-200',
  ems_not_found: 'bg-orange-100 text-orange-900 border-orange-200',
  parse_error: 'bg-gray-100 text-gray-800 border-gray-200',
};

type FilterKey = 'all' | EmsShippingImportRow['sync_status'];

export default function AdminShippingPage() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EmsShippingImportResult | null>(null);
  const [filter, setFilter] = useState<FilterKey>('all');

  const filteredRows = useMemo(() => {
    if (!result) return [];
    if (filter === 'all') return result.rows;
    return result.rows.filter((row) => row.sync_status === filter);
  }, [result, filter]);

  const runImport = useCallback(async () => {
    if (!file) {
      setError('Chọn file Excel trước.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await adminShippingAPI.importEmsExcel(file);
      setResult(data);
      setFilter('all');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import thất bại');
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, [file]);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">
      <div>
        <p className="text-sm text-gray-500">
          <Link href="/admin/orders" className="text-emerald-700 hover:underline">
            ← Đơn hàng
          </Link>
        </p>
        <h1 className="text-2xl font-bold text-gray-900 mt-2">Quản lý vận chuyển EMS</h1>
        <p className="mt-1 text-sm text-gray-600">
          Import file <strong>gui ems.xlsx</strong>: cột <strong>D (MA_DON_HANG)</strong> tra hành trình EMS,
          cột <strong>J (TEN_NGUOI_NHAN)</strong> tách mã đơn shop (vd. <code>DH093</code>) để đối chiếu.
        </p>
      </div>

      <section className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm space-y-4">
        <h2 className="text-lg font-semibold text-gray-900">1. Upload file Excel</h2>
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx,.xlsm"
            className="block w-full text-sm text-gray-700 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-emerald-50 file:text-emerald-700 hover:file:bg-emerald-100"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setError(null);
            }}
          />
          <button
            type="button"
            onClick={runImport}
            disabled={loading || !file}
            className="inline-flex items-center justify-center rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {loading ? 'Đang tra EMS…' : 'Import & đối chiếu'}
          </button>
        </div>
        {file ? <p className="text-xs text-gray-500">Đã chọn: {file.name}</p> : null}
      </section>

      {error ? (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          {error}{' '}
          <button type="button" onClick={runImport} className="underline font-medium">
            Thử lại
          </button>
        </div>
      ) : null}

      {result?.warnings?.length ? (
        <div className="bg-amber-50 border border-amber-200 text-amber-900 rounded-lg px-4 py-3 text-sm space-y-1">
          {result.warnings.map((w) => (
            <p key={w}>{w}</p>
          ))}
        </div>
      ) : null}

      {result ? (
        <>
          <section className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
            {[
              ['Tổng dòng', result.summary.total_rows, 'all'],
              ['Khớp', result.summary.matched, 'matched'],
              ['Đang xử lý', result.summary.in_progress, 'in_progress'],
              ['Lệch', result.summary.mismatch, 'mismatch'],
              ['Không có đơn', result.summary.order_not_found, 'order_not_found'],
              ['Không tra EMS', result.summary.ems_not_found, 'ems_not_found'],
              ['Lỗi parse', result.summary.parse_error, 'parse_error'],
            ].map(([label, count, key]) => (
              <button
                key={String(key)}
                type="button"
                onClick={() => setFilter(key as FilterKey)}
                className={`rounded-xl border px-3 py-3 text-left transition ${
                  filter === key ? 'border-emerald-500 ring-2 ring-emerald-100' : 'border-gray-200 bg-white'
                }`}
              >
                <div className="text-xs text-gray-500">{label}</div>
                <div className="text-xl font-semibold text-gray-900">{count}</div>
              </button>
            ))}
          </section>

          <section className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
            <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between gap-3">
              <h2 className="text-lg font-semibold text-gray-900">Kết quả đối chiếu</h2>
              <span className="text-sm text-gray-500">{filteredRows.length} dòng</span>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-gray-50 text-gray-600">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">#</th>
                    <th className="px-3 py-2 text-left font-medium">Mã tham chiếu</th>
                    <th className="px-3 py-2 text-left font-medium">Đơn shop</th>
                    <th className="px-3 py-2 text-left font-medium">Mã EMS</th>
                    <th className="px-3 py-2 text-left font-medium">Trạng thái EMS</th>
                    <th className="px-3 py-2 text-left font-medium">Đơn / timeline shop</th>
                    <th className="px-3 py-2 text-left font-medium">Đối chiếu</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {filteredRows.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-4 py-8 text-center text-gray-500">
                        Không có dòng nào trong bộ lọc này.
                      </td>
                    </tr>
                  ) : (
                    filteredRows.map((row) => (
                      <tr key={`${row.row_number}-${row.reference_code}-${row.order_code || 'na'}`} className="align-top">
                        <td className="px-3 py-3 text-gray-500">{row.row_number}</td>
                        <td className="px-3 py-3">
                          <div className="font-medium text-gray-900">{row.reference_code || '—'}</div>
                          <div className="text-xs text-gray-500 mt-1 line-clamp-2">{row.recipient_label}</div>
                        </td>
                        <td className="px-3 py-3">
                          {row.order_code ? (
                            row.order_id ? (
                              <Link href={`/admin/orders?q=${encodeURIComponent(row.order_code)}`} className="text-emerald-700 hover:underline font-medium">
                                {row.order_code}
                              </Link>
                            ) : (
                              <span className="font-medium text-gray-900">{row.order_code}</span>
                            )
                          ) : (
                            '—'
                          )}
                          {row.tracking_number_saved ? (
                            <div className="text-xs text-gray-500 mt-1">Mã lưu: {row.tracking_number_saved}</div>
                          ) : null}
                        </td>
                        <td className="px-3 py-3">{row.ems_tracking_code || '—'}</td>
                        <td className="px-3 py-3">
                          <div className="text-gray-900">{row.ems_status || row.ems_error || '—'}</div>
                          {row.ems_phase ? <div className="text-xs text-gray-500 mt-1">{row.ems_phase}</div> : null}
                        </td>
                        <td className="px-3 py-3">
                          <div>{row.order_status || '—'}</div>
                          {row.current_step_key ? (
                            <div className="text-xs text-gray-500 mt-1">{row.current_step_key}</div>
                          ) : null}
                        </td>
                        <td className="px-3 py-3">
                          <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${SYNC_BADGE[row.sync_status] || SYNC_BADGE.parse_error}`}>
                            {SYNC_LABELS[row.sync_status] || row.sync_status}
                          </span>
                          {row.sync_message ? <p className="text-xs text-gray-600 mt-2 max-w-xs">{row.sync_message}</p> : null}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : (
        <section className="bg-gray-50 border border-dashed border-gray-300 rounded-xl px-4 py-10 text-center text-sm text-gray-500">
          Chưa có kết quả. Upload file Excel EMS để bắt đầu đối chiếu.
        </section>
      )}
    </div>
  );
}
