'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  adminProductAPI,
  type AdminSourceStockActivityReport,
  type AdminSourceStockActivityReportSampleRow,
  type AdminSourceStockBatchDbNextResult,
  type AdminSourceStockBatchOneMatched,
  type AdminSourceStockBatchOneResult,
  type AdminSourceStockQueueStats,
} from '@/lib/admin-api';

const EMPTY_REPORT_SAMPLE_ROWS: AdminSourceStockActivityReportSampleRow[] = [];

/** Nguồn kiểm tra: Hibox (scrape) hoặc CSSBuy (API /web/item — không cần bấm modal). */
type SourceStockDomain = 'hibox' | 'cssbuy';

/** Theo DB + bật lặp: khoảng cách ngẫu nhiên giữa hai lần *bắt đầu* kiểm tra (sequential — chờ xong SP hiện tại). */
const ADMIN_SOURCE_DB_LOOP_GAP_MS_MIN = 46_000;
const ADMIN_SOURCE_DB_LOOP_GAP_MS_MAX = 60_000;

function randomAdminSourceLoopGapMs(): number {
  const span = ADMIN_SOURCE_DB_LOOP_GAP_MS_MAX - ADMIN_SOURCE_DB_LOOP_GAP_MS_MIN + 1;
  return ADMIN_SOURCE_DB_LOOP_GAP_MS_MIN + Math.floor(Math.random() * span);
}

/** Kết quả một lần gọi run-next (phục vụ lặp tuần tự). */
type RunNextOutcome = 'ok' | 'halt' | 'fail';

type OosRow = AdminSourceStockBatchOneMatched & {
  rowKey: string;
  sourceUrl: string;
  canonicalUrl: string;
  domain: SourceStockDomain;
  reason: string;
  checkedAtIso: string;
};

/** Trong lúc gọi API máy chủ chọn SP từ hàng chờ. */
type ActiveCheck = { mode: 'db' };

type LastFinishedCheck =
  | {
      kind: 'ok';
      finishedAtIso: string;
      attemptedUrl: string;
      canonicalUrl: string;
      domain: SourceStockDomain;
      seedProductDbId?: number | null;
      seedProductName?: string | null;
      classifiedOutOfStock: boolean;
      updatesCommitted?: boolean;
      rawStatus?: string | null;
      detail?: string | null;
      warnings: string[];
    }
  | { kind: 'queue_empty'; finishedAtIso: string; detail?: string | null }
  | {
      kind: 'error';
      finishedAtIso: string;
      attemptedUrl?: string;
      message: string;
    };

function buildLastOkFromApi(
  res: AdminSourceStockBatchDbNextResult | AdminSourceStockBatchOneResult,
  attemptedUrl: string,
  domainUsed: SourceStockDomain,
): Extract<LastFinishedCheck, { kind: 'ok' }> {
  const dbr = res as AdminSourceStockBatchDbNextResult;
  return {
    kind: 'ok',
    finishedAtIso: new Date().toISOString(),
    attemptedUrl: attemptedUrl.trim() || res.canonical_url?.trim() || '—',
    canonicalUrl: (res.canonical_url || '').trim() || '—',
    domain: domainUsed,
    seedProductDbId: dbr.seed_product_db_id,
    seedProductName: dbr.seed_product_name,
    classifiedOutOfStock: !!res.classified_out_of_stock,
    updatesCommitted: res.updates_committed,
    rawStatus: res.raw_status,
    detail: res.detail,
    warnings: res.warnings ?? [],
  };
}

/** Ghi chú hàng chờ DB vào ô Lý do. */
function stockScanReasonLine(
  res: AdminSourceStockBatchOneResult | AdminSourceStockBatchDbNextResult,
): string | undefined {
  const r = res as AdminSourceStockBatchDbNextResult;
  if (r.seed_product_db_id == null) return undefined;
  const name = r.seed_product_name?.trim();
  return `Hàng DB #${r.seed_product_db_id}${name ? `: ${name}` : ''}`;
}

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

function newOosRowKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `oos-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}

/** DOM/API không khẳng định được còn hàng — không được coi «hết hàng» trong nghiệp vụ cửa hàng. */
function isUnresolvedStockProbe(raw: string | null | undefined): boolean {
  const s = (raw || '').trim().toLowerCase();
  return ['error', 'unknown', 'fetch_error', 'bad_url', 'no_data'].includes(s);
}

/** Phản hồi raw_status «blocked» (hiếm) hoặc heuristic chặn — dừng lặp queue, chi tiết trong `detail`. */
function isBlockedBySourceSite(raw: string | null | undefined): boolean {
  return (raw || '').trim().toLowerCase() === 'blocked';
}

/** Backend đôi khi trả `unknown`/`error` nhưng `detail` vẫn mô tả captcha/chặn — dừng lặp như `blocked`. */
function detailLooksLikeCaptchaOrSiteBlock(detail: string | null | undefined): boolean {
  const u = (detail || '').trim();
  if (!u) return false;
  const low = u.toLowerCase();
  if (/cloudflare|security verification|csrf-token không đọc được|không đọc được csrf/i.test(low)) {
    return true;
  }
  if (
    /\bcaptcha\b|\bverify\b|verification\b|rate\s*limit|too\s+many\s+requests|\b403\b|\bforbidden\b|\bblocked\b|access\s+denied|\bpunish\b|nocaptcha/i.test(
      low,
    )
  ) {
    return true;
  }
  if (
    /验证码|验证失败|校验|扫码验证|滑动验证|滑块|安全验证|人机验证|风控|拦截|访问过于频繁|请登录|登录后|passport|x5sec|_____tmd____|wh_nav/i.test(u)
  ) {
    return true;
  }
  if (/khung chặn|captcha|interstitial|anti-bot/i.test(low)) {
    return true;
  }
  return false;
}

function shouldStopAutoForAntiBot(
  res: AdminSourceStockBatchDbNextResult | AdminSourceStockBatchOneResult,
): boolean {
  if (isBlockedBySourceSite(res.raw_status)) return true;
  if (!isUnresolvedStockProbe(res.raw_status)) return false;
  return detailLooksLikeCaptchaOrSiteBlock(res.detail);
}

function isDualPlatformHardFailure(res: AdminSourceStockBatchOneResult): boolean {
  return res.dual_platform_both_failed === true;
}

function isAntiBotUiHighlight(raw: string | null | undefined, detail: string | null | undefined): boolean {
  return isBlockedBySourceSite(raw) || (isUnresolvedStockProbe(raw) && detailLooksLikeCaptchaOrSiteBlock(detail));
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

function sleepMs(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
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
                    {formatReportTimestampUtc(row.source_stock_checked_at)}
                  </td>
                  <td className="px-2 py-1.5 whitespace-nowrap text-[11px]">
                    {formatReportTimestampUtc(row.admin_source_batch_scanned_at)}
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
  const [auto, setAuto] = useState(true);
  const [running, setRunning] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: 'ok' | 'info' | 'err'; msg: string } | null>(null);
  const [domain, setDomain] = useState<SourceStockDomain>('hibox');
  /** Sen kẽ thứ tự Hibox/CSSBuy + fallback trong một lần kiểm tra (backend). */
  const [dualAlternateFallback, setDualAlternateFallback] = useState(false);

  /** DB: cứ SAU id này thì query SP kế có link_default trong bộ lọc */
  const [dbCursorAfterId, setDbCursorAfterId] = useState(0);

  const [recent, setRecent] = useState<Array<AdminSourceStockBatchDbNextResult | AdminSourceStockBatchOneResult>>(
    [],
  );
  const [oosRows, setOosRows] = useState<OosRow[]>([]);
  /** Số lần đã gọi kiểm tra thành công (phiên làm việc) */
  const [sessionChecks, setSessionChecks] = useState(0);
  /** Số ngày chờ để một SP được xếp hàng kiểm tra lại (theo backend, mặc định 30). */
  const [cooldownDays, setCooldownDays] = useState(30);
  const [deleteDbModalOpen, setDeleteDbModalOpen] = useState(false);
  const [bulkDeletingDb, setBulkDeletingDb] = useState(false);
  const [queueStats, setQueueStats] = useState<AdminSourceStockQueueStats | null>(null);
  const [queueStatsLoading, setQueueStatsLoading] = useState(false);
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
  const [activeCheck, setActiveCheck] = useState<ActiveCheck | null>(null);
  const [lastFinished, setLastFinished] = useState<LastFinishedCheck | null>(null);

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

  /** Cột «DB id» trong bảng = `products.id` (để xóa thật trên máy chủ). */
  const oosDistinctDbIds = useMemo(() => {
    const s = new Set<number>();
    for (const row of oosRows) {
      if (typeof row.id === 'number' && row.id > 0) s.add(row.id);
    }
    return Array.from(s).sort((a, b) => a - b);
  }, [oosRows]);

  const alternateSeqRef = useRef(0);
  /** Theo DB: giữ `products.id` khi lần trước lỗi tạm — backend + tab luôn retry đúng SP đó trước. */
  const stickySeedProductIdRef = useRef<number | null>(null);

  /** Luôn khớp render hiện tại — async loop đọc sau `await` không bị stale như chỉ state. */
  const autoGateRef = useRef(auto);
  autoGateRef.current = auto;

  useEffect(() => {
    stickySeedProductIdRef.current = null;
  }, [domain]);

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
  }, [domain]);

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
        running ||
        bulkDeletingDb ||
        activityReportLoading ||
        reportOosDeleting ||
        reportOosBulkBusy,
      onDeleteDb: (row) => requestReportOosDeleteDbIds([row.id]),
      onClearFlag: handleReportOosClearFlag,
      onRecheck: handleReportOosRecheck,
    }),
    [
      activityReportLoading,
      bulkDeletingDb,
      handleReportOosClearFlag,
      handleReportOosRecheck,
      reportOosBulkBusy,
      reportOosDeleting,
      reportOosRowBusyById,
      requestReportOosDeleteDbIds,
      running,
    ],
  );

  const bumpOosRows = useCallback(
    (res: AdminSourceStockBatchDbNextResult | AdminSourceStockBatchOneResult, attemptedUrl: string) => {
      if (!res.classified_out_of_stock) return;
      const seedLine = stockScanReasonLine(res);
      const markLine =
        typeof (res as AdminSourceStockBatchDbNextResult).seed_admin_batch_scanned_at === 'string'
          ? `Đánh dấu queue: ${(res as AdminSourceStockBatchDbNextResult).seed_admin_batch_scanned_at}`
          : undefined;
      const reason = [
        seedLine,
        markLine,
        res.raw_status ?? '',
        res.detail ?? '',
        (res.warnings ?? []).slice(0, 2).join('; '),
      ]
        .filter(Boolean)
        .join(' · ')
        .slice(0, 520);

      const products: AdminSourceStockBatchOneMatched[] =
        res.matched_products?.length > 0
          ? res.matched_products
          : [{ id: 0, name: '— không khớp sản phẩm trong shop —', slug: '', product_id: null }];

      const iso = new Date().toISOString();
      const dom = res.domain as SourceStockDomain;

      setOosRows((prev) => {
        const next = [...prev];
        for (const m of products) {
          const dedupeKey = `${m.id}|${attemptedUrl}|${res.canonical_url}|${reason.slice(0, 80)}`;
          if (
            next.some(
              (row) =>
                `${row.id}|${row.sourceUrl}|${row.canonicalUrl}|${row.reason.slice(0, 80)}` === dedupeKey,
            )
          )
            continue;
          next.unshift({
            rowKey: newOosRowKey(),
            ...m,
            sourceUrl: attemptedUrl,
            canonicalUrl: res.canonical_url,
            domain: dom,
            reason:
              reason ||
              'Phát hiện không đọc đủ dữ liệu SP trên Hibox sau scrape — có thể hết hoặc trang lỗi.',
            checkedAtIso: iso,
          });
        }
        return next.slice(0, 220);
      });
    },
    [],
  );

  const runNextInternal = useCallback(async (): Promise<RunNextOutcome> => {
    setActiveCheck({ mode: 'db' });
    setRunning(true);
    setLastError(null);
    try {
        const seqSlot = dualAlternateFallback ? alternateSeqRef.current++ : 0;
        const res = await adminProductAPI.runSourceStockBatchNextFromDb({
          domain,
          activeOnly: true,
          cursorAfterProductId: 0,
          stickySeedProductId: stickySeedProductIdRef.current ?? undefined,
          dualAlternateFallback,
          alternateSequenceIndex: seqSlot,
        });

        if (res.done) {
          stickySeedProductIdRef.current = null;
          const ttl =
            typeof res.admin_batch_scan_cooldown_days === 'number'
              ? res.admin_batch_scan_cooldown_days
              : cooldownDays;
          if (typeof res.admin_batch_scan_cooldown_days === 'number') {
            setCooldownDays(res.admin_batch_scan_cooldown_days);
          }
          showToast(
            'info',
            res.detail ||
              `Không còn sản trong hàng chờ (có thể tất cả đang chờ TTL ${ttl} ngày hoặc hết SP khớp bộ lọc).`,
          );
          setAuto(false);
          setLastFinished({
            kind: 'queue_empty',
            finishedAtIso: new Date().toISOString(),
            detail: res.detail ?? null,
          });
          setRecent((prev) => [res, ...prev].slice(0, 36));
          return 'halt';
        }

        const tried = (res.seed_link_default || '').trim() || res.canonical_url || '';
        setDbCursorAfterId(res.cursor_after_product_id);
        setSessionChecks((n) => n + 1);
        if (typeof res.admin_batch_scan_cooldown_days === 'number') {
          setCooldownDays(res.admin_batch_scan_cooldown_days);
        }
        setRecent((prev) => [res, ...prev].slice(0, 36));
        bumpOosRows(res, tried);
        setLastFinished(buildLastOkFromApi(res, tried, domain));

        const shortUrl = tried.length > 86 ? `${tried.slice(0, 86)}…` : tried || '(thiếu link)';
        const seedShort =
          typeof res.seed_product_db_id === 'number' ? ` — DB id ${res.seed_product_db_id}` : '';
        const hint = typeof res.detail === 'string' && res.detail.trim() ? ` — ${res.detail.trim().slice(0, 200)}` : '';
        if (res.classified_out_of_stock) {
          stickySeedProductIdRef.current = null;
          if (res.updates_committed) {
            showToast(
              'info',
              `Hết hàng trên nguồn đã có dấu hiệu rõ — đã cập nhật tồn = 0 nếu khớp SP («${shortUrl}»${seedShort})`,
            );
          } else {
            showToast(
              'info',
              `Hết hàng trên nguồn (theo cờ trang); chưa khớp bản trong shop — không đổi DB («${shortUrl}»${seedShort})`,
            );
          }
        } else if (isDualPlatformHardFailure(res)) {
          stickySeedProductIdRef.current = null;
          setAuto(false);
          const full = (res.detail || '').trim() || 'Hibox và CSSBuy đều không đọc được — không đổi DB.';
          const toastSlice = full.length > 520 ? `${full.slice(0, 520)}…` : full;
          showToast(
            'err',
            `${toastSlice} Đã dừng lặp — xem đầy đủ trong «Lần kiểm tra gần nhất».`,
          );
        } else if (shouldStopAutoForAntiBot(res)) {
          stickySeedProductIdRef.current = null;
          setAuto(false);
          const full =
            (res.detail || '').trim() ||
            (isBlockedBySourceSite(res.raw_status)
              ? 'Trang nguồn báo chặn hoặc phát hiện quét.'
              : 'Phát hiện dấu hiệu captcha/chặn trong phản hồi — đã dừng lặp.');
          const toastSlice = full.length > 520 ? `${full.slice(0, 520)}…` : full;
          showToast(
            'err',
            `${toastSlice} Đã dừng lặp — xem đầy đủ trong ô «Lần kiểm tra gần nhất».`,
          );
        } else if (isUnresolvedStockProbe(res.raw_status)) {
          if (typeof res.seed_product_db_id === 'number' && res.seed_product_db_id > 0) {
            stickySeedProductIdRef.current = res.seed_product_db_id;
          }
          showToast(
            'info',
            `Chưa kiểm tra được nguồn (lỗi đọc / mạng…) — giữ SP này, sẽ chạy lại sau («${shortUrl}»${seedShort})${hint}`,
          );
        } else {
          stickySeedProductIdRef.current = null;
          showToast(
            'ok',
            `OK — nguồn đọc được, không xếp hết («${shortUrl}»${seedShort})`,
          );
        }
        return 'ok';
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setLastError(msg);
        setLastFinished({
          kind: 'error',
          finishedAtIso: new Date().toISOString(),
          message: msg,
        });
        showToast('err', `${msg} — giữ nguyên, xem báo lỗi phía trên và thử lại.`);
        return 'fail';
      } finally {
        setActiveCheck(null);
        setRunning(false);
        void refreshQueueStats();
      }
  }, [bumpOosRows, cooldownDays, domain, dualAlternateFallback, refreshQueueStats, showToast]);

  const runNextRef = useRef(runNextInternal);
  useEffect(() => {
    runNextRef.current = runNextInternal;
  }, [runNextInternal]);

  useEffect(() => {
    void refreshQueueStats();
  }, [refreshQueueStats]);

  useEffect(() => {
    void refreshActivityReport();
  }, [refreshActivityReport]);

  useEffect(() => {
    if (!auto) return;
    const id = window.setInterval(() => void refreshQueueStats(), 90_000);
    return () => window.clearInterval(id);
  }, [auto, refreshQueueStats]);

  useEffect(() => {
    if (!deleteDbModalOpen && reportOosDeleteConfirmIds == null) return;
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key !== 'Escape') return;
      if (deleteDbModalOpen && !bulkDeletingDb) setDeleteDbModalOpen(false);
      if (reportOosDeleteConfirmIds != null && !reportOosDeleting) setReportOosDeleteConfirmIds(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [deleteDbModalOpen, bulkDeletingDb, reportOosDeleteConfirmIds, reportOosDeleting]);

  useEffect(() => {
    if (!auto) return;

    const ctl = { cancelled: false, sleepTimer: null as number | null };

    const sleepRemain = (ms: number) =>
      new Promise<void>((resolve) => {
        if (ctl.cancelled || ms <= 0) {
          resolve();
          return;
        }
        ctl.sleepTimer = window.setTimeout(() => {
          ctl.sleepTimer = null;
          resolve();
        }, ms);
      });

    void (async () => {
      while (!ctl.cancelled && autoGateRef.current) {
        const startedAt = Date.now();
        const outcome = await runNextRef.current();
        if (ctl.cancelled || outcome === 'halt') break;
        if (!autoGateRef.current) break;
        const elapsed = Date.now() - startedAt;
        const remaining = Math.max(0, randomAdminSourceLoopGapMs() - elapsed);
        await sleepRemain(remaining);
      }
    })();

    return () => {
      ctl.cancelled = true;
      if (ctl.sleepTimer != null) window.clearTimeout(ctl.sleepTimer);
    };
  }, [auto]);

  const resetPointers = () => {
    stickySeedProductIdRef.current = null;
    setDbCursorAfterId(0);
    showToast(
      'ok',
      'Đã xóa id seed cục bộ trên tab (để ý chỉ báo hiển thị). Backend vẫn chọn SP theo độ ưu tiên toàn DB như trong chú thích.',
    );
    void refreshQueueStats();
  };

  const clearOosBrowserOnly = () => {
    setOosRows([]);
    showToast('ok', 'Đã ẩn danh sách trên tab này — không đổi dữ liệu trên máy chủ.');
  };

  const confirmDeleteOosProductsFromDb = async () => {
    if (!oosDistinctDbIds.length) {
      showToast('err', 'Không có hàng nào có DB id khớp sản trong shop để xóa.');
      return;
    }
    setBulkDeletingDb(true);
    setLastError(null);
    try {
      const res = await adminProductAPI.deleteSourceStockBatchProductsByDbIds(oosDistinctDbIds);
      const removed = new Set(res.deleted_db_ids ?? []);
      setOosRows((prev) => prev.filter((row) => !removed.has(row.id)));
      setDeleteDbModalOpen(false);
      let msg = `Đã xóa ${res.deleted_count ?? 0} sản khỏi DB.`;
      if ((res.not_found_db_ids ?? []).length) {
        msg += ` Không thấy id: ${res.not_found_db_ids!.join(', ')}.`;
      }
      showToast(res.deleted_count ? 'info' : 'err', msg);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setLastError(msg);
      showToast('err', msg);
    } finally {
      setBulkDeletingDb(false);
      void refreshQueueStats();
    }
  };

  const startAutoSequence = async () => {
    stickySeedProductIdRef.current = null;
    setDbCursorAfterId(0);
    setAuto(true);
    showToast(
      'info',
      'Đã bật lặp — chạy ngay một SP; các lần sau: chờ xong SP hiện tại rồi nghỉ thêm ngẫu nhiên ~46–60 giây giữa hai lần bắt đầu.',
    );
  };

  return (
    <div className="max-w-[88rem] mx-auto px-3 sm:px-5 py-5 pb-8">
      <header className="mb-5">
        <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
          <div className="min-w-0">
            <h1 className="text-xl sm:text-2xl font-bold text-gray-900 tracking-tight">Kiểm tra nguồn hàng</h1>
            <p className="text-xs sm:text-sm text-gray-600 mt-1 max-w-3xl">
              Mỗi lần <strong>một SP</strong>. Lặp: nghỉ ngẫu nhiên ~46–60s giữa hai lần <em>bắt đầu</em>. Ưu tiên SP có lượt
              xem PDP trong cửa sổ gần; lỗi tạm / captcha → giữ SP, không TTL.
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
            Đọc thêm — TTL batch, PDP traffic, chặn lặp, Hibox &amp; CSSBuy
          </summary>
          <div className="px-3 pb-3 pt-0 space-y-3 text-[13px] leading-relaxed text-gray-700 border-t border-gray-200">
            <p>
              Không cần nạp danh sách tay khi Theo DB + bật lặp (tab mở): luôn <strong>một SP một lần</strong>; chờ xong SP
              hiện tại rồi xếp lượt tiếp. Giữa hai lần <em>bắt đầu</em> có khoảng nghỉ ngẫu nhiên như phần đầu; nếu một SP xử lý lâu
              hơn khoảng đó, SP kế bắt đầu ngay sau khi xong. Khi phản hồi báo chặn / rủi ro (
              <code className="text-[11px] bg-white px-1 rounded border border-gray-200">blocked</code>
              hoặc dấu hiệu captcha trên UI), lặp <strong>tự dừng</strong>.{' '}
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
              <code className="text-[11px] bg-white px-1 rounded border border-gray-200">link_default</code> đủ dài.
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
            <p className="text-[11px] text-gray-500 max-w-[16rem] leading-snug">
              Một SP mỗi lần; ưu tiên PDP. Lặp: nghỉ ~46–60s giữa hai lần bắt đầu.
            </p>
          </div>
          <div className="flex flex-col gap-1 flex-1 min-w-[12rem] max-w-md">
            <label htmlFor="source-domain-select" className="text-xs font-medium text-gray-500">
              Nguồn đọc (batch)
            </label>
            <select
              id="source-domain-select"
              className="border border-gray-300 rounded-lg px-3 h-10 text-sm w-full"
              value={domain}
              onChange={(e) => setDomain(e.target.value as SourceStockDomain)}
              disabled={running}
            >
              <option value="hibox">hibox.mn — scrape</option>
              <option value="cssbuy">cssbuy.com — API /web/item</option>
            </select>
            <label className="mt-2 flex items-start gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                className="mt-0.5 h-4 w-4 rounded border-gray-300 accent-orange-700 disabled:opacity-45"
                checked={dualAlternateFallback}
                onChange={(ev) => setDualAlternateFallback(ev.target.checked)}
                disabled={running}
                aria-describedby="dual-alternate-hint"
              />
              <span id="dual-alternate-hint" className="text-[11px] text-gray-600 leading-snug">
                <strong className="text-gray-800">Sen kẽ + fallback 2 nền:</strong> mỗi lần chạy thử Hibox rồi CSSBuy
                theo thứ tự luân phiên; một nền lỗi thì đọc nền còn lại. Nếu <strong className="text-gray-800">cả hai
                lỗi</strong> → dừng lặp và xem chi tiết bên dưới. Khi tắt: chỉ một nền như ô «Nguồn đọc».
              </span>
            </label>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 py-2 border-y border-gray-100">
          <button
            type="button"
            onClick={() => void runNextInternal()}
            disabled={running}
            className="rounded-lg bg-orange-600 text-white px-4 py-2 text-sm font-semibold disabled:opacity-50 hover:bg-orange-700 shadow-sm"
          >
            {running ? 'Đang chạy…' : 'Chạy 1 SP'}
          </button>
          <button
            type="button"
            aria-pressed={auto}
            onClick={() => {
              if (auto) {
                setAuto(false);
                showToast('info', 'Đã dừng lặp.');
              } else {
                void startAutoSequence();
              }
            }}
            disabled={running && !auto}
            className={`rounded-lg px-4 py-2 text-sm font-semibold border-2 transition-colors shadow-sm ${
              auto
                ? 'border-emerald-600 bg-emerald-50 text-emerald-950 hover:bg-emerald-100 disabled:opacity-50'
                : 'border-slate-800 bg-slate-800 text-white hover:bg-slate-900 disabled:opacity-45'
            }`}
          >
            {auto ? 'Dừng lặp' : 'Bật lặp'}
          </button>
          <span className="hidden sm:inline w-px h-7 bg-gray-200 shrink-0" aria-hidden />
          <button
            type="button"
            onClick={resetPointers}
            disabled={running}
            title="Chỉ trên tab này"
            className="text-xs font-semibold text-gray-600 hover:text-gray-900 underline underline-offset-2 disabled:opacity-40"
          >
            Đặt lại chỉ báo
          </button>
          <button
            type="button"
            disabled={running || bulkDeletingDb || queueStatsLoading}
            className="text-xs font-semibold text-indigo-700 underline underline-offset-2 disabled:opacity-45"
            onClick={() => void refreshQueueStats()}
          >
            {queueStatsLoading ? 'Đang đếm queue…' : 'Làm mới queue'}
          </button>
          <button
            type="button"
            disabled={running || bulkDeletingDb || activityReportLoading}
            className="text-xs font-semibold text-indigo-700 underline underline-offset-2 disabled:opacity-45"
            onClick={() => void refreshActivityReport()}
          >
            {activityReportLoading ? 'Đang tải BC…' : 'Làm mới báo cáo 30 ngày'}
          </button>
        </div>

        <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-gray-800 bg-slate-50 border border-slate-100 rounded-lg px-3 py-2">
              <span>
                Seed <code className="text-[11px] bg-white px-1 rounded border">{dbCursorAfterId}</code>
              </span>
              <span className="text-gray-400" aria-hidden>
                ·
              </span>
              <span>TTL cổ điển {cooldownDays} ngày</span>
              {queueStats?.admin_batch_traffic_check_gap_days != null ? (
                <span className="text-gray-600">· PDP gap {queueStats.admin_batch_traffic_check_gap_days}d</span>
              ) : null}
              {queueStats?.admin_batch_traffic_view_window_days != null ? (
                <span className="text-gray-600">· PDP cửa sổ {queueStats.admin_batch_traffic_view_window_days}d</span>
              ) : null}
              <span className="text-gray-400" aria-hidden>
                ·
              </span>
              <span className="text-emerald-800">
                Phiên OK: <strong>{sessionChecks}</strong>
              </span>
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
                          <strong>Reload trang làm trống</strong>{' '}
                          <a
                            href="#oos-heading"
                            className="font-semibold text-indigo-800 underline underline-offset-2 whitespace-nowrap"
                          >
                            «Hết trên nguồn (phiên tab)»
                          </a>{' '}
                          — chỉ lưu tạm trên tab, <strong>không gửi máy chủ</strong>. Dữ liệu bền nằm ở bảng mẫu này
                          (đã có out_of_stock trong DB trong cửa sổ) và trong tab sản CRM.
                        </li>
                        <li>
                          <strong>Hàng chờ DB:</strong> kết quả scrape/API báo «hết nguồn», backend{' '}
                          <strong className="not-italic">luôn cập nhật cờ + mốc kiểm tra + tồn ≤ 0 trên đúng</strong>{' '}
                          <code className="text-[10px] bg-white px-0.5">products.id</code> của sản được lấy từ queue (neo),
                          kể khi không tìm thêm được bản ghi khác qua slug. Không map slug <em>ngoài</em> neo không bị coi là
                          «mất cờ»: tra cứu trong{' '}
                          <strong>Phản hồi hệ thống</strong> trường <code className="text-[10px] bg-white px-0.5">oos_commit_included_anchor_db_id</code>{' '}
                          (xuất hiện khi chỉ neo mới có mặt — lúc đó nên chỉnh <code className="text-[10px] bg-white px-0.5">link_default</code> /{' '}
                          <code className="text-[10px] bg-white px-0.5">product_id</code> để slug đồng bộ nhưng không bắt buộc để có dòng trong báo cáo).
                        </li>
                        <li>
                          Nếu vừa chạy xong có commit DB nhưng bảng này không đổi: bấm <strong>«Làm mới báo cáo 30 ngày»</strong>, kiểm
                          tra ô domain (hibox/cssbuy) và xem trong JSON <code className="text-[10px] bg-white px-0.5">classified_out_of_stock</code> /{' '}
                          <code className="text-[10px] bg-white px-0.5">updates_committed</code>.
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
            className={`flex flex-wrap items-center gap-2.5 rounded-lg border px-3 py-2.5 text-sm ${
              running
                ? 'border-amber-300 bg-amber-50 text-amber-950'
                : auto
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
                  : 'border-slate-200 bg-slate-50 text-slate-700'
            }`}
          >
            {running ? (
              <>
                <SpinnerIcon className="text-amber-700" />
                <div className="flex flex-col gap-1 min-w-0 flex-1">
                  <span className="font-semibold">Đang kiểm tra</span>
                  {activeCheck?.mode === 'db' ? (
                    <span className="text-amber-900/90">
                      Máy chủ đang chọn <strong>một SP kế trong hàng chờ</strong> và đọc{' '}
                      <strong>{domain === 'cssbuy' ? 'CSSBuy (API)' : 'Hibox (scrape)'}</strong>; URL trong DB chỉ hiện ở dưới sau khi xong lần này.
                    </span>
                  ) : (
                    <span className="text-amber-900/90">Đang gọi API scrape / cập nhật…</span>
                  )}
                  <span className="text-amber-800/85 text-xs leading-snug">
                    Một SP mỗi lần; lần kế chỉ sau khi xong + nghỉ ~46–60s khi lặp bật.
                  </span>
                </div>
              </>
            ) : auto ? (
              <>
                <span className="flex h-2 w-2 rounded-full bg-emerald-500 animate-pulse shrink-0" aria-hidden />
                <span className="font-semibold">Lặp đang bật</span>
                <span className="text-emerald-900/95 text-xs sm:text-sm leading-snug max-w-xl">
                  Nghỉ ~46–60s giữa hai lần bắt đầu. Dừng: nút «Dừng lặp» trên thanh thao tác.
                </span>
              </>
            ) : (
              <>
                <span className="h-2 w-2 rounded-full bg-slate-400 shrink-0" aria-hidden />
                <span className="font-semibold">Lặp đang tắt</span>
                <span className="text-sm text-gray-700">
                  Cam = một SP; nút đen/xanh lá = bật lặp tuần tự theo queue.
                </span>
              </>
            )}
          </div>

          {lastFinished ? (
            <div
              className="rounded-lg border border-indigo-200 bg-indigo-50/70 px-3 py-3 text-sm text-indigo-950 space-y-2"
              aria-live="polite"
            >
              <h3 className="font-semibold text-indigo-950 text-[13px] uppercase tracking-wide">
                Lần kiểm tra gần nhất
              </h3>
              {lastFinished.kind === 'queue_empty' ? (
                <p className="text-indigo-900/95">
                  <strong>Hết / không còn sản trong hàng chờ</strong>
                  {lastFinished.detail ? ` — ${lastFinished.detail}` : ''}.
                </p>
              ) : lastFinished.kind === 'error' ? (
                <div className="space-y-1">
                  <p className="font-medium text-red-900">Lỗi kiểm tra nguồn</p>
                  {lastFinished.attemptedUrl ? (
                    <p className="break-words">
                      <strong className="font-medium">Đang cố kiểm tra:</strong>{' '}
                      <ExternalHttpLink url={lastFinished.attemptedUrl} />
                    </p>
                  ) : null}
                  <p className="text-red-950/95 whitespace-pre-wrap">{lastFinished.message}</p>
                </div>
              ) : (
                <div className="space-y-2 text-[13px] leading-snug">
                  <p className="text-indigo-800/90">
                    Hoàn lúc{' '}
                    <time dateTime={lastFinished.finishedAtIso}>
                      {new Date(lastFinished.finishedAtIso).toLocaleString('vi-VN')}
                    </time>
                    {' · Hàng chờ DB'}
                  </p>
                  {lastFinished.seedProductDbId != null ? (
                    <p>
                      <strong>Sản trong shop:</strong> DB id{' '}
                      <code className="text-xs bg-white/80 px-1 rounded">{lastFinished.seedProductDbId}</code>
                      {lastFinished.seedProductName ? ` · ${lastFinished.seedProductName}` : ''}
                    </p>
                  ) : null}
                  <div>
                    <p className="font-medium mb-1">Link lấy trong DB / vừa thử scrape</p>
                    <div className="font-mono text-xs bg-white/60 rounded px-2 py-1 border border-indigo-100 break-all">
                      <ExternalHttpLink url={lastFinished.attemptedUrl} />
                    </div>
                  </div>
                  {lastFinished.canonicalUrl && lastFinished.canonicalUrl !== '—' ? (
                    <div>
                      <p className="font-medium mb-1">Canonical / URL sau scrape</p>
                      <div className="font-mono text-xs bg-white/60 rounded px-2 py-1 border border-indigo-100 break-all">
                        <ExternalHttpLink url={lastFinished.canonicalUrl} />
                      </div>
                    </div>
                  ) : null}
                  {!lastFinished.classifiedOutOfStock &&
                  isAntiBotUiHighlight(lastFinished.rawStatus, lastFinished.detail) ? (
                    <div className="rounded-md bg-red-50 border-2 border-red-400 px-3 py-2 text-red-950 space-y-2 mt-1">
                      <p className="font-semibold">
                        {isBlockedBySourceSite(lastFinished.rawStatus)
                          ? 'Nguồn chặn / phát hiện quét — đã dừng lặp hàng chờ'
                          : 'Phát hiện captcha/chặn trong phản hồi — đã dừng lặp hàng chờ'}
                      </p>
                      <p className="text-[12px] leading-relaxed whitespace-pre-wrap">{lastFinished.detail ?? '—'}</p>
                      <p className="text-[11px] text-red-900/90">
                        Kiểm tra lại URL trong DB / độ trễ Hibox / giảm tần suất lặp nếu cần; sau đó bấm «Chạy 1 SP» hoặc «Bật lặp».
                      </p>
                      <dl className="grid gap-2 text-[12px]">
                        <div>
                          <dt className="font-medium text-red-900/95">raw_status</dt>
                          <dd className="font-mono mt-0.5 break-all">{lastFinished.rawStatus ?? '—'}</dd>
                        </div>
                      </dl>
                    </div>
                  ) : !lastFinished.classifiedOutOfStock &&
                  isUnresolvedStockProbe(lastFinished.rawStatus) &&
                  !isAntiBotUiHighlight(lastFinished.rawStatus, lastFinished.detail) ? (
                    <div className="rounded-md bg-amber-50 border border-amber-300 px-3 py-2 text-amber-950 space-y-1.5 mt-1">
                      <p className="font-semibold">Chưa kiểm tra được nguồn</p>
                      <p className="text-amber-950/95 text-[12px]">
                        Lỗi đọc trang tạm, mạng hoặc scraper không khẳng định được tồn —{' '}
                        <strong>không coi là hết hàng</strong>, <strong>tồn kho shop không đổi</strong>; phiên sẽ giữ SP để thử lại.
                      </p>
                      <dl className="grid gap-2 text-[12px]">
                        <div>
                          <dt className="font-medium text-amber-900/95">raw_status</dt>
                          <dd className="font-mono mt-0.5 break-all">{lastFinished.rawStatus ?? '—'}</dd>
                        </div>
                        <div>
                          <dt className="font-medium text-amber-900/95">detail</dt>
                          <dd className="mt-0.5 whitespace-pre-wrap">{lastFinished.detail ?? '—'}</dd>
                        </div>
                        {lastFinished.warnings.length > 0 ? (
                          <div>
                            <dt className="font-medium text-amber-900/95">warnings</dt>
                            <dd className="break-words">{lastFinished.warnings.join(' · ')}</dd>
                          </div>
                        ) : null}
                      </dl>
                    </div>
                  ) : !lastFinished.classifiedOutOfStock ? (
                    <p className="text-emerald-900 font-semibold pt-1">
                      Kết quả: có tín hiệu trang đọc bình thường — <strong>không xếp hết</strong>.
                    </p>
                  ) : (
                    <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-red-950 space-y-1.5 mt-1">
                      <p className="font-semibold">Đã có dấu hiệu không đọc được SP trên Hibox (xếp hết khi có khớp DB)</p>
                      <p className="text-red-950/95 text-[12px]">
                        Chỉ khi scrape đọc được nội dung và gặp cờ «đã xuống kệ / hết». Không nhầm với chỉ báo khác.
                      </p>
                      <dl className="grid gap-2 text-[12px]">
                        <div>
                          <dt className="text-red-950/85 font-medium">raw_status</dt>
                          <dd className="font-mono text-red-950 mt-0.5 break-all">{lastFinished.rawStatus ?? '—'}</dd>
                        </div>
                        <div>
                          <dt className="text-red-950/85 font-medium">detail</dt>
                          <dd className="text-red-950 mt-0.5 whitespace-pre-wrap">{lastFinished.detail ?? '—'}</dd>
                        </div>
                        {lastFinished.warnings.length > 0 ? (
                          <div>
                            <dt className="text-red-950/85 font-medium">warnings</dt>
                            <dd className="text-red-950 mt-0.5 break-words">{lastFinished.warnings.join(' · ')}</dd>
                          </div>
                        ) : null}
                      </dl>
                    </div>
                  )}
                  {lastFinished.classifiedOutOfStock && lastFinished.updatesCommitted ? (
                    <p className="text-amber-900 text-[12px]">
                      Đã cập nhật cửa hàng (tồn = 0 / trạng thái phù hợp theo luồng admin) cho sản khớp.
                    </p>
                  ) : lastFinished.classifiedOutOfStock && !lastFinished.updatesCommitted ? (
                    <p className="text-amber-900 text-[12px]">
                      Chưa ghi đổi trên cửa hàng — thường do không khớp sản hoặc lỗi commit.
                    </p>
                  ) : null}
                </div>
              )}
            </div>
          ) : null}
        </div>
      </div>

      <section className="mt-8 scroll-mt-4" aria-labelledby="oos-heading">
        <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
          <div>
            <h2 id="oos-heading" className="text-base sm:text-lg font-semibold text-gray-900 tracking-tight">
              Hết trên nguồn <span className="font-normal text-red-800">(phiên tab)</span>
            </h2>
            <details className="mb-3 rounded-lg border border-gray-100 bg-gray-50/70 text-[13px] text-gray-700">
              <summary className="cursor-pointer px-3 py-2 font-medium text-gray-900 select-none [&::-webkit-details-marker]:hidden list-none flex items-center gap-2">
                <span className="text-gray-400 text-[10px]">▾</span>
                Danh sách phiên chỉ trong tab — không thay máy chủ
              </summary>
              <div className="px-3 pb-3 pt-0 border-t border-gray-100 space-y-2 leading-relaxed">
                <p>
                  Khi scrape báo cờ «hết», SP được ghép vào bảng bên dưới để bạn đối chiếu. «DB đã commit» chỉ có nghĩa đã
                  đổi tồn/trạng thái nguồn trên các bản ghi khớp — không tự xóa sản. Xóa vĩnh viễn cần bấm đỏ + xác nhận.
                </p>
                <p className="text-gray-600 text-xs">
                  Refresh tab làm trống danh sách phiên; không ảnh hưởng DB.
                </p>
              </div>
            </details>
          </div>
          <div className="flex flex-wrap gap-3 items-center shrink-0 justify-end">
            <button
              type="button"
              className="text-sm text-orange-700 font-medium underline disabled:opacity-50"
              onClick={clearOosBrowserOnly}
              disabled={oosRows.length === 0 || bulkDeletingDb}
            >
              Ẩn danh sách trong trình duyệt
            </button>
            <button
              type="button"
              className="text-sm rounded-lg border border-red-300 bg-red-50 px-3 py-1.5 font-semibold text-red-900 hover:bg-red-100 disabled:opacity-50"
              disabled={bulkDeletingDb || oosDistinctDbIds.length === 0}
              onClick={() => setDeleteDbModalOpen(true)}
              aria-expanded={deleteDbModalOpen}
            >
              Xóa sản khỏi DB cửa hàng…
            </button>
          </div>
        </div>
        <div className="rounded-xl border overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-100 text-gray-700">
              <tr>
                <th className="text-left px-3 py-2 font-medium whitespace-nowrap">Trên phiên tab</th>
                <th className="text-left px-3 py-2 font-medium">DB id</th>
                <th className="text-left px-3 py-2 font-medium">Mã</th>
                <th className="text-left px-3 py-2 font-medium">Tên</th>
                <th className="text-left px-3 py-2 font-medium">Domain</th>
                <th className="text-left px-3 py-2 font-medium">URL trong DB</th>
                <th className="text-left px-3 py-2 font-medium">Canonical / scrape</th>
                <th className="text-left px-3 py-2 font-medium">Ghi chú</th>
                <th className="text-left px-3 py-2 font-medium">Slug</th>
              </tr>
            </thead>
            <tbody>
              {oosRows.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-3 py-6 text-gray-500 text-center">
                    Chưa có SP nào bị đánh trong phiên làm việc này.
                  </td>
                </tr>
              ) : (
                oosRows.map((row) => (
                  <tr key={row.rowKey} className="border-t border-gray-200 align-top">
                    <td className="px-3 py-2 whitespace-nowrap align-top">
                      <button
                        type="button"
                        className="text-xs font-medium text-slate-600 underline hover:text-orange-900"
                        aria-label={`Xóa khỏi danh sách hết hàng (browser) DB id ${row.id > 0 ? row.id : '—'} `}
                        onClick={() =>
                          setOosRows((prev) => prev.filter((r) => r.rowKey !== row.rowKey))
                        }
                      >
                        Xóa dòng (tab)
                      </button>
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">{row.id > 0 ? row.id : '—'}</td>
                    <td className="px-3 py-2 font-mono text-xs max-w-[120px] break-all">{row.product_id ?? '—'}</td>
                    <td className="px-3 py-2 max-w-[200px]">{row.name}</td>
                    <td className="px-3 py-2 whitespace-nowrap">{row.domain}</td>
                    <td className="px-3 py-2 max-w-[200px]">
                      <ExternalHttpLink url={row.sourceUrl} />
                    </td>
                    <td className="px-3 py-2 max-w-[200px]">
                      <ExternalHttpLink url={row.canonicalUrl} />
                    </td>
                    <td className="px-3 py-2 text-xs max-w-[260px]" title={row.reason}>
                      {row.reason}
                    </td>
                    <td className="px-3 py-2 text-xs">
                      {row.slug ? (
                        <Link
                          className="text-orange-700 underline"
                          href={`/products/${row.slug}`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          /{row.slug}
                        </Link>
                      ) : (
                        '—'
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {deleteDbModalOpen ? (
        <div
          className="fixed inset-0 z-[120] flex items-center justify-center bg-black/45 p-4"
          role="presentation"
          onClick={() => {
            if (!bulkDeletingDb) setDeleteDbModalOpen(false);
          }}
        >
          <div
            className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 border border-gray-200"
            role="dialog"
            aria-modal="true"
            aria-labelledby="del-db-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 id="del-db-title" className="text-lg font-bold text-gray-900">
              Xóa vĩnh viễn khỏi CSDL cửa hàng?
            </h3>
            <p className="text-sm text-gray-700 mt-3 leading-relaxed">
              Đây là <strong>bước quyết định cuối của admin</strong>, tách khỏi việc chỉ cập nhật tồn khi kiểm tra nguồn.
              Sẽ gọi API xóa <strong>{oosDistinctDbIds.length}</strong> sản theo khóa{' '}
              <code className="text-xs bg-gray-100 px-1 rounded">products.id</code> đang có trong danh sách —
              không hoàn tác (kèm dọn asset Bunny như khi xóa sản ở admin). Hàng chỉ «không khớp SP» không có DB id vẫn không bị đụng đến.
            </p>
            <div className="flex flex-wrap gap-3 justify-end mt-6">
              <button
                type="button"
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50 disabled:opacity-50"
                disabled={bulkDeletingDb}
                onClick={() => setDeleteDbModalOpen(false)}
              >
                Hủy
              </button>
              <button
                type="button"
                className="rounded-lg bg-red-700 text-white px-4 py-2 text-sm font-semibold hover:bg-red-800 disabled:opacity-50"
                disabled={bulkDeletingDb}
                onClick={() => void confirmDeleteOosProductsFromDb()}
              >
                {bulkDeletingDb ? 'Đang xóa…' : 'Đồng ý — xóa'}
              </button>
            </div>
          </div>
        </div>
      ) : null}

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

      <section className="mt-10" aria-labelledby="recent-heading">
        <h2 id="recent-heading" className="text-lg font-semibold text-gray-900 mb-2">
          Phản hồi hệ thống (mới nhất)
        </h2>
        <div className="rounded-xl border border-gray-200 bg-white divide-y text-sm">
          {recent.length === 0 ? (
            <p className="p-4 text-gray-500">Chưa có phiên kiểm tra.</p>
          ) : (
            recent.map((r, idx) => {
              const dbr = r as AdminSourceStockBatchDbNextResult;
              const doneQueue = typeof dbr.done === 'boolean' && dbr.done;
              const blockedBySite =
                !doneQueue &&
                !r.classified_out_of_stock &&
                (isBlockedBySourceSite(r.raw_status) ||
                  (isUnresolvedStockProbe(r.raw_status) && detailLooksLikeCaptchaOrSiteBlock(r.detail)));
              const unresolvedProbe =
                !doneQueue &&
                !r.classified_out_of_stock &&
                isUnresolvedStockProbe(r.raw_status) &&
                !detailLooksLikeCaptchaOrSiteBlock(r.detail);
              const headline = doneQueue
                ? 'Hết danh sách DB trong bộ lọc'
                : r.classified_out_of_stock
                  ? 'Hết hàng trên nguồn (đã có cờ trang)'
                  : blockedBySite
                    ? 'Bị chặn / phát hiện quét — đã dừng lặp'
                  : unresolvedProbe
                    ? 'Chưa kiểm tra được (lỗi đọc tạm…)'
                    : 'Đọc OK — không xếp hết';
              const sub =
                typeof dbr.seed_product_db_id === 'number'
                  ? `SP hàng chờ #${dbr.seed_product_db_id} ${r.canonical_url || ''}`
                  : r.canonical_url || '';
              const summaryClass =
                doneQueue
                  ? 'text-gray-800'
                  : r.classified_out_of_stock
                    ? 'text-red-700'
                    : blockedBySite
                      ? 'text-red-800 font-semibold'
                    : unresolvedProbe
                      ? 'text-amber-900'
                      : 'text-emerald-800';
              return (
                <details key={`recent-${idx}-${sub}-${idx}`} className="p-4 group">
                  <summary className="cursor-pointer font-medium text-gray-900 list-none flex flex-wrap gap-2 items-baseline">
                    <span className={summaryClass}>{headline}</span>
                    <span className="text-gray-500 font-mono text-xs truncate max-w-xl">{sub}</span>
                    {r.updates_committed ? (
                      <span
                        className="text-xs bg-orange-50 text-orange-900 px-2 rounded border border-orange-100 cursor-help"
                        title="Đã ghi thay đổi tồn/trạng thái nguồn lên các SP khớp trong DB. Không xóa sản — xóa vĩnh viễn chỉ khi admin dùng «Xóa sản khỏi DB cửa hàng»."
                      >
                        DB đã commit
                      </span>
                    ) : null}
                  </summary>
                  <pre className="mt-3 text-xs bg-gray-50 p-3 rounded-lg overflow-auto max-h-48 whitespace-pre-wrap">
                    {JSON.stringify(r, null, 2)}
                  </pre>
                </details>
              );
            })
          )}
        </div>
      </section>
    </div>
  );
}
