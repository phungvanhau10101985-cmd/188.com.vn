'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  adminProductAPI,
  type AdminSourceStockActivityReport,
  type AdminSourceStockActivityReportSampleRow,
  type AdminSourceStockQueueStats,
  type AdminSourceStockWorkerProgressRow,
  type AdminSourceStockWorkerState,
} from '@/lib/admin-api';

const EMPTY_REPORT_SAMPLE_ROWS: AdminSourceStockActivityReportSampleRow[] = [];

/** Nguồn trong thống kê queue / báo cáo (worker nền kiểm tra nguồn luôn Hibox). */
type SourceStockDomain = 'hibox' | 'cssbuy';

function SpinnerIcon({ className }: { className?: string }) {
  return (
    <svg
      className={`animate-spin h-4 w-4 shrink-0 ${className ?? ''}`}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-hidden
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  );
}

/** Link http(s) mở tab mới — URL trong DB / canonical scrape. */
function ExternalHttpLink({ url }: { url: string }) {
  const u = url.trim();
  if (!u) return '—';
  const isHttp = /^https?:\/\//i.test(u);
  if (!isHttp) {
    return <span className="font-mono text-xs break-all">{u}</span>;
  }
  return (
    <a
      href={u}
      target="_blank"
      rel="noopener noreferrer"
      className="font-mono text-xs text-orange-700 underline break-all"
    >
      {u}
    </a>
  );
}

function formatReportTimestampUtc(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.toLocaleString('vi-VN', { timeZone: 'UTC' })} UTC`;
}

function formatReportAge(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const diffMs = Date.now() - d.getTime();
  if (diffMs < 0) return 'vừa ghi';
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 60) return minutes <= 1 ? 'vừa ghi' : `${minutes} phút trước`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} giờ trước`;
  const days = Math.floor(hours / 24);
  return `${days} ngày trước`;
}

function sleepMs(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

/** Ô «đang scrape / vừa xong / sắp tới» trên snapshot worker. */
function WorkerStockProgressCard({
  title,
  subtitle,
  tone,
  row,
  emptyHint,
  mode,
}: {
  title: string;
  subtitle: string;
  tone: 'sky' | 'emerald' | 'slate';
  row: AdminSourceStockWorkerProgressRow | null | undefined;
  emptyHint: string;
  mode: 'checking' | 'completed' | 'upcoming';
}) {
  const skin =
    tone === 'sky'
      ? 'border-sky-200/90 bg-white/85'
      : tone === 'emerald'
        ? 'border-emerald-200/90 bg-white/85'
        : 'border-slate-200/90 bg-white/85';
  const titleColor =
    tone === 'sky' ? 'text-sky-950' : tone === 'emerald' ? 'text-emerald-950' : 'text-slate-900';

  return (
    <div className={`rounded-lg border px-2.5 py-2 min-w-0 ${skin}`}>
      <p className={`text-[11px] font-semibold uppercase tracking-wide ${titleColor}`}>{title}</p>
      <p className="text-[10px] text-slate-600 leading-snug mt-0.5">{subtitle}</p>
      {!row ? (
        <p className="text-[11px] text-slate-500 mt-2 leading-snug">{emptyHint}</p>
      ) : (
        <div className="mt-2 space-y-1 text-[11px] text-slate-800">
          <p>
            <span className="font-mono tabular-nums">DB #{row.product_db_id}</span>
            {row.product_code ? (
              <>
                {' · '}
                <span className="font-mono">{row.product_code}</span>
              </>
            ) : null}
          </p>
          {row.name ? <p className="line-clamp-2 text-slate-700">{row.name}</p> : null}
          <p className="break-all">
            <span className="text-slate-500">Link: </span>
            <ExternalHttpLink url={row.link_default ?? ''} />
          </p>
          {mode === 'checking' && row.checking_started_at_utc_iso ? (
            <p className="text-slate-600">
              Bắt đầu:{' '}
              <span className="font-mono text-[10px]">{formatReportTimestampUtc(row.checking_started_at_utc_iso)}</span>{' '}
              <span className="text-slate-400">{formatReportAge(row.checking_started_at_utc_iso)}</span>
            </p>
          ) : null}
          {mode === 'completed' ? (
            <>
              {row.source_stock_status ? (
                <p>
                  Trạng thái:{' '}
                  <code className="text-[10px] bg-slate-100 px-1 rounded border border-slate-200">{row.source_stock_status}</code>
                </p>
              ) : null}
              {row.finished_at_utc_iso ? (
                <p className="text-slate-600">
                  Hoàn tất:{' '}
                  <span className="font-mono text-[10px]">{formatReportTimestampUtc(row.finished_at_utc_iso)}</span>{' '}
                  <span className="text-slate-400">{formatReportAge(row.finished_at_utc_iso)}</span>
                </p>
              ) : null}
            </>
          ) : null}
          {mode === 'upcoming' && row.queue_hint_vi ? (
            <p className="text-[10px] text-indigo-950/90 bg-indigo-50/80 border border-indigo-100 rounded px-1.5 py-1">
              {row.queue_hint_vi}
            </p>
          ) : null}
        </div>
      )}
    </div>
  );
}

function MiniStat({
  label,
  value,
  variant = 'slate',
}: {
  label: string;
  value: number | string;
  variant?: 'slate' | 'emerald' | 'violet' | 'amber' | 'rose' | 'teal';
}) {
  const skin: Record<string, string> = {
    slate: 'border-slate-200 bg-slate-50/90 text-slate-900',
    emerald: 'border-emerald-200 bg-emerald-50/90 text-emerald-950',
    violet: 'border-violet-200 bg-violet-50/90 text-violet-950',
    amber: 'border-amber-200 bg-amber-50/90 text-amber-950',
    rose: 'border-rose-200 bg-rose-50/90 text-rose-950',
    teal: 'border-teal-200 bg-teal-50/90 text-teal-950',
  };
  const v = skin[variant] ?? skin.slate;
  const display = typeof value === 'number' ? value.toLocaleString('vi-VN') : value;
  return (
    <div className={`rounded-lg border px-2.5 py-2 text-center min-w-0 ${v}`}>
      <div className="text-[10px] uppercase tracking-wide opacity-80 font-medium leading-tight line-clamp-2">
        {label}
      </div>
      <div className="text-base sm:text-lg font-semibold tabular-nums mt-0.5">{display}</div>
    </div>
  );
}

/** Nút trong bảng mẫu «cờ hết nguồn»: xóa DB / gỡ cờ / kiểm tra worker PDP lại. */
type ReportSampleOosRowActions = {
  busyByDbId: Record<number, string>;
  disabledGlobally: boolean;
  onDeleteDb: (row: AdminSourceStockActivityReportSampleRow) => void;
  onClearFlag: (row: AdminSourceStockActivityReportSampleRow) => void;
  onRecheck: (row: AdminSourceStockActivityReportSampleRow) => void;
};

/** Chọn nhiều dòng trong bảng mẫu OOS — thao tác hàng loạt và «tất cả mẫu». */
type ReportSampleOosBulkSelection = {
  selectedDbIds: readonly number[];
  displayedCount: number;
  selectedCount: number;
  bulkBarBusy: boolean;
  onToggleDbId: (dbId: number, nextSelected: boolean) => void;
  onSelectAllDisplayed: () => void;
  onClearSelection: () => void;
  onBulkDeleteSelected: () => void;
  onBulkClearFlagSelected: () => void;
  onBulkRecheckSelected: () => void;
  onBulkDeleteAllDisplayed: () => void;
  onBulkClearFlagAllDisplayed: () => void;
  onBulkRecheckAllDisplayed: () => void;
};

/** Bảng mẫu (tối đa `detail_limit` từ API) trong báo cáo 30 ngày. */
function SourceStockReportSampleTable({
  title,
  rows,
  emptyHint,
  defaultOpen,
  oosActions,
  oosBulkSelection,
}: {
  title: string;
  rows: AdminSourceStockActivityReportSampleRow[];
  emptyHint: string;
  defaultOpen: boolean;
  oosActions?: ReportSampleOosRowActions;
  oosBulkSelection?: ReportSampleOosBulkSelection;
}) {
  const colSpan = 9 + (oosActions ? 1 : 0) + (oosBulkSelection ? 1 : 0);
  const headerCheckboxRef = useRef<HTMLInputElement>(null);

  const selectedSet = useMemo(
    () => new Set(oosBulkSelection?.selectedDbIds ?? []),
    [oosBulkSelection?.selectedDbIds],
  );

  const allDisplayedSelected = rows.length > 0 && rows.every((r) => selectedSet.has(r.id));
  const someDisplayedSelected = rows.some((r) => selectedSet.has(r.id));

  useEffect(() => {
    const el = headerCheckboxRef.current;
    if (!el || !oosBulkSelection) return;
    el.indeterminate = someDisplayedSelected && !allDisplayedSelected;
  }, [oosBulkSelection, someDisplayedSelected, allDisplayedSelected]);

  return (
    <details
      className="rounded-lg border border-slate-200 bg-white mt-2"
      open={defaultOpen}
    >
      <summary className="cursor-pointer select-none px-3 py-2 text-sm font-semibold text-slate-800 bg-slate-50/90 list-none [&::-webkit-details-marker]:hidden flex flex-wrap justify-between gap-2">
        <span>
          {title}{' '}
          <span className="font-normal text-slate-500">({rows.length} dòng)</span>
        </span>
        <span className="text-[11px] font-normal text-indigo-700 underline">Mở / thu</span>
      </summary>
      {oosBulkSelection && rows.length > 0 ? (
        <div className="border-t border-slate-200 bg-slate-50/80 px-2.5 py-2 flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-slate-800">
            {oosBulkSelection.bulkBarBusy ? <SpinnerIcon className="text-slate-700" /> : null}
            <span>
              Đã chọn <strong className="tabular-nums">{oosBulkSelection.selectedCount}</strong>{' '}
              /{' '}
              <strong className="tabular-nums">{oosBulkSelection.displayedCount}</strong> trong bảng
            </span>
            <span className="hidden sm:inline text-slate-400" aria-hidden>
              ·
            </span>
            <button
              type="button"
              disabled={oosBulkSelection.bulkBarBusy}
              className="text-[11px] font-medium text-indigo-800 underline disabled:opacity-45 disabled:no-underline"
              onClick={() => oosBulkSelection.onSelectAllDisplayed()}
            >
              Chọn hết
            </button>
            <button
              type="button"
              disabled={oosBulkSelection.bulkBarBusy || !oosBulkSelection.selectedCount}
              className="text-[11px] font-medium text-slate-700 underline disabled:opacity-45 disabled:no-underline"
              onClick={() => oosBulkSelection.onClearSelection()}
            >
              Bỏ chọn
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
            <span className="font-semibold text-slate-600 mr-0.5">Theo ô đánh dấu:</span>
            <button
              type="button"
              disabled={oosBulkSelection.bulkBarBusy || !oosBulkSelection.selectedCount}
              className="rounded-md border border-red-200 bg-white px-2 py-1 font-semibold text-red-950 hover:bg-red-50 disabled:opacity-45"
              onClick={() => oosBulkSelection.onBulkDeleteSelected()}
            >
              Xóa DB
            </button>
            <button
              type="button"
              disabled={oosBulkSelection.bulkBarBusy || !oosBulkSelection.selectedCount}
              className="rounded-md border border-slate-300 bg-white px-2 py-1 font-semibold text-slate-900 hover:bg-slate-50 disabled:opacity-45"
              onClick={() => oosBulkSelection.onBulkClearFlagSelected()}
            >
              Gỡ cờ
            </button>
            <button
              type="button"
              disabled={oosBulkSelection.bulkBarBusy || !oosBulkSelection.selectedCount}
              className="rounded-md border border-emerald-300 bg-emerald-50 px-2 py-1 font-semibold text-emerald-950 hover:bg-emerald-100 disabled:opacity-45"
              onClick={() => oosBulkSelection.onBulkRecheckSelected()}
            >
              PDP lại
            </button>
            <span className="mx-1 h-4 w-px bg-slate-300 shrink-0" aria-hidden />
            <span className="font-semibold text-slate-600 mr-0.5">Toàn bộ mẫu:</span>
            <button
              type="button"
              disabled={oosBulkSelection.bulkBarBusy}
              className="rounded-md border border-red-400 bg-red-50 px-2 py-1 font-semibold text-red-950 hover:bg-red-100 disabled:opacity-45"
              onClick={() => oosBulkSelection.onBulkDeleteAllDisplayed()}
            >
              Xóa DB (tất cả)
            </button>
            <button
              type="button"
              disabled={oosBulkSelection.bulkBarBusy}
              className="rounded-md border border-slate-300 bg-white px-2 py-1 font-semibold text-slate-900 hover:bg-slate-50 disabled:opacity-45"
              onClick={() => oosBulkSelection.onBulkClearFlagAllDisplayed()}
            >
              Gỡ cờ (tất cả)
            </button>
            <button
              type="button"
              disabled={oosBulkSelection.bulkBarBusy}
              className="rounded-md border border-emerald-400 bg-emerald-50 px-2 py-1 font-semibold text-emerald-950 hover:bg-emerald-100 disabled:opacity-45"
              onClick={() => oosBulkSelection.onBulkRecheckAllDisplayed()}
            >
              PDP lại (tất cả)
            </button>
          </div>
        </div>
      ) : null}
      <div className="overflow-x-auto border-t border-slate-100">
        <table className="min-w-full text-xs">
          <thead className="bg-gray-100 text-gray-700">
            <tr>
              {oosBulkSelection ? (
                <th scope="col" className="w-9 px-1 py-1.5 align-middle">
                  <span className="sr-only">Chọn dòng</span>
                  <input
                    ref={headerCheckboxRef}
                    type="checkbox"
                    checked={allDisplayedSelected}
                    disabled={oosBulkSelection.bulkBarBusy}
                    onChange={() => {
                      if (allDisplayedSelected) {
                        oosBulkSelection.onClearSelection();
                      } else {
                        oosBulkSelection.onSelectAllDisplayed();
                      }
                    }}
                    className="h-4 w-4 accent-indigo-700 disabled:opacity-45"
                    title="Chọn hoặc bỏ chọn toàn bộ dòng hiển thị"
                    aria-label="Chọn hoặc bỏ chọn toàn bộ dòng hiển thị trong bảng mẫu"
                  />
                </th>
              ) : null}
              <th scope="col" className="text-left px-2 py-1.5 font-medium whitespace-nowrap">
                DB id
              </th>
              <th scope="col" className="text-left px-2 py-1.5 font-medium whitespace-nowrap">
                Mã SP
              </th>
              <th scope="col" className="text-left px-2 py-1.5 font-medium min-w-[10rem]">
                Tên
              </th>
              <th scope="col" className="text-left px-2 py-1.5 font-medium whitespace-nowrap">
                Tồn
              </th>
              <th scope="col" className="text-left px-2 py-1.5 font-medium whitespace-nowrap">
                source_stock_status
              </th>
              <th scope="col" className="text-left px-2 py-1.5 font-medium whitespace-nowrap">
                Kiểm tra nguồn
              </th>
              <th scope="col" className="text-left px-2 py-1.5 font-medium whitespace-nowrap">
                Batch TTL
              </th>
              <th scope="col" className="text-left px-2 py-1.5 font-medium min-w-[12rem]">
                Link DB
              </th>
              <th scope="col" className="text-left px-2 py-1.5 font-medium whitespace-nowrap">
                PDP
              </th>
              {oosActions ? (
                <th scope="col" className="text-left px-2 py-1.5 font-medium whitespace-nowrap min-w-[7.5rem]">
                  Thao tác
                </th>
              ) : null}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={colSpan} className="px-2 py-4 text-gray-500 text-center">
                  {emptyHint}
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={`${title}-${row.id}`} className="border-t border-gray-200 align-top">
                  {oosBulkSelection ? (
                    <td className="px-1 py-1.5 align-middle text-center">
                      <input
                        type="checkbox"
                        checked={selectedSet.has(row.id)}
                        disabled={oosBulkSelection.bulkBarBusy}
                        onChange={(ev) =>
                          oosBulkSelection.onToggleDbId(row.id, ev.target.checked)
                        }
                        className="h-4 w-4 accent-indigo-700 disabled:opacity-45"
                        aria-label={`Chọn SP database id ${row.id}`}
                      />
                    </td>
                  ) : null}
                  <td className="px-2 py-1.5 whitespace-nowrap font-mono">{row.id}</td>
                  <td className="px-2 py-1.5 whitespace-nowrap font-mono text-[11px]">{row.product_id}</td>
                  <td className="px-2 py-1.5 max-w-[14rem]">{row.name}</td>
                  <td className="px-2 py-1.5 whitespace-nowrap">{row.available}</td>
                  <td className="px-2 py-1.5 whitespace-nowrap">{row.source_stock_status ?? '—'}</td>
                  <td className="px-2 py-1.5 whitespace-nowrap text-[11px]">
                    <span className="block">{formatReportTimestampUtc(row.source_stock_checked_at)}</span>
                    {formatReportAge(row.source_stock_checked_at) ? (
                      <span className="block text-[10px] text-slate-500">
                        {formatReportAge(row.source_stock_checked_at)}
                      </span>
                    ) : null}
                  </td>
                  <td className="px-2 py-1.5 whitespace-nowrap text-[11px]">
                    <span className="block">{formatReportTimestampUtc(row.admin_source_batch_scanned_at)}</span>
                    {formatReportAge(row.admin_source_batch_scanned_at) ? (
                      <span className="block text-[10px] text-slate-500">
                        {formatReportAge(row.admin_source_batch_scanned_at)}
                      </span>
                    ) : null}
                  </td>
                  <td className="px-2 py-1.5">
                    <ExternalHttpLink url={row.link_default} />
                  </td>
                  <td className="px-2 py-1.5 whitespace-nowrap">
                    {row.slug ? (
                      <Link
                        href={`/products/${encodeURIComponent(row.slug)}`}
                        className="text-indigo-700 underline"
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        Xem
                      </Link>
                    ) : (
                      '—'
                    )}
                  </td>
                  {oosActions ? (
                    <td className="px-2 py-1.5 align-top min-w-[7.75rem]">
                      {(() => {
                        const busy = oosActions.busyByDbId[row.id];
                        const blocked = oosActions.disabledGlobally || Boolean(busy);
                        return (
                          <div className="flex flex-col gap-1.5">
                            <button
                              type="button"
                              className="text-[10px] font-semibold rounded border border-red-300 bg-red-50 px-2 py-1 text-red-950 hover:bg-red-100 disabled:opacity-45 text-left leading-tight"
                              disabled={blocked}
                              aria-label={`Xóa vĩnh viễn sản khỏi cửa hàng, DB id ${row.id}`}
                              onClick={() => oosActions.onDeleteDb(row)}
                            >
                              Xóa khỏi DB…
                              <span className="font-normal block text-[9px] text-red-950/85">Đúng là hết, gỡ SP shop</span>
                            </button>
                            <button
                              type="button"
                              className="text-[10px] font-semibold rounded border border-slate-300 bg-white px-2 py-1 text-slate-900 hover:bg-slate-50 disabled:opacity-45 text-left leading-tight"
                              disabled={blocked}
                              aria-label={`Gỡ cờ out_of_stock sai, DB id ${row.id}`}
                              onClick={() => oosActions.onClearFlag(row)}
                            >
                              Gỡ cờ hết…
                              <span className="font-normal block text-[9px] text-slate-600">Đọc sai — giữ SP, mở tồn lại</span>
                            </button>
                            <button
                              type="button"
                              className="text-[10px] font-semibold rounded border border-emerald-400 bg-emerald-50 px-2 py-1 text-emerald-950 hover:bg-emerald-100 disabled:opacity-45 text-left leading-tight"
                              disabled={blocked}
                              aria-label={`Xếp worker kiểm tra lại PDP, DB id ${row.id}`}
                              onClick={() => oosActions.onRecheck(row)}
                            >
                              Kiểm tra lại PDP
                              <span className="font-normal block text-[9px] text-emerald-900">Hết vẫn cờ • còn thì báo</span>
                            </button>
                            {busy ? (
                              <span className="text-[10px] text-slate-500 leading-snug">{busy}</span>
                            ) : null}
                          </div>
                        );
                      })()}
                    </td>
                  ) : null}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </details>
  );
}

export default function AdminSourceStockCheckPage() {
  const [lastError, setLastError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: 'ok' | 'info' | 'err'; msg: string } | null>(null);
  const [domain, setDomain] = useState<SourceStockDomain>('hibox');

  /** Số ngày chờ để một SP được xếp hàng kiểm tra lại (theo backend, mặc định 30). */
  const [cooldownDays, setCooldownDays] = useState(30);
  const [queueStats, setQueueStats] = useState<AdminSourceStockQueueStats | null>(null);
  const [queueStatsLoading, setQueueStatsLoading] = useState(false);
  /** Snapshot daemon + cờ pause DB (`source_stock_worker_state`); queue RAM chỉ của process báo KPI. */
  const [workerState, setWorkerState] = useState<AdminSourceStockWorkerState | null>(null);
  const [pauseActionBusy, setPauseActionBusy] = useState(false);
  const [activityReport, setActivityReport] = useState<AdminSourceStockActivityReport | null>(null);
  const [activityReportLoading, setActivityReportLoading] = useState(false);
  const [activityReportError, setActivityReportError] = useState<string | null>(null);
  /** Hàng đang chờ thao tác trên báo cáo OOS — khóa trùng nút trong bảng. */
  const [reportOosRowBusyById, setReportOosRowBusyById] = useState<Record<number, string>>({});
  /** `products.id` đang chờ xác nhận xóa (một hoặc nhiều) trong modal báo cáo OOS. */
  const [reportOosDeleteConfirmIds, setReportOosDeleteConfirmIds] = useState<number[] | null>(
    null,
  );
  const [reportOosDeleting, setReportOosDeleting] = useState(false);
  const [reportOosSampleSelectedIds, setReportOosSampleSelectedIds] = useState<number[]>([]);
  const [reportOosBulkBusy, setReportOosBulkBusy] = useState(false);
  const recheckPollCancelRef = useRef(false);

  const reportOosSampleRows = activityReport?.samples?.oos ?? EMPTY_REPORT_SAMPLE_ROWS;
  const reportOosRowById = useMemo(() => {
    const m = new Map<number, AdminSourceStockActivityReportSampleRow>();
    for (const r of reportOosSampleRows) {
      m.set(r.id, r);
    }
    return m;
  }, [reportOosSampleRows]);

  useEffect(() => {
    const valid = new Set(reportOosSampleRows.map((r) => r.id));
    setReportOosSampleSelectedIds((prev) => prev.filter((id) => valid.has(id)));
  }, [reportOosSampleRows]);

  useEffect(() => {
    recheckPollCancelRef.current = false;
    return () => {
      recheckPollCancelRef.current = true;
    };
  }, []);

  const showToast = useCallback((type: 'ok' | 'info' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 5200);
  }, []);

  const refreshQueueStats = useCallback(async () => {
    setQueueStatsLoading(true);
    try {
      const s = await adminProductAPI.fetchSourceStockQueueStats({
        domain,
        activeOnly: true,
      });
      setQueueStats(s);
      if (typeof s.admin_batch_scan_cooldown_days === 'number') {
        setCooldownDays(s.admin_batch_scan_cooldown_days);
      }
    } catch {
      setQueueStats(null);
    } finally {
      setQueueStatsLoading(false);
    }
    try {
      const w = await adminProductAPI.fetchSourceStockWorkerState();
      setWorkerState(w);
    } catch {
      /* giữ snapshot cũ — API worker-state lỗi không làm trống queue-stats */
    }
  }, [domain]);

  const toggleWorkerPauseFromDb = useCallback(
    async (nextPaused: boolean) => {
      setPauseActionBusy(true);
      try {
        const w = await adminProductAPI.setSourceStockWorkerPaused(nextPaused);
        setWorkerState(w);
        showToast(
          'ok',
          nextPaused
            ? 'Đã tạm dừng kiểm tra nguồn (ghi DB). Worker không pop/claim cho đến khi «Chạy tiếp».'
            : 'Đã bỏ tạm dừng — worker scrape lại khi có SP trong queue hoặc đến hạn.',
        );
      } catch (e) {
        showToast('err', e instanceof Error ? e.message : String(e));
      } finally {
        setPauseActionBusy(false);
      }
    },
    [showToast],
  );

  const refreshActivityReport = useCallback(async () => {
    setActivityReportLoading(true);
    setActivityReportError(null);
    try {
      const r = await adminProductAPI.fetchSourceStockActivityReport({
        domain,
        activeOnly: true,
        windowDays: 30,
        detailLimit: 120,
      });
      setActivityReport(r);
    } catch (e) {
      setActivityReport(null);
      setActivityReportError(e instanceof Error ? e.message : String(e));
    } finally {
      setActivityReportLoading(false);
    }
  }, [domain]);

  const bumpReportBusy = useCallback((id: number, label: string) => {
    setReportOosRowBusyById((m) => ({ ...m, [id]: label }));
  }, []);

  const clearReportBusy = useCallback((id: number) => {
    setReportOosRowBusyById((m) => {
      const next = { ...m };
      delete next[id];
      return next;
    });
  }, []);

  const pollWorkerRecheckOutcome = useCallback(
    async (productDbId: number) => {
      const stepMs = 2800;
      const maxAttempts = 32;
      for (let attempt = 0; attempt < maxAttempts; attempt++) {
        if (recheckPollCancelRef.current) return;
        await sleepMs(stepMs);
        if (recheckPollCancelRef.current) return;
        try {
          const p = await adminProductAPI.getProductByDatabaseId(productDbId);
          const st = (p.source_stock_status ?? '').trim().toLowerCase();
          if (st === 'queued' || st === 'checking') continue;
          if (st === 'in_stock') {
            showToast('ok', `SP DB #${productDbId}: đã kiểm tra — nguồn còn hàng (in_stock).`);
            void refreshActivityReport();
            void refreshQueueStats();
            return;
          }
          if (st === 'out_of_stock') {
            showToast('info', `SP DB #${productDbId}: đã kiểm tra — vẫn hết trên nguồn.`);
            void refreshActivityReport();
            void refreshQueueStats();
            return;
          }
          const err = typeof p.source_stock_error === 'string' ? p.source_stock_error.trim() : '';
          const slice = err.length > 160 ? `${err.slice(0, 160)}…` : err;
          showToast(
            'info',
            `SP DB #${productDbId}: kết quả «${st || 'không rõ'}».${slice ? ` ${slice}` : ''}`,
          );
          void refreshActivityReport();
          void refreshQueueStats();
          return;
        } catch (e) {
          const msg = e instanceof Error ? e.message : String(e);
          showToast('err', `Không đọc được SP DB #${productDbId} khi chờ worker — ${msg}`);
          return;
        }
      }
      showToast(
        'info',
        `SP DB #${productDbId}: chưa có kết quả sau ~${Math.round(
          (maxAttempts * stepMs) / 1000,
        )}s — đợi thêm và bấm «Làm mới báo cáo».`,
      );
    },
    [refreshActivityReport, refreshQueueStats, showToast],
  );

  const handleReportOosClearFlag = useCallback(
    async (row: AdminSourceStockActivityReportSampleRow) => {
      bumpReportBusy(row.id, 'Đang gỡ cờ…');
      try {
        await adminProductAPI.clearSourceStockOosFlagByDbId(row.id);
        showToast(
          'ok',
          `Đã gỡ cờ và mở tồn mặc định khi đang 0 — DB #${row.id}. TTL batch admin không đổi.`,
        );
        void refreshActivityReport();
        void refreshQueueStats();
      } catch (e) {
        showToast('err', e instanceof Error ? e.message : String(e));
      } finally {
        clearReportBusy(row.id);
      }
    },
    [bumpReportBusy, clearReportBusy, refreshActivityReport, refreshQueueStats, showToast],
  );

  const handleReportOosRecheck = useCallback(
    async (row: AdminSourceStockActivityReportSampleRow) => {
      bumpReportBusy(row.id, 'Đang xếp hàng PDP…');
      try {
        const out = await adminProductAPI.forceWorkerSourceStockRecheckByDbId(row.id);
        if (out.skip_reason === 'not_eligible_or_failed' && !out.enqueued_now) {
          showToast(
            'err',
            `Không xếp kiểm tra PDP cho DB #${row.id}: link không đủ điều kiện hoặc tắt worker.`,
          );
          return;
        }
        bumpReportBusy(row.id, 'Worker đọc…');
        if (!out.enqueued_now && out.skip_reason === 'already_pending') {
          showToast('info', `SP DB #${row.id} đã trong hàng chờ worker — đang chờ kết quả.`);
        } else {
          showToast('ok', `Đã xếp worker PDP kiểm tra DB #${row.id}.`);
        }
        await pollWorkerRecheckOutcome(row.id);
      } catch (e) {
        showToast('err', e instanceof Error ? e.message : String(e));
      } finally {
        clearReportBusy(row.id);
      }
    },
    [bumpReportBusy, clearReportBusy, pollWorkerRecheckOutcome, showToast],
  );

  const toggleReportOosSampleSelect = useCallback((dbId: number, nextSelected: boolean) => {
    setReportOosSampleSelectedIds((prev) => {
      const s = new Set(prev);
      if (nextSelected) s.add(dbId);
      else s.delete(dbId);
      return [...s].sort((a, b) => a - b);
    });
  }, []);

  const selectAllReportOosDisplayed = useCallback(() => {
    const rows = activityReport?.samples?.oos ?? EMPTY_REPORT_SAMPLE_ROWS;
    setReportOosSampleSelectedIds([...rows.map((r) => r.id)].sort((a, b) => a - b));
  }, [activityReport?.samples?.oos]);

  const clearReportOosSampleSelection = useCallback(() => {
    setReportOosSampleSelectedIds([]);
  }, []);

  const requestReportOosDeleteDbIds = useCallback(
    (rawIds: number[]) => {
      const uniq = [...new Set(rawIds.filter((id) => id > 0))].sort((a, b) => a - b);
      if (!uniq.length) {
        showToast('err', 'Chưa có SP nào được chọn trong bảng mẫu.');
        return;
      }
      const cap =
        typeof activityReport?.detail_limit_applied === 'number'
          ? activityReport.detail_limit_applied
          : 120;
      if (uniq.length > cap) {
        showToast('err', `Chỉ xử lý tối đa ${cap} SP mỗi lần (giới hạn bảng mẫu).`);
        return;
      }
      setReportOosDeleteConfirmIds(uniq);
    },
    [activityReport?.detail_limit_applied, showToast],
  );

  const runBulkReportOosClearFlags = useCallback(
    async (dbIds: number[]) => {
      const ids = [...new Set(dbIds)].filter((id) => id > 0);
      if (!ids.length) {
        showToast('err', 'Không có SP trong bảng mẫu để gỡ cờ.');
        return;
      }
      setReportOosBulkBusy(true);
      try {
        let ok = 0;
        let failed = 0;
        for (const id of ids) {
          bumpReportBusy(id, 'Hàng loạt · gỡ cờ…');
          try {
            await adminProductAPI.clearSourceStockOosFlagByDbId(id);
            ok++;
          } catch {
            failed++;
          } finally {
            clearReportBusy(id);
          }
          await sleepMs(140);
        }
        showToast(
          failed ? 'info' : 'ok',
          `Gỡ cờ hàng loạt: thành công ${ok}, lỗi ${failed}. Làm mới báo cáo nếu danh sách chưa đổi.`,
        );
        setReportOosSampleSelectedIds((prev) => prev.filter((tid) => !ids.includes(tid)));
        void refreshActivityReport();
        void refreshQueueStats();
      } finally {
        setReportOosBulkBusy(false);
      }
    },
    [bumpReportBusy, clearReportBusy, refreshActivityReport, refreshQueueStats, showToast],
  );

  const runBulkReportOosEnqueueRecheckNoPoll = useCallback(
    async (dbIds: number[]) => {
      const ids = [...new Set(dbIds)].filter((id) => id > 0);
      if (!ids.length) {
        showToast('err', 'Không có SP trong bảng mẫu để xếp PDP.');
        return;
      }
      setReportOosBulkBusy(true);
      try {
        let queuedOk = 0;
        let alreadyPending = 0;
        let ineligible = 0;
        let callErr = 0;
        for (const id of ids) {
          bumpReportBusy(id, 'Đang xếp hàng PDP…');
          try {
            const out = await adminProductAPI.forceWorkerSourceStockRecheckByDbId(id);
            if (out.skip_reason === 'not_eligible_or_failed' && !out.enqueued_now) {
              ineligible++;
            } else if (!out.enqueued_now && out.skip_reason === 'already_pending') {
              bumpReportBusy(id, 'Đang chờ worker…');
              alreadyPending++;
            } else {
              bumpReportBusy(id, 'Worker đọc…');
              queuedOk++;
            }
          } catch {
            callErr++;
          } finally {
            clearReportBusy(id);
          }
          await sleepMs(160);
        }
        showToast(
          callErr ? 'info' : 'ok',
          `Xếp kiểm tra PDP (hàng loạt): enqueue ${queuedOk}, đã chờ sẵn ${alreadyPending}, không đủ điều kiện ${ineligible}, lỗi gọi ${callErr}. Mở từng dòng «Kiểm tra lại PDP» nếu cần chờ kết quả chi tiết.`,
        );
        void refreshActivityReport();
        void refreshQueueStats();
      } finally {
        setReportOosBulkBusy(false);
      }
    },
    [bumpReportBusy, clearReportBusy, refreshActivityReport, refreshQueueStats, showToast],
  );

  const executeReportOosDeleteFromDb = useCallback(async () => {
    const ids = reportOosDeleteConfirmIds;
    if (!ids?.length) return;
    setReportOosDeleting(true);
    try {
      const res = await adminProductAPI.deleteSourceStockBatchProductsByDbIds(ids);
      let msg = `Đã xóa ${res.deleted_count ?? 0} sản (${(res.deleted_db_ids ?? []).length} khớp).`;
      if ((res.not_found_db_ids ?? []).length) {
        msg += ` Không thấy id: ${res.not_found_db_ids!.join(', ')}.`;
      }
      showToast(res.deleted_count ? 'ok' : 'info', msg);
      setReportOosDeleteConfirmIds(null);
      const removed = new Set(res.deleted_db_ids ?? []);
      setReportOosSampleSelectedIds((prev) => prev.filter((tid) => !removed.has(tid)));
      void refreshActivityReport();
      void refreshQueueStats();
    } catch (e) {
      showToast('err', e instanceof Error ? e.message : String(e));
    } finally {
      setReportOosDeleting(false);
    }
  }, [refreshActivityReport, refreshQueueStats, reportOosDeleteConfirmIds, showToast]);

  const reportOosBulkSelection = useMemo<ReportSampleOosBulkSelection | undefined>(() => {
    if (!reportOosSampleRows.length) return undefined;
    return {
      selectedDbIds: reportOosSampleSelectedIds,
      displayedCount: reportOosSampleRows.length,
      selectedCount: reportOosSampleSelectedIds.length,
      bulkBarBusy: reportOosBulkBusy || reportOosDeleting,
      onToggleDbId: toggleReportOosSampleSelect,
      onSelectAllDisplayed: selectAllReportOosDisplayed,
      onClearSelection: clearReportOosSampleSelection,
      onBulkDeleteSelected: () => requestReportOosDeleteDbIds([...reportOosSampleSelectedIds]),
      onBulkClearFlagSelected: () => void runBulkReportOosClearFlags([...reportOosSampleSelectedIds]),
      onBulkRecheckSelected: () => void runBulkReportOosEnqueueRecheckNoPoll([...reportOosSampleSelectedIds]),
      onBulkDeleteAllDisplayed: () =>
        requestReportOosDeleteDbIds(reportOosSampleRows.map((r) => r.id)),
      onBulkClearFlagAllDisplayed: () =>
        void runBulkReportOosClearFlags(reportOosSampleRows.map((r) => r.id)),
      onBulkRecheckAllDisplayed: () =>
        void runBulkReportOosEnqueueRecheckNoPoll(reportOosSampleRows.map((r) => r.id)),
    };
  }, [
    clearReportOosSampleSelection,
    reportOosBulkBusy,
    reportOosDeleting,
    reportOosSampleRows,
    reportOosSampleSelectedIds,
    requestReportOosDeleteDbIds,
    runBulkReportOosClearFlags,
    runBulkReportOosEnqueueRecheckNoPoll,
    selectAllReportOosDisplayed,
    toggleReportOosSampleSelect,
  ]);

  const reportOosActionsForTable = useMemo<ReportSampleOosRowActions>(
    () => ({
      busyByDbId: reportOosRowBusyById,
      disabledGlobally:
        activityReportLoading || reportOosDeleting || reportOosBulkBusy,
      onDeleteDb: (row) => requestReportOosDeleteDbIds([row.id]),
      onClearFlag: handleReportOosClearFlag,
      onRecheck: handleReportOosRecheck,
    }),
    [
      activityReportLoading,
      handleReportOosClearFlag,
      handleReportOosRecheck,
      reportOosBulkBusy,
      reportOosDeleting,
      reportOosRowBusyById,
      requestReportOosDeleteDbIds,
    ],
  );

  useEffect(() => {
    void refreshQueueStats();
  }, [refreshQueueStats]);

  useEffect(() => {
    void refreshActivityReport();
  }, [refreshActivityReport]);

  useEffect(() => {
    const id = window.setInterval(() => void refreshQueueStats(), 90_000);
    return () => window.clearInterval(id);
  }, [refreshQueueStats]);

  useEffect(() => {
    if (reportOosDeleteConfirmIds == null) return;
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key !== 'Escape') return;
      if (!reportOosDeleting) setReportOosDeleteConfirmIds(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [reportOosDeleteConfirmIds, reportOosDeleting]);

  return (
    <div className="max-w-[88rem] mx-auto px-3 sm:px-5 py-5 pb-8">
      <header className="mb-5">
        <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
          <div className="min-w-0">
            <h1 className="text-xl sm:text-2xl font-bold text-gray-900 tracking-tight">Kiểm tra nguồn hàng</h1>
            <p className="text-xs sm:text-sm text-gray-600 mt-1 max-w-3xl">
              <strong>Kiểm tra hết/còn hàng trên nguồn (1688/Hibox) chạy trên máy chủ:</strong> thread daemon trong process FastAPI, xếp
              từng SP và ghi vào DB. Env chính:{' '}
              <code className="text-[11px] bg-gray-100 px-1 rounded">SOURCE_STOCK_CHECK_ENABLED</code> (mặc định <strong>bật</strong>; đặt
              false và khởi động lại backend để tắt), cùng <code className="text-[11px] bg-gray-100 px-1 rounded">SOURCE_STOCK_CHECK_*</code>{' '}
              (interval, stale…). Worker luôn qua scrape Hibox. Tab này chỉ xem tiến độ queue và báo cáo — không scrape từ trình duyệt.
            </p>
          </div>
        </div>
        <details className="group rounded-lg border border-gray-200 bg-gray-50/90 text-sm text-gray-700">
          <summary className="cursor-pointer list-none [&::-webkit-details-marker]:hidden flex items-center gap-2 px-3 py-2.5 font-medium text-gray-900 select-none hover:bg-gray-100/80 rounded-lg transition-colors">
            <span aria-hidden className="text-gray-400 text-[10px] group-open:hidden">
              ▸
            </span>
            <span aria-hidden className="text-gray-400 text-[10px] hidden group-open:inline">
              ▾
            </span>
            Đọc thêm — TTL batch, PDP traffic, chặn / captcha, Hibox &amp; CSSBuy
          </summary>
          <div className="px-3 pb-3 pt-0 space-y-3 text-[13px] leading-relaxed text-gray-700 border-t border-gray-200">
            <p>
              Worker máy chủ (khi <code className="text-[11px] bg-white px-1 rounded border border-gray-200">SOURCE_STOCK_CHECK_ENABLED</code>{' '}
              bật — mặc định vậy) luôn xử lý qua <strong>scrape Hibox</strong> (không có chọn CSSBuy trên luồng nền), một SP mỗi vòng,
              nghỉ theo{' '}
              <code className="text-[11px] bg-white px-1 rounded border border-gray-200">SOURCE_STOCK_CHECK_INTERVAL_SECONDS</code>. Không
              cần mở tab admin để duy trì luồng. Khi phản hồi báo chặn / rủi ro (
              <code className="text-[11px] bg-white px-1 rounded border border-gray-200">blocked</code>
              hoặc dấu hiệu captcha trên UI), hãy xử lý nguồn hoặc hạ tần suất trên server.{' '}
              <code className="text-[11px] bg-white px-1 rounded border border-gray-200">error</code> /{' '}
              <code className="text-[11px] bg-white px-1 rounded border border-gray-200">fetch_error</code>:{' '}
              <strong>không đánh dấu TTL batch</strong> và <strong>giữ đúng SP đó</strong> để thử lại.
            </p>
            <p>
              PDP traffic lấy từ{' '}
              <code className="text-[11px] bg-white px-1 rounded border border-gray-200">user_product_views</code> và{' '}
              <code className="text-[11px] bg-white px-1 rounded border border-gray-200">guest_product_views</code> trong cửa sổ{' '}
              <code className="text-[11px] bg-white px-1 rounded border border-gray-200">
                ADMIN_SOURCE_BATCH_TRAFFIC_VIEW_WINDOW_DAYS
              </code>
              ; SP traffic được ưu tiên. Nếu đã có{' '}
              <code className="text-[11px] bg-white px-1 rounded border border-gray-200">admin_source_batch_scanned_at</code> nhưng
              chưa qua{' '}
              <code className="text-[11px] bg-white px-1 rounded border border-gray-200">
                ADMIN_SOURCE_BATCH_TRAFFIC_CHECK_GAP_DAYS
              </code>
              → không xếp hàng. SP không traffic vẫn theo TTL{' '}
              <code className="text-[11px] bg-white px-1 rounded border border-gray-200">
                ADMIN_SOURCE_BATCH_SCAN_COOLDOWN_DAYS
              </code>{' '}
              (= <strong>{cooldownDays}</strong> ngày theo API hiện tại). Một lần chạy cần{' '}
              <code className="text-[11px] bg-white px-1 rounded border border-gray-200">link_default</code> đủ dài trong DB.
            </p>
            <p>
              <strong>Hibox:</strong> quy đổi <code className="text-[11px] bg-white px-1 rounded border">hibox.mn/v/…</code> rồi
              scrape. <strong>CSSBuy:</strong> quy đổi <code className="text-[11px] bg-white px-1 rounded border">item-1688-…</code> /{' '}
              <code className="text-[11px] bg-white px-1 rounded border">item-….html</code> — API{' '}
              <code className="text-[11px] bg-white px-1 rounded border">POST /web/item</code> (không cần modal rủi ro).
            </p>
          </div>
        </details>
      </header>

      {toast ? (
        <div
          className={`fixed bottom-4 right-4 z-[130] max-w-[min(22rem,calc(100vw-1.5rem))] rounded-lg border px-3 py-2 text-sm shadow-lg ${
            toast.type === 'err'
              ? 'bg-red-50 border-red-200 text-red-800'
              : toast.type === 'ok'
                ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
                : 'bg-amber-50 border-amber-200 text-amber-900'
          }`}
          role="status"
        >
          {toast.msg}
        </div>
      ) : null}

      {lastError && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          <p className="font-medium">Lỗi khi gọi API</p>
          <p className="mt-1 whitespace-pre-wrap">{lastError}</p>
          <button
            type="button"
            onClick={() => setLastError(null)}
            className="mt-3 text-sm font-semibold underline"
          >
            Đóng
          </button>
        </div>
      )}

      <div className="rounded-xl border border-gray-200 bg-white p-4 sm:p-5 shadow-sm space-y-4">
        <div className="flex flex-wrap items-end gap-4 gap-y-3">
          <div className="flex flex-col gap-1 min-w-[10rem]">
            <span className="text-xs font-medium text-gray-500">Luồng</span>
            <p className="text-sm font-semibold text-gray-900">Theo DB (queue)</p>
            <p className="text-[11px] text-gray-500 max-w-[19rem] leading-snug">
              Worker máy chủ (mặc định <strong>bật</strong>, scrape Hibox) tiếp tục đọc và cập nhật DB — tab chỉ làm dashboard, không có
              lượt chạy từ trình duyệt.
            </p>
          </div>
          <div className="flex flex-col gap-1 flex-1 min-w-[12rem] max-w-md">
            <label htmlFor="source-domain-select" className="text-xs font-medium text-gray-500">
              Góc nhìn thống kê (batch)
            </label>
            <select
              id="source-domain-select"
              className="border border-gray-300 rounded-lg px-3 h-10 text-sm w-full"
              value={domain}
              onChange={(e) => setDomain(e.target.value as SourceStockDomain)}
            >
              <option value="hibox">hibox.mn — scrape</option>
              <option value="cssbuy">cssbuy.com — API /web/item</option>
            </select>
            <p className="text-[11px] text-gray-500 mt-1 leading-snug">
              Lọc số trong «Tiến độ DB» và «Báo cáo 30 ngày» theo chiều admin batch đã định nghĩa — không đổi worker nền (luôn Hibox).
            </p>
          </div>
        </div>

        <section
          className="rounded-lg border border-indigo-100 bg-indigo-50/70 px-3 py-3 space-y-2"
          aria-label="Tiến trình worker và tạm dừng trên DB"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 space-y-1">
              <p className="text-xs font-semibold text-indigo-950 uppercase tracking-wide">Worker PDP / Hibox (server)</p>
              {workerState ? (
                <>
                  <p className="text-[11px] text-indigo-950/85 leading-snug">
                    ENV <code className="text-[10px] px-1 bg-white/80 rounded border border-indigo-100">SOURCE_STOCK_CHECK_ENABLED</code>:{' '}
                    <strong>{workerState.env_source_stock_check_enabled ? 'bật' : 'tắt'}</strong>
                    {' · '}Cờ tạm dừng (DB){' '}
                    <strong>{workerState.db_paused ? 'BẬT — không scrape' : 'tắt'}</strong>
                    {workerState.db_pause_updated_at_utc_iso
                      ? ` · ${formatReportTimestampUtc(workerState.db_pause_updated_at_utc_iso)}`
                      : ''}
                    <br />
                    Luồng <code className="text-[10px] px-1 bg-white/80 rounded border border-indigo-100">source-stock-checker</code>{' '}
                    trong process này:{' '}
                    <strong>{workerState.daemon_thread_alive ? 'đang chạy' : 'không hoạt động / chưa bật'}</strong>
                    {' · '}Hàng chờ RAM process:{' '}
                    <strong className="tabular-nums">{workerState.process_in_memory_queue_depth}</strong>
                    {' · '}chu kỳ ~{' '}
                    <strong className="tabular-nums">{workerState.check_interval_seconds}s</strong>
                  </p>
                  {workerState.effective_idle_reason ? (
                    <p className="text-[11px] text-amber-950 bg-amber-50/95 border border-amber-100 rounded-md px-2 py-1.5">
                      Hiện worker idle:{' '}
                      <code className="text-[10px]">{workerState.effective_idle_reason}</code>
                      {workerState.effective_idle_hint_vi ? ` — ${workerState.effective_idle_hint_vi}` : null}
                    </p>
                  ) : null}
                  {workerState.products_commit_audit ? (
                    workerState.products_commit_audit.ok === false ? (
                      <div
                        role="alert"
                        className="rounded-md border border-red-200 bg-red-50 px-2 py-1.5 text-[11px] text-red-900 space-y-1"
                      >
                        <p className="font-semibold">Commit bảng products: chưa ghi được (hoặc lỗi ghi).</p>
                        {workerState.products_commit_audit.detail ? (
                          <p className="whitespace-pre-wrap leading-snug">{workerState.products_commit_audit.detail}</p>
                        ) : null}
                        {workerState.products_commit_audit.at_utc_iso ? (
                          <p className="text-[10px] opacity-85">
                            Ghi nhận audit:{' '}
                            <span className="font-mono">{formatReportTimestampUtc(workerState.products_commit_audit.at_utc_iso)}</span>{' '}
                            {workerState.products_commit_audit.product_db_id != null ? (
                              <span className="font-mono">{` · DB #${workerState.products_commit_audit.product_db_id}`}</span>
                            ) : null}
                          </p>
                        ) : null}
                        {workerState.products_commit_audit.consistency_hint_vi ? (
                          <p className="text-[10px] leading-snug border-t border-red-100 pt-1 mt-1">
                            {workerState.products_commit_audit.consistency_hint_vi}
                          </p>
                        ) : null}
                      </div>
                    ) : (
                      <div
                        role="status"
                        className={`rounded-md border px-2 py-1.5 text-[11px] space-y-1 ${
                          workerState.products_commit_audit.ok === true
                            ? 'border-emerald-200 bg-emerald-50/90 text-emerald-950'
                            : 'border-amber-200 bg-amber-50/90 text-amber-950'
                        }`}
                      >
                        <p className="font-semibold">
                          Commit bảng products:{' '}
                          {workerState.products_commit_audit.ok === true
                            ? 'đã ghi (theo audit worker state).'
                            : 'chưa rõ — xem detail / đối chiếu.'}
                        </p>
                        {workerState.products_commit_audit.detail ? (
                          <p className="text-[10px] leading-snug opacity-90 whitespace-pre-wrap">
                            {workerState.products_commit_audit.detail}
                          </p>
                        ) : null}
                        {workerState.products_commit_audit.at_utc_iso ? (
                          <p className="text-[10px] opacity-85">
                            Thời điểm audit:{' '}
                            <span className="font-mono">{formatReportTimestampUtc(workerState.products_commit_audit.at_utc_iso)}</span>
                            {workerState.products_commit_audit.product_db_id != null ? (
                              <span className="font-mono">{` · DB #${workerState.products_commit_audit.product_db_id}`}</span>
                            ) : null}
                          </p>
                        ) : null}
                        {workerState.products_commit_audit.consistency_hint_vi ? (
                          <p className="text-[10px] leading-snug border-t border-black/5 pt-1 mt-1 opacity-95">
                            {workerState.products_commit_audit.consistency_hint_vi}
                          </p>
                        ) : null}
                      </div>
                    )
                  ) : (
                    <p className="text-[10px] text-indigo-900/70">
                      Chưa có audit commit bảng products — lần scrape đầu sau khi cập nhật backend sẽ có dòng trạng thái tại đây.
                    </p>
                  )}
                  <details className="text-[10px] text-indigo-900/85">
                    <summary className="cursor-pointer underline font-medium text-indigo-900 select-none">Nhiều tiến trình / VPS</summary>
                    <p className="mt-1.5 leading-relaxed">{workerState.deployment_notes_vi}</p>
                  </details>
                </>
              ) : (
                <p className="text-[11px] text-indigo-900/85">
                  Chưa có snapshot worker — đang tải cùng «Làm mới queue» hoặc lỗi mạng. Bấm «Làm mới queue» để đọc lại API.
                </p>
              )}
            </div>
            <div className="flex flex-wrap gap-2 shrink-0">
              <button
                type="button"
                aria-label="Tạm dừng kiểm tra nguồn, ghi cờ vào DB"
                disabled={
                  pauseActionBusy || !workerState || workerState.db_paused || !workerState.env_source_stock_check_enabled
                }
                className="rounded-lg border border-amber-200 bg-white px-3 py-2 text-xs font-semibold text-amber-950 hover:bg-amber-50 disabled:opacity-45 disabled:pointer-events-none"
                onClick={() => void toggleWorkerPauseFromDb(true)}
              >
                {pauseActionBusy ? 'Đang ghi…' : 'Tạm dừng (DB)'}
              </button>
              <button
                type="button"
                aria-label="Bỏ tạm dừng, worker chạy lại trong các process backend"
                disabled={pauseActionBusy || !workerState || !workerState.db_paused}
                className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-950 hover:bg-emerald-100 disabled:opacity-45 disabled:pointer-events-none"
                onClick={() => void toggleWorkerPauseFromDb(false)}
              >
                Chạy tiếp (DB)
              </button>
            </div>
          </div>
          {workerState ? (
            <div className="space-y-2 pt-2 mt-2 border-t border-indigo-100/80">
              <p className="text-[10px] font-semibold text-indigo-950/90 uppercase tracking-wide">Link PDP — tiến trình scrape</p>
              <div className="grid md:grid-cols-3 gap-2">
                <WorkerStockProgressCard
                  tone="sky"
                  title="Đang chạy"
                  subtitle="Ghi vào DB khi worker bước vào scrape (mọi process đọc chung)."
                  row={workerState.checking}
                  emptyHint="Không có SP đang «checking» trên snapshot — có thể worker đang nghỉ giữa chu kỳ hoặc vừa xong và chưa kịp vào PDP kế."
                  mode="checking"
                />
                <WorkerStockProgressCard
                  tone="emerald"
                  title="Vừa chạy xong"
                  subtitle="PDP kết thúc gần nhất đã commit trạng thái."
                  row={workerState.last_completed}
                  emptyHint="Chưa ghi «vừa xong» (chưa có lần scrape commit / worker mới restart)."
                  mode="completed"
                />
                <WorkerStockProgressCard
                  tone="slate"
                  title="Chuẩn bị chạy tiếp"
                  subtitle="Ưu tiên FIFO hàng chờ RAM process này, rồi SP đến hạn theo DB."
                  row={workerState.next_upcoming_primary}
                  emptyHint="FIFO RAM trống và không còn dòng đến hạn phù hợp trong bản preview (hoặc đang chờ TTL)."
                  mode="upcoming"
                />
              </div>
              {(workerState.upcoming_candidates ?? []).length > 0 ? (
                <details className="rounded-md border border-indigo-100/80 bg-white/60 px-2 py-1.5 text-[10px] text-indigo-950/90">
                  <summary className="cursor-pointer font-medium select-none underline">
                    Các PDP xếp tiếp theo snapshot ({workerState.upcoming_candidates?.length ?? 0} dòng)
                  </summary>
                  <ol className="mt-2 list-decimal pl-4 space-y-2">
                    {(workerState.upcoming_candidates ?? []).map((u) => (
                      <li key={`${String(u.queue_hint)}-${String(u.product_db_id)}`} className="leading-snug">
                        <span className="font-mono">#{u.product_db_id}</span>
                        {u.product_code ? (
                          <>
                            {' · '}<span className="font-mono">{u.product_code}</span>
                          </>
                        ) : null}{' '}
                        —{' '}
                        <ExternalHttpLink url={u.link_default ?? ''} />
                        {u.queue_hint_vi ? (
                          <span className="block text-[9px] text-slate-600 mt-0.5">{u.queue_hint_vi}</span>
                        ) : null}
                      </li>
                    ))}
                  </ol>
                </details>
              ) : null}
              {workerState.progress_notes_vi ? (
                <p className="text-[10px] text-slate-600 leading-relaxed italic">{workerState.progress_notes_vi}</p>
              ) : null}
            </div>
          ) : null}
        </section>

        <div className="flex flex-wrap items-center gap-2 py-2 border-y border-gray-100">
          <button
            type="button"
            disabled={queueStatsLoading}
            className="text-xs font-semibold text-indigo-700 underline underline-offset-2 disabled:opacity-45"
            onClick={() => void refreshQueueStats()}
          >
            {queueStatsLoading ? 'Đang đếm queue…' : 'Làm mới queue'}
          </button>
          <button
            type="button"
            disabled={activityReportLoading}
            className="text-xs font-semibold text-indigo-700 underline underline-offset-2 disabled:opacity-45"
            onClick={() => void refreshActivityReport()}
          >
            {activityReportLoading ? 'Đang tải BC…' : 'Làm mới báo cáo 30 ngày'}
          </button>
        </div>

        <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-gray-800 bg-slate-50 border border-slate-100 rounded-lg px-3 py-2">
              <span>TTL cổ điển {cooldownDays} ngày</span>
              {queueStats?.admin_batch_traffic_check_gap_days != null ? (
                <span className="text-gray-600">· PDP gap {queueStats.admin_batch_traffic_check_gap_days}d</span>
              ) : null}
              {queueStats?.admin_batch_traffic_view_window_days != null ? (
                <span className="text-gray-600">· PDP cửa sổ {queueStats.admin_batch_traffic_view_window_days}d</span>
              ) : null}
            </div>

            {queueStatsLoading && !queueStats ? (
              <p className="text-xs text-gray-500">Đang đếm hàng chờ…</p>
            ) : queueStats ? (
              <div className="space-y-2">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">Tiến độ DB · is_active</p>
                <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
                  <MiniStat label="Tổng phạm vi" value={queueStats.total_in_scope} variant="slate" />
                  <MiniStat label="Đến lượt ngay" value={queueStats.eligible_now} variant="emerald" />
                  <MiniStat label="PDP trong đến lượt" value={queueStats.eligible_with_recent_customer_view ?? 0} variant="violet" />
                  <MiniStat label="Chờ TTL" value={queueStats.in_cooldown} variant="amber" />
                  <MiniStat label="Chưa batch lần nào" value={queueStats.eligible_never_scanned ?? 0} variant="slate" />
                  <MiniStat label="Đến lượt sau TTL" value={queueStats.eligible_rescan_after_ttl ?? 0} variant="teal" />
                  <MiniStat
                    label="Đến lượt không PDP"
                    value={queueStats.eligible_without_recent_customer_view ?? 0}
                    variant="slate"
                  />
                </div>
                <details className="text-[11px] text-gray-600 rounded-lg border border-slate-100 bg-white px-2.5 py-1.5">
                  <summary className="cursor-pointer font-medium text-gray-800 select-none">Cách đếm &amp; thứ tự chọn</summary>
                  <p className="mt-2 leading-relaxed">
                    Ưu tiên PDP traffic trong cửa sổ; trong mỗi nhóm:{' '}
                    <code className="bg-gray-50 px-0.5 rounded border border-gray-200">admin_source_batch_scanned_at</code> chưa
                    có đi trước → ai càng cũ càng được lấy → <code className="bg-gray-50 px-0.5 rounded border border-gray-200">products.id</code> tăng dần. «Chờ TTL» gồm SP traffic chưa qua chờ-gap và SP không traffic chưa qua TTL cổ điển.
                  </p>
                </details>
              </div>
            ) : (
              <p className="text-xs text-gray-500">Không đọc được số đếm — bấm «Làm mới queue».</p>
            )}

            <div
              className={`rounded-lg border px-3 py-3 ${
                activityReportError ? 'border-red-200 bg-red-50/70' : 'border-indigo-100 bg-indigo-50/40'
              }`}
              aria-labelledby="source-stock-report-heading"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                <h3 id="source-stock-report-heading" className="text-sm font-semibold text-indigo-950">
                  Báo cáo cửa sổ <span className="tabular-nums">{activityReport?.window_days ?? 30}</span> ngày{' '}
                  <span className="font-normal text-indigo-800/85 text-xs">(UTC rolling)</span>
                </h3>
              </div>
              <details className="text-[11px] text-indigo-900/85 mb-2 rounded border border-white/70 bg-white/50 px-2 py-1.5">
                <summary className="cursor-pointer font-medium select-none text-indigo-950">Giải thích nhanh các cột đếm</summary>
                <p className="mt-2 text-gray-700 leading-relaxed">
                  Cùng phạm vi <code className="text-[10px] bg-gray-50 px-0.5 rounded border">is_active</code> và link như queue. «TTL
                  batch»: <code className="text-[10px] bg-gray-50 px-0.5 rounded border">admin_source_batch_scanned_at</code> trong
                  cửa sổ. «Kiểm tra nguồn»: <code className="text-[10px] bg-gray-50 px-0.5 rounded border">source_stock_checked_at</code>{' '}
                  trong cửa sổ. Hết / còn: theo{' '}
                  <code className="text-[10px] bg-gray-50 px-0.5 rounded border">source_stock_status</code> và tồn.
                </p>
              </details>
              {activityReportError ? (
                <div
                  role="alert"
                  className="rounded border border-red-200 bg-white px-2 py-1.5 text-xs text-red-900 mb-2 flex flex-wrap items-center gap-x-2 gap-y-1"
                >
                  <span>{activityReportError}</span>
                  <button type="button" className="underline font-medium shrink-0" onClick={() => void refreshActivityReport()}>
                    Thử lại
                  </button>
                </div>
              ) : null}
              {activityReportLoading && !activityReport ? (
                <p className="text-xs text-indigo-900/85">Đang tải báo cáo…</p>
              ) : null}
              {activityReport ? (
                <>
                  <p className="text-[11px] text-slate-700 mb-2">
                    <span className="text-gray-500">Từ</span>{' '}
                    <code className="text-[10px] bg-white/95 px-1 rounded border border-indigo-100">
                      {activityReport.window_since_utc_iso}
                    </code>{' '}
                    <span className="text-gray-500">·</span> Mẫu / bảng tối đa{' '}
                    <strong className="tabular-nums">{activityReport.detail_limit_applied}</strong> dòng
                  </p>
                  <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-7 gap-2 mb-2">
                    <MiniStat label="Đến lượt ngay" value={activityReport.queue.eligible_now} variant="emerald" />
                    <MiniStat
                      label="TTL batch trong cửa sổ"
                      value={activityReport.counts.batch_ttl_stamped_in_window}
                      variant="slate"
                    />
                    <MiniStat
                      label="Đã có checked_at"
                      value={activityReport.counts.source_stock_checked_any_in_window}
                      variant="slate"
                    />
                    <MiniStat
                      label="Cờ hết trong cửa sổ"
                      value={activityReport.counts.source_stock_oos_signal_in_window}
                      variant="rose"
                    />
                    <MiniStat
                      label="Cờ còn trong cửa sổ"
                      value={activityReport.counts.source_stock_in_stock_signal_in_window}
                      variant="teal"
                    />
                    <MiniStat
                      label="Sau KT: tồn &gt; 0"
                      value={activityReport.counts.checked_available_positive_in_window}
                      variant="emerald"
                    />
                    <MiniStat
                      label="Sau KT: tồn ≤ 0"
                      value={activityReport.counts.checked_available_zero_or_negative_in_window}
                      variant="amber"
                    />
                  </div>
                  <div className="flex flex-wrap items-center gap-2 mb-2">
                    <span className="text-[11px] font-semibold text-slate-600">status khi có checked_at trong cửa sổ:</span>
                  </div>
                  <ul className="flex flex-wrap gap-1.5 text-[11px] mb-2">
                    {Object.entries(activityReport.checked_in_window_by_source_stock_status)
                      .sort((a, b) => b[1] - a[1])
                      .map(([k, v]) => (
                        <li
                          key={k}
                          className="rounded-full bg-white/95 border border-slate-200 px-2 py-0.5 font-mono text-[10px]"
                        >
                          {k}: <strong>{v.toLocaleString('vi-VN')}</strong>
                        </li>
                      ))}
                    {Object.keys(activityReport.checked_in_window_by_source_stock_status).length === 0 ? (
                      <li className="text-slate-500 text-[11px]">Không có checked_at trong cửa sổ.</li>
                    ) : null}
                  </ul>
                  <SourceStockReportSampleTable
                    title="Mẫu: cờ hết hàng (out_of_stock) trong cửa sổ"
                    rows={activityReport.samples.oos}
                    emptyHint={
                      'Không có sản DB nào thỏa: trong cửa sổ 30 ngày + source_stock_status = out_of_stock. Nếu vừa kiểm tra xong — bấm «Làm mới báo cáo 30 ngày».' +
                      ' Luôn gắn cờ lên đúng SP được chọn trong hàng chờ (neo), không chỉ dựa slug.'
                    }
                    defaultOpen
                    oosActions={reportOosActionsForTable}
                    oosBulkSelection={reportOosBulkSelection}
                  />
                  {activityReport.samples.oos.length === 0 ? (
                    <div className="rounded-lg border border-amber-200 bg-amber-50/80 px-3 py-2 mb-3 text-[11px] text-amber-950 leading-snug">
                      <p className="font-semibold mb-1">Vì sao vừa «hết» nhưng bảng này vẫn trống, hoặc F5 là mất link?</p>
                      <ul className="list-disc ml-4 space-y-1 text-amber-900/95">
                        <li>
                          Dữ liệu bền nằm ở bảng mẫu và tab sản CRM (theo cờ và timestamp trong DB), không nhờ bảng tạm trên tab.
                        </li>
                        <li>
                          <strong>Hàng chờ DB:</strong> mỗi lần kiểm tra sẽ ghi{' '}
                          <code className="text-[10px] bg-white px-0.5">source_stock_checked_at</code> và{' '}
                          <code className="text-[10px] bg-white px-0.5">source_stock_status</code> lên đúng{' '}
                          <code className="text-[10px] bg-white px-0.5">products.id</code> được lấy từ queue. Nếu hết nguồn thì
                          thêm tồn ≤ 0 / <code className="text-[10px] bg-white px-0.5">out_of_stock</code>; nếu đọc OK thì ghi{' '}
                          <code className="text-[10px] bg-white px-0.5">in_stock</code>; nếu lỗi scrape / không khẳng định được thì ghi{' '}
                          <code className="text-[10px] bg-white px-0.5">error</code>.
                        </li>
                        <li>
                          Nếu JSON có <code className="text-[10px] bg-white px-0.5">classified_out_of_stock = true</code> và đã commit
                          nhưng bảng này chưa đổi: bấm <strong>«Làm mới báo cáo 30 ngày»</strong>, kiểm tra ô domain (hibox/cssbuy)
                          và <code className="text-[10px] bg-white px-0.5">updates_committed</code>.
                        </li>
                        <li>
                          Card <strong>«Sau KT: tồn ≤ 0»</strong> khác chỉ báo{' '}
                          <code className="text-[10px] ml-1 bg-white px-0.5">out_of_stock</code> của bảng OOS — đừng so sánh một-một.
                        </li>
                      </ul>
                    </div>
                  ) : null}
                  <SourceStockReportSampleTable
                    title="Mẫu: cờ còn hàng (in_stock) trong cửa sổ"
                    rows={activityReport.samples.in_stock}
                    emptyHint="Không có dòng trong phạm vi."
                    defaultOpen={false}
                  />
                  <SourceStockReportSampleTable
                    title="Mẫu: TTL batch gần nhất trong cửa sổ"
                    rows={activityReport.samples.batch_ttl_recent}
                    emptyHint="Không có dòng trong phạm vi."
                    defaultOpen={false}
                  />
                </>
              ) : !activityReportLoading && !activityReportError ? (
                <p className="text-xs text-slate-600">Chưa có dữ liệu báo cáo.</p>
              ) : null}
            </div>
        </div>

        <div className="space-y-3 pt-4 border-t border-gray-100">
          <div
            role="status"
            aria-live="polite"
            className="flex flex-wrap items-start gap-2.5 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700"
          >
            <span className="h-2 w-2 mt-1.5 rounded-full bg-emerald-500 shrink-0" aria-hidden />
            <div className="flex flex-col gap-0.5 min-w-0">
              <span className="font-semibold text-slate-900">Luồng chính: máy chủ</span>
              <span className="text-xs sm:text-sm text-slate-700 leading-snug max-w-4xl">
                Worker kiểm tra nguồn chạy trong process backend với{' '}
                <code className="text-[10px] bg-white px-1 rounded border">SOURCE_STOCK_CHECK_ENABLED=true</code> (mặc định). Các ô đếm
                trên chỉ đọc DB đã được worker/hệ thống ghi — để tần suất / sự cố, chỉnh env và log trên máy chủ (tab không bắt đầu
                scrape tay).
              </span>
            </div>
          </div>
        </div>
      </div>

      {reportOosDeleteConfirmIds != null ? (
        <div
          className="fixed inset-0 z-[121] flex items-center justify-center bg-black/45 p-4"
          role="presentation"
          onClick={() => {
            if (!reportOosDeleting) setReportOosDeleteConfirmIds(null);
          }}
        >
          <div
            className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 border border-gray-200"
            role="dialog"
            aria-modal="true"
            aria-labelledby="report-oos-del-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 id="report-oos-del-title" className="text-lg font-bold text-gray-900">
              Xóa vĩnh viễn {reportOosDeleteConfirmIds.length} sản khỏi DB cửa hàng?
            </h3>
            <div className="text-sm text-gray-700 mt-3 leading-relaxed space-y-2">
              <p>
                Sẽ xóa theo khóa <code className="text-xs bg-gray-100 px-1 rounded">products.id</code> — không
                hoàn tác (kèm dọn Bunny). Thích hợp khi chắc chắn không còn bán những mã này.
              </p>
              {!reportOosDeleting ? (
                <ul className="mt-2 max-h-48 overflow-auto border border-gray-100 rounded-lg divide-y divide-gray-100 text-[13px]">
                  {reportOosDeleteConfirmIds.slice(0, 18).map((id) => {
                    const row = reportOosRowById.get(id);
                    return (
                      <li key={id} className="px-3 py-2 flex flex-col gap-0.5">
                        <span className="font-mono text-xs text-gray-900">#{id}</span>
                        <span className="text-gray-800 line-clamp-2">{row?.name ?? '—'}</span>
                      </li>
                    );
                  })}
                </ul>
              ) : null}
              {reportOosDeleteConfirmIds.length > 18 && !reportOosDeleting ? (
                <p className="text-xs text-gray-500">
                  và {reportOosDeleteConfirmIds.length - 18} mã khác trong cùng lần xóa.
                </p>
              ) : null}
            </div>
            <div className="flex flex-wrap gap-3 justify-end mt-6">
              <button
                type="button"
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50 disabled:opacity-50"
                disabled={reportOosDeleting}
                onClick={() => setReportOosDeleteConfirmIds(null)}
              >
                Hủy
              </button>
              <button
                type="button"
                className="rounded-lg bg-red-700 text-white px-4 py-2 text-sm font-semibold hover:bg-red-800 disabled:opacity-50"
                disabled={reportOosDeleting}
                onClick={() => void executeReportOosDeleteFromDb()}
              >
                {reportOosDeleting ? 'Đang xóa…' : 'Đồng ý — xóa'}
              </button>
            </div>
          </div>
        </div>
      ) : null}

    </div>
  );
}
