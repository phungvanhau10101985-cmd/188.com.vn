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

/** Trong lúc gọi API (tay: biết URL; DB: máy chủ chọn SP). */
type ActiveCheck = { mode: 'db' } | { mode: 'manual'; url: string };

type LastFinishedCheck =
  | {
      kind: 'ok';
      finishedAtIso: string;
      scanMode: 'db' | 'manual';
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
      scanMode: 'db' | 'manual';
      attemptedUrl?: string;
      message: string;
    };

function buildLastOkFromApi(
  res: AdminSourceStockBatchDbNextResult | AdminSourceStockBatchOneResult,
  scanMode: 'db' | 'manual',
  attemptedUrl: string,
  domainUsed: SourceStockDomain,
): Extract<LastFinishedCheck, { kind: 'ok' }> {
  const dbr = res as AdminSourceStockBatchDbNextResult;
  return {
    kind: 'ok',
    finishedAtIso: new Date().toISOString(),
    scanMode,
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

function parseUrls(raw: string): string[] {
  return raw
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean);
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

/** Bảng mẫu (tối đa `detail_limit` từ API) trong báo cáo 30 ngày. */
function SourceStockReportSampleTable({
  title,
  rows,
  emptyHint,
  defaultOpen,
}: {
  title: string;
  rows: AdminSourceStockActivityReportSampleRow[];
  emptyHint: string;
  defaultOpen: boolean;
}) {
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
      <div className="overflow-x-auto border-t border-slate-100">
        <table className="min-w-full text-xs">
          <thead className="bg-gray-100 text-gray-700">
            <tr>
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
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-2 py-4 text-gray-500 text-center">
                  {emptyHint}
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={`${title}-${row.id}`} className="border-t border-gray-200 align-top">
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
  const [scanFromDb, setScanFromDb] = useState(true);
  const [auto, setAuto] = useState(true);
  const [running, setRunning] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: 'ok' | 'info' | 'err'; msg: string } | null>(null);
  const [domain, setDomain] = useState<SourceStockDomain>('hibox');

  /** DB: cứ SAU id này thì query SP kế có link_default trong bộ lọc */
  const [dbCursorAfterId, setDbCursorAfterId] = useState(0);
  /** Dán tay: chỉ số trong textarea */
  const [manualCursor, setManualCursor] = useState(0);
  const [urlsText, setUrlsText] = useState('');
  const [showManualTextarea, setShowManualTextarea] = useState(false);
  const [loadingPreviewUrls, setLoadingPreviewUrls] = useState(false);

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
  const [activeCheck, setActiveCheck] = useState<ActiveCheck | null>(null);
  const [lastFinished, setLastFinished] = useState<LastFinishedCheck | null>(null);

  const urlsList = useMemo(() => parseUrls(urlsText), [urlsText]);

  /** Cột «DB id» trong bảng = `products.id` (để xóa thật trên máy chủ). */
  const oosDistinctDbIds = useMemo(() => {
    const s = new Set<number>();
    for (const row of oosRows) {
      if (typeof row.id === 'number' && row.id > 0) s.add(row.id);
    }
    return Array.from(s).sort((a, b) => a - b);
  }, [oosRows]);

  const manualCursorRef = useRef(0);
  /** Theo DB: giữ `products.id` khi lần trước lỗi tạm — backend + tab luôn retry đúng SP đó trước. */
  const stickySeedProductIdRef = useRef<number | null>(null);

  /** Luôn khớp render hiện tại — async loop đọc sau `await` không bị stale như chỉ state. */
  const autoGateRef = useRef(auto);
  const scanFromDbGateRef = useRef(scanFromDb);
  autoGateRef.current = auto;
  scanFromDbGateRef.current = scanFromDb;

  useEffect(() => {
    stickySeedProductIdRef.current = null;
  }, [domain]);

  useEffect(() => {
    if (!scanFromDb) stickySeedProductIdRef.current = null;
  }, [scanFromDb]);

  useEffect(() => {
    manualCursorRef.current = manualCursor;
  }, [manualCursor]);

  useEffect(() => {
    const n = urlsList.length;
    if (manualCursor > n) {
      manualCursorRef.current = n;
      setManualCursor(n);
    }
  }, [manualCursor, urlsList.length]);

  const showToast = useCallback((type: 'ok' | 'info' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 5200);
  }, []);

  const refreshQueueStats = useCallback(async () => {
    if (!scanFromDb) return;
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
  }, [scanFromDb, domain]);

  const refreshActivityReport = useCallback(async () => {
    if (!scanFromDb) return;
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
  }, [scanFromDb, domain]);

  const fillTextareaPreviewFromDb = useCallback(async () => {
    setLoadingPreviewUrls(true);
    setLastError(null);
    try {
      const res = await adminProductAPI.fetchSourceStockProductUrls({
        domain,
        limit: 5000,
        activeOnly: true,
      });
      setUrlsText(res.urls.join('\n'));
      manualCursorRef.current = 0;
      setManualCursor(0);
      setShowManualTextarea(true);
      showToast('ok', `Đã điền ${res.count} link xem trước vào ô bên dưới — không chạy queue.`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setLastError(msg);
      showToast('err', msg);
    } finally {
      setLoadingPreviewUrls(false);
    }
  }, [domain, showToast]);

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
    if (scanFromDb) {
      setActiveCheck({ mode: 'db' });
      setRunning(true);
      setLastError(null);
      try {
        const res = await adminProductAPI.runSourceStockBatchNextFromDb({
          domain,
          activeOnly: true,
          cursorAfterProductId: 0,
          stickySeedProductId: stickySeedProductIdRef.current ?? undefined,
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
        setLastFinished(buildLastOkFromApi(res, 'db', tried, domain));

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
          scanMode: 'db',
          message: msg,
        });
        showToast('err', `${msg} — giữ nguyên, xem báo lỗi phía trên và thử lại.`);
        return 'fail';
      } finally {
        setActiveCheck(null);
        setRunning(false);
        void refreshQueueStats();
      }
    }

    /* Chế độ dán tay */
    const q = parseUrls(urlsText);
    const i = manualCursorRef.current;

    if (!q.length) {
      showToast('err', 'Chưa có URL — điền mỗi dòng một link hoặc bật chế độ theo DB.');
      return 'fail';
    }
    if (i >= q.length) {
      showToast('info', 'Đã hết ô danh sách — đặt lại chỉ số tay hoặc dán thêm.');
      setAuto(false);
      return 'halt';
    }

    const url = q[i];
    setActiveCheck({ mode: 'manual', url });
    setRunning(true);
    setLastError(null);
    try {
      const res = await adminProductAPI.runSourceStockBatchOne({ url, domain });
      const blockedManual = shouldStopAutoForAntiBot(res);
      if (!blockedManual) {
        manualCursorRef.current = i + 1;
        setManualCursor(i + 1);
      }
      setSessionChecks((n) => n + 1);
      setRecent((prev) => [res, ...prev].slice(0, 36));
      bumpOosRows(res, url);
      setLastFinished(buildLastOkFromApi(res, 'manual', url, domain));

      const shortUrl = url.length > 86 ? `${url.slice(0, 86)}…` : url;
      const hint = typeof res.detail === 'string' && res.detail.trim() ? ` — ${res.detail.trim().slice(0, 200)}` : '';
      if (res.classified_out_of_stock) {
        if (res.updates_committed) {
          showToast('info', `Hết trên nguồn (có cờ): đặt hết và tồn = 0 nếu khớp («${shortUrl}»)`);
        } else {
          showToast(
            'info',
            `Hết trên nguồn (theo cờ) nhưng chưa thấy sản khớp trong shop — không đổi DB («${shortUrl}»)`,
          );
        }
      } else if (blockedManual) {
        const full =
          (res.detail || '').trim() ||
          (isBlockedBySourceSite(res.raw_status)
            ? 'Trang nguồn báo chặn hoặc phát hiện quét.'
            : 'Phát hiện dấu hiệu captcha/chặn trong phản hồi.');
        const toastSlice = full.length > 520 ? `${full.slice(0, 520)}…` : full;
        showToast('err', `${toastSlice} (giữ nguyên dòng URL trong ô để chỉnh link / thử lại).`);
      } else if (isUnresolvedStockProbe(res.raw_status)) {
        showToast('info', `Chưa kiểm tra được nguồn — không coi là hết hàng («${shortUrl}»)${hint}`);
      } else {
        showToast('ok', `OK — đọc nguồn được («${shortUrl}»)`);
      }
      return 'ok';
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setLastError(msg);
      setLastFinished({
        kind: 'error',
        finishedAtIso: new Date().toISOString(),
        scanMode: 'manual',
        attemptedUrl: url,
        message: msg,
      });
      showToast('err', `${msg} — giữ nguyên chỉ số, vui lòng thử lại.`);
      return 'fail';
    } finally {
      setActiveCheck(null);
      setRunning(false);
    }
  }, [
    bumpOosRows,
    cooldownDays,
    domain,
    refreshQueueStats,
    scanFromDb,
    showToast,
    urlsText,
  ]);

  const runNextRef = useRef(runNextInternal);
  useEffect(() => {
    runNextRef.current = runNextInternal;
  }, [runNextInternal]);

  useEffect(() => {
    if (!scanFromDb) {
      setQueueStats(null);
      return;
    }
    void refreshQueueStats();
  }, [scanFromDb, refreshQueueStats]);

  useEffect(() => {
    if (!scanFromDb) {
      setActivityReport(null);
      setActivityReportError(null);
      return;
    }
    void refreshActivityReport();
  }, [scanFromDb, refreshActivityReport]);

  useEffect(() => {
    if (!scanFromDb || !auto) return;
    const id = window.setInterval(() => void refreshQueueStats(), 90_000);
    return () => window.clearInterval(id);
  }, [scanFromDb, auto, refreshQueueStats]);

  useEffect(() => {
    if (!deleteDbModalOpen) return;
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape' && !bulkDeletingDb) setDeleteDbModalOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [deleteDbModalOpen, bulkDeletingDb]);

  useEffect(() => {
    if (!auto || !scanFromDb) return;

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
      while (!ctl.cancelled && autoGateRef.current && scanFromDbGateRef.current) {
        const startedAt = Date.now();
        const outcome = await runNextRef.current();
        if (ctl.cancelled || outcome === 'halt') break;
        if (!autoGateRef.current || !scanFromDbGateRef.current) break;
        const elapsed = Date.now() - startedAt;
        const remaining = Math.max(0, randomAdminSourceLoopGapMs() - elapsed);
        await sleepRemain(remaining);
      }
    })();

    return () => {
      ctl.cancelled = true;
      if (ctl.sleepTimer != null) window.clearTimeout(ctl.sleepTimer);
    };
  }, [auto, scanFromDb]);

  const resetPointers = () => {
    if (scanFromDb) {
      stickySeedProductIdRef.current = null;
      setDbCursorAfterId(0);
      showToast(
        'ok',
        'Đã xóa id seed cục bộ trên tab (để ý chỉ báo hiển thị). Backend vẫn chọn SP theo độ ưu tiên toàn DB như trong chú thích.'
      );
      void refreshQueueStats();
    } else {
      manualCursorRef.current = 0;
      setManualCursor(0);
      showToast('ok', 'Đã đặt chỉ số danh sách tay về dòng đầu.');
    }
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
      if (scanFromDb) void refreshQueueStats();
    }
  };

  const startAutoSequence = async () => {
    if (scanFromDb) {
      stickySeedProductIdRef.current = null;
      setDbCursorAfterId(0);
    } else {
      manualCursorRef.current = 0;
      setManualCursor(0);
    }
    setAuto(true);
    showToast(
      'info',
      'Đã bật lặp — chạy ngay một SP; các lần sau: chờ xong SP hiện tại rồi nghỉ thêm ngẫu nhiên ~46–60 giây giữa hai lần bắt đầu.',
    );
  };

  return (
    <div className="p-6 max-w-5xl pb-28">
      <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Kiểm tra nguồn hàng</h1>
          <p className="text-sm text-gray-600 mt-1">
            Mặc định không cần nạp danh sách; với chế độ Theo DB tab mở và <strong>đã bật lặp</strong>: luôn{' '}
            <strong>một SP một lần</strong> — chờ kiểm tra xong SP đó rồi mới xếp lượt tiếp; giữa hai lần <em>bắt đầu</em>{' '}
            kiểm tra cách nhau <strong>ngẫu nhiên ~46–60 giây</strong> giữa hai lần <em>bắt đầu</em> (nếu một SP chạy lâu hơn khoảng đó thì SP kế bắt đầu ngay sau khi xong).
            Khi phản hồi báo chặn / rủi ro (<code className="text-[11px] bg-gray-100 px-1 rounded">blocked</code>) hoặc heuristic tương tự trên UI, lặp <strong>tự dừng</strong>. Khi chỉ lỗi đọc tạm (<code className="text-[11px] bg-gray-100 px-1 rounded">error</code> /{' '}
            <code className="text-[11px] bg-gray-100 px-1 rounded">fetch_error</code>), hệ thống{' '}
            <strong>không đánh dấu TTL batch</strong> và <strong>giữ đúng SP đó</strong> cho tới khi đọc được trang hoặc có kết quả xác định khác.
            Backend đọc{' '}
            <strong>PDP traffic</strong> từ bảng{' '}
            <code className="text-[11px] bg-gray-100 px-1 rounded">user_product_views</code> /{' '}
            <code className="text-[11px] bg-gray-100 px-1 rounded">guest_product_views</code>: trong cửa sổ gần (ENV{' '}
            <code className="text-xs bg-gray-100 px-1 rounded">ADMIN_SOURCE_BATCH_TRAFFIC_VIEW_WINDOW_DAYS</code>) SP đó được{' '}
            <strong>xếp hàng chờ và được ưu tiên trong vòng luân phiên</strong>. Nếu SP traffic đã có mốc{' '}
            <code className="text-xs bg-gray-100 px-1 rounded">admin_source_batch_scanned_at</code> nhưng{' '}
            <strong>chưa qua đủ</strong> cửa sổ chờ ENV{' '}
            <code className="text-xs bg-gray-100 px-1 rounded">ADMIN_SOURCE_BATCH_TRAFFIC_CHECK_GAP_DAYS</code> →{' '}
            <strong>không xếp hàng kiểm tra</strong>. SP <strong>không</strong> có PDP traffic trong cửa sổ đó vẫn xếp theo TTL cổ điển{' '}
            <code className="text-xs bg-gray-100 px-1 rounded">ADMIN_SOURCE_BATCH_SCAN_COOLDOWN_DAYS</code> (= <strong>{cooldownDays}</strong> hiện
            báo trong API).

            Một lần chạy lấy <strong>một</strong>{' '}sản với đủ <code className="text-xs bg-gray-100 px-1 rounded">link_default</code>{' '}(
            Excel <code className="text-xs bg-gray-100 px-1 rounded">product_url</code>), sau đó ghi mốc và giữ chờ TTL tương ứng từng loại như trên.
          </p>
          <p className="text-sm text-gray-600 mt-2">
            <strong>Hibox:</strong> quy đổi sang <code className="text-xs bg-gray-100 px-1 rounded">hibox.mn/v/…</code> rồi scrape.
            {' '}
            <strong>CSSBuy:</strong> quy đổi sang{' '}
            <code className="text-xs bg-gray-100 px-1 rounded">item-1688-…</code> /{' '}
            <code className="text-xs bg-gray-100 px-1 rounded">item-….html</code> và đọc qua API{' '}
            <code className="text-xs bg-gray-100 px-1 rounded">POST /web/item</code> — không cần bấm «I accept the risks»
            (modal chỉ là UI; JSON đã có giá/title).
          </p>
        </div>
        {toast && (
          <div
            className={`rounded-lg border px-4 py-2 text-sm shrink-0 max-w-sm ${
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
        )}
      </div>

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

      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm space-y-4">
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium text-gray-800">Chế độ hàng chờ</legend>
          <div className="flex flex-wrap gap-4">
            <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
              <input
                type="radio"
                name="scan-mode"
                checked={scanFromDb}
                onChange={() => {
                  setScanFromDb(true);
                }}
                disabled={running}
              />
              <span>
                <strong>Theo DB</strong> — <strong>máy chủ chọn một SP mỗi lần</strong>: PDP traffic (guest + khách có tài khoản
                mới mở trang PDP) được <strong>ưu tiên trước</strong>; SP không PDP traffic chỉ chờ TTL thường. Trong từng
                nhánh thỏa điều kiện: chưa từng batch đi trước, tiếp theo là mốc batch càng cũ, cuối cùng là id tăng dần.
              </span>
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
              <input
                type="radio"
                name="scan-mode"
                checked={!scanFromDb}
                onChange={() => {
                  setScanFromDb(false);
                  setAuto(false);
                  setShowManualTextarea(true);
                }}
                disabled={running}
              />
              <span>
                <strong>Dán tay</strong> — mỗi dòng một URL trong ô bên dưới
              </span>
            </label>
          </div>
        </fieldset>

        {!scanFromDb && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <button
              type="button"
              className="text-sm font-medium text-indigo-700 underline"
              disabled={running || loadingPreviewUrls}
              onClick={() => void fillTextareaPreviewFromDb()}
            >
              {loadingPreviewUrls ? 'Đang lấy mẫu…' : 'Chỉ xem trước: đổ vào ô danh sách (không chạy kiểm tra)'}
            </button>
            <button
              type="button"
              className="text-sm text-gray-600 underline"
              onClick={() => setShowManualTextarea((s) => !s)}
            >
              {showManualTextarea ? 'Thu gọn ô danh sách' : 'Mở rộng ô danh sách'}
            </button>
          </div>
        )}

        {!scanFromDb && showManualTextarea && (
          <div>
            <label className="block text-sm font-medium text-gray-800 mb-2" htmlFor="source-url-batch">
              Danh sách URL (mỗi dòng một link)
            </label>
            <textarea
              id="source-url-batch"
              className="w-full min-h-[140px] border border-gray-300 rounded-lg p-3 text-sm font-mono"
              spellCheck={false}
              placeholder={
                'https://detail.1688.com/offer/…\nhttps://hibox.mn/v/…\nhttps://www.cssbuy.com/item-1688-….html'
              }
              value={urlsText}
              onChange={(e) => setUrlsText(e.target.value)}
              disabled={running}
            />
            <p className="text-xs text-gray-500 mt-1">
              Tay: dòng đang chỉ {manualCursor}/{urlsList.length}
            </p>
          </div>
        )}

        <div className="flex flex-wrap items-start gap-4 pt-2 border-t border-gray-100">
          <div>
            <label htmlFor="source-domain-select" className="block text-sm font-medium text-gray-800 mb-1">
              Nguồn kiểm tra
            </label>
            <select
              id="source-domain-select"
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm min-w-[16rem]"
              value={domain}
              onChange={(e) => setDomain(e.target.value as SourceStockDomain)}
              disabled={running}
            >
              <option value="hibox">hibox.mn — scrape sau quy đổi</option>
              <option value="cssbuy">cssbuy.com — API /web/item (Taobao item-… / 1688 item-1688-…)</option>
            </select>
          </div>
          {scanFromDb ? (
            <div className="text-sm text-gray-600 pb-1 flex-1 min-w-[14rem] space-y-1.5">
              <div>
                <strong>Vừa xử lý (id báo trong phiên tab):</strong>{' '}
                <code className="text-xs bg-gray-100 px-1 rounded">products.id</code> seed ={' '}
                <strong>{dbCursorAfterId}</strong>
                {' · '}
                <span className="text-gray-500">
                  TTL thường <strong>{cooldownDays}</strong> ngày
                  {queueStats?.admin_batch_traffic_check_gap_days != null ? (
                    <>
                      {' '}
                      — PDP chờ-gap <strong>{queueStats.admin_batch_traffic_check_gap_days}</strong> ngày
                    </>
                  ) : null}
                  {queueStats?.admin_batch_traffic_view_window_days != null ? (
                    <>
                      {' '}
                      — cửa sổ PDP <strong>{queueStats.admin_batch_traffic_view_window_days}</strong> ngày
                    </>
                  ) : null}
                  {' — '}
                  phiên đã kiểm tra thành công: <strong>{sessionChecks}</strong> lần
                </span>
              </div>
              {queueStatsLoading && !queueStats ? (
                <p className="text-xs text-gray-500">Đang đếm hàng chờ trên DB…</p>
              ) : queueStats ? (
                <div className="text-xs text-gray-800 leading-snug rounded-lg bg-slate-50 border border-slate-100 px-3 py-2">
                  <strong className="block text-[11px] uppercase tracking-wide text-slate-500 mb-1">Tiến độ trong DB</strong>
                  Tổng phạm vi (link đủ dài + lọc miền + chỉ sản đang hoạt động{' '}
                  <code className="text-[10px] bg-white px-0.5 rounded">is_active</code>):{' '}
                  <strong>{queueStats.total_in_scope.toLocaleString('vi-VN')}</strong> SP
                  {' — '}
                  <span className="text-emerald-900 whitespace-nowrap">
                    đến lượt ngay:{' '}
                    <strong>{queueStats.eligible_now.toLocaleString('vi-VN')}</strong>
                    （chưa từng batch:{' '}
                    <strong>
                      {(queueStats.eligible_never_scanned ?? 0).toLocaleString('vi-VN')}
                    </strong>
                    ; đã TTL:{' '}
                    <strong>
                      {(queueStats.eligible_rescan_after_ttl ?? 0).toLocaleString('vi-VN')}
                    </strong>）
                  </span>
                  <span className="block text-violet-950/95 mt-1.5">
                    Trong <strong>{queueStats.eligible_now.toLocaleString('vi-VN')}</strong> SP đến lượt — nhánh PDP traffic
                    (cửa sổ <strong>{queueStats.admin_batch_traffic_view_window_days ?? '?'}</strong> ngày):{' '}
                    <strong>
                      {(queueStats.eligible_with_recent_customer_view ?? 0).toLocaleString('vi-VN')}
                    </strong>
                    ; không PDP traffic chỉ chờ TTL thường:{' '}
                    <strong>
                      {(queueStats.eligible_without_recent_customer_view ?? 0).toLocaleString('vi-VN')}
                    </strong>
                  </span>
                  <span className="text-amber-900 whitespace-nowrap mt-1.5 inline-block md:inline">
                    đang chờ TTL (chưa tới vòng tiếp):{' '}
                    <strong>{queueStats.in_cooldown.toLocaleString('vi-VN')}</strong>
                    <abbr
                      title="Gồm SP traffic vừa batch chưa qua ADMIN_SOURCE_BATCH_TRAFFIC_CHECK_GAP_DAYS và SP không traffic vừa batch nhưng chưa qua ADMIN_SOURCE_BATCH_SCAN_COOLDOWN_DAYS"
                      className="no-underline cursor-help mx-1"
                    >
                      ({queueStats.admin_batch_scan_cooldown_days} ngày)
                    </abbr>
                  </span>
                  <span className="text-slate-500"> · </span>
                  <button
                    type="button"
                    disabled={running || bulkDeletingDb || queueStatsLoading}
                    className="text-indigo-700 font-medium underline disabled:opacity-50"
                    onClick={() => void refreshQueueStats()}
                  >
                    Làm mới số đếm
                  </button>
                  <span className="block text-[11px] text-slate-500 mt-1">
                    Đếm COUNT trên DB. Ưu tiên chọn: nhánh PDP traffic (cửa sổ xem) trước; trong nhánh không traffic vẫn theo TTL
                    thường. Tie-break trong mỗi nhóm:{' '}
                    <code className="text-[10px] bg-white px-0.5 rounded">admin_source_batch_scanned_at</code> chưa có → đi
                    trước, có thì ai càng cũ càng được lấy, cuối cùng là <code className="text-[10px] bg-white px-0.5 rounded">products.id</code>.
                  </span>
                </div>
              ) : (
                <p className="text-xs text-gray-500">Không đọc được số đếm — bấm «Làm mới số đếm» hoặc tải lại trang.</p>
              )}
              <div
                className={`rounded-lg border px-3 py-2 mt-2 ${
                  activityReportError ? 'border-red-200 bg-red-50/70' : 'border-indigo-100 bg-indigo-50/35'
                }`}
                aria-labelledby="source-stock-report-heading"
              >
                <div className="flex flex-wrap items-start justify-between gap-2 mb-1">
                  <strong
                    id="source-stock-report-heading"
                    className="text-[11px] uppercase tracking-wide text-indigo-900"
                  >
                    Báo cáo chi tiết (cửa sổ {activityReport?.window_days ?? 30} ngày, UTC)
                  </strong>
                  <button
                    type="button"
                    disabled={running || bulkDeletingDb || activityReportLoading}
                    className="text-[11px] font-semibold text-indigo-800 underline disabled:opacity-50"
                    onClick={() => void refreshActivityReport()}
                  >
                    {activityReportLoading ? 'Đang tải…' : 'Làm mới báo cáo'}
                  </button>
                </div>
                <p className="text-[11px] text-slate-600 mb-2 leading-snug">
                  Cùng phạm vi link +{' '}
                  <code className="text-[10px] bg-white/80 px-0.5 rounded">is_active</code> như hàng chờ. «Đã TTL batch»
                  = có{' '}
                  <code className="text-[10px] bg-white/80 px-0.5 rounded">admin_source_batch_scanned_at</code> trong cửa sổ.
                  «Đã có kiểm tra nguồn» = có{' '}
                  <code className="text-[10px] bg-white/80 px-0.5 rounded">source_stock_checked_at</code> (worker PDP hoặc
                  batch khi commit). «Hết / còn» trong cửa sổ dựa trên{' '}
                  <code className="text-[10px] bg-white/80 px-0.5 rounded">source_stock_status</code> và cột tồn khi có
                  kiểm tra.
                </p>
                {activityReportError ? (
                  <div
                    role="alert"
                    className="rounded border border-red-200 bg-white px-2 py-1.5 text-xs text-red-900 mb-2"
                  >
                    {activityReportError}{' '}
                    <button
                      type="button"
                      className="underline font-medium"
                      onClick={() => void refreshActivityReport()}
                    >
                      Thử lại
                    </button>
                  </div>
                ) : null}
                {activityReportLoading && !activityReport ? (
                  <p className="text-xs text-indigo-900/80">Đang lấy báo cáo từ máy chủ…</p>
                ) : null}
                {activityReport ? (
                  <>
                    <p className="text-[11px] text-slate-600 mb-2">
                      Bắt đầu cửa sổ (UTC):{' '}
                      <code className="text-[10px] bg-white/90 px-1 rounded">
                        {activityReport.window_since_utc_iso}
                      </code>
                      {' · '}
                      Mẫu tối đa mỗi bảng: <strong>{activityReport.detail_limit_applied}</strong>
                    </p>
                    <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-2 text-[11px] text-gray-900 mb-2">
                      <div className="rounded bg-white/70 border border-white px-2 py-1.5">
                        <dt className="text-slate-500 font-medium">Đến lượt kiểm tra ngay</dt>
                        <dd className="text-base font-semibold text-emerald-900">
                          {activityReport.queue.eligible_now.toLocaleString('vi-VN')}
                        </dd>
                      </div>
                      <div className="rounded bg-white/70 border border-white px-2 py-1.5">
                        <dt className="text-slate-500 font-medium">Đã TTL batch trong cửa sổ</dt>
                        <dd className="text-base font-semibold">
                          {activityReport.counts.batch_ttl_stamped_in_window.toLocaleString('vi-VN')}
                        </dd>
                      </div>
                      <div className="rounded bg-white/70 border border-white px-2 py-1.5">
                        <dt className="text-slate-500 font-medium">Đã có kiểm tra nguồn (checked_at)</dt>
                        <dd className="text-base font-semibold">
                          {activityReport.counts.source_stock_checked_any_in_window.toLocaleString('vi-VN')}
                        </dd>
                      </div>
                      <div className="rounded bg-white/70 border border-white px-2 py-1.5">
                        <dt className="text-slate-500 font-medium">Cờ out_of_stock trong cửa sổ</dt>
                        <dd className="text-base font-semibold text-red-900">
                          {activityReport.counts.source_stock_oos_signal_in_window.toLocaleString('vi-VN')}
                        </dd>
                      </div>
                      <div className="rounded bg-white/70 border border-white px-2 py-1.5">
                        <dt className="text-slate-500 font-medium">Cờ in_stock trong cửa sổ</dt>
                        <dd className="text-base font-semibold text-teal-900">
                          {activityReport.counts.source_stock_in_stock_signal_in_window.toLocaleString('vi-VN')}
                        </dd>
                      </div>
                      <div className="rounded bg-white/70 border border-white px-2 py-1.5">
                        <dt className="text-slate-500 font-medium">Sau kiểm tra: tồn &gt; 0</dt>
                        <dd className="text-base font-semibold">
                          {activityReport.counts.checked_available_positive_in_window.toLocaleString('vi-VN')}
                        </dd>
                      </div>
                      <div className="rounded bg-white/70 border border-white px-2 py-1.5">
                        <dt className="text-slate-500 font-medium">Sau kiểm tra: tồn ≤ 0</dt>
                        <dd className="text-base font-semibold">
                          {activityReport.counts.checked_available_zero_or_negative_in_window.toLocaleString('vi-VN')}
                        </dd>
                      </div>
                    </dl>
                    <div className="text-[11px] text-slate-700 mb-1">
                      <strong className="text-slate-600">Phân rã trạng thái</strong> (trong các SP có{' '}
                      <code className="text-[10px] bg-white px-0.5 rounded">source_stock_checked_at</code> trong cửa sổ):
                    </div>
                    <ul className="flex flex-wrap gap-2 text-[11px] mb-2">
                      {Object.entries(activityReport.checked_in_window_by_source_stock_status)
                        .sort((a, b) => b[1] - a[1])
                        .map(([k, v]) => (
                          <li
                            key={k}
                            className="rounded-full bg-white/90 border border-slate-200 px-2 py-0.5 font-mono text-[10px]"
                          >
                            {k}: <strong>{v.toLocaleString('vi-VN')}</strong>
                          </li>
                        ))}
                      {Object.keys(activityReport.checked_in_window_by_source_stock_status).length === 0 ? (
                        <li className="text-slate-500">Không có SP nào có checked_at trong cửa sổ.</li>
                      ) : null}
                    </ul>
                    <SourceStockReportSampleTable
                      title="Mẫu: cờ hết hàng (out_of_stock) trong cửa sổ"
                      rows={activityReport.samples.oos}
                      emptyHint="Không có dòng trong phạm vi."
                      defaultOpen
                    />
                    <SourceStockReportSampleTable
                      title="Mẫu: cờ còn hàng (in_stock) trong cửa sổ"
                      rows={activityReport.samples.in_stock}
                      emptyHint="Không có dòng trong phạm vi."
                      defaultOpen={false}
                    />
                    <SourceStockReportSampleTable
                      title="Mẫu: đã đánh TTL batch gần nhất trong cửa sổ"
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
          ) : null}
        </div>

        <div className="space-y-3 pt-4 border-t border-gray-100">
          {(running || scanFromDb) && (
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
                    {activeCheck?.mode === 'manual' ? (
                      <span className="text-amber-900/95 break-words">
                        <strong className="font-medium">Link trong danh sách tay:</strong>{' '}
                        <ExternalHttpLink url={activeCheck.url} />
                      </span>
                    ) : scanFromDb && activeCheck?.mode === 'db' ? (
                      <span className="text-amber-900/90">
                        Máy chủ đang chọn <strong>một SP kế trong hàng chờ</strong> và đọc{' '}
                        <strong>{domain === 'cssbuy' ? 'CSSBuy (API)' : 'Hibox (scrape)'}</strong>; URL trong DB chỉ hiện ở dưới sau khi xong lần này.
                      </span>
                    ) : (
                      <span className="text-amber-900/90">
                        {scanFromDb
                          ? 'Đang gọi API scrape / cập nhật…'
                          : 'Đang gọi API cho link tay…'}
                      </span>
                    )}
                    <span className="text-amber-800/85 text-[13px]">
                      {scanFromDb
                        ? 'Đang xử lý một SP — chờ xong lần này; lần tiếp chỉ bắt đầu sau đó và sau khoảng nghỉ ngẫu nhiên ~46–60 giây kể từ lần bắt đầu trước (nếu lặp vẫn bật).'
                        : 'Chờ phản hồi máy chủ.'}
                    </span>
                  </div>
                </>
              ) : scanFromDb && auto ? (
                <>
                  <span className="flex h-2 w-2 rounded-full bg-emerald-500 animate-pulse shrink-0" aria-hidden />
                  <span className="font-semibold">Lặp đang bật</span>
                  <span className="text-emerald-900/95">
                    Khi không «Đang kiểm tra»: đang nghỉ giữa hai SP (ngẫu nhiên ~46–60 giây kể từ lần bắt đầu trước). Muốn dừng: bấm{' '}
                    <strong>Bật lặp</strong> (lúc đang bật sẽ hiện «Đang lặp · bấm dừng»).
                  </span>
                </>
              ) : scanFromDb ? (
                <>
                  <span className="h-2 w-2 rounded-full bg-slate-400 shrink-0" aria-hidden />
                  <span className="font-semibold">Lặp đang tắt</span>
                  <span>
                    Trong khối «Kiểm tra nguồn»: nút đậm kế nút cam là <strong>Bật lặp</strong>. Nút cam chỉ chạy đúng một lần.
                  </span>
                </>
              ) : null}
            </div>
          )}

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
                  <p className="font-medium text-red-900">Lỗi ({lastFinished.scanMode === 'db' ? 'Theo DB' : 'Danh sách tay'})</p>
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
                    {lastFinished.scanMode === 'db' ? ' · Theo DB' : ' · Tay'}
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

          <div className="space-y-3 pt-4 border-t border-gray-100">
            <h3 className="text-sm font-semibold text-gray-900">Kiểm tra nguồn</h3>
            <div className="rounded-xl border border-gray-200 bg-slate-50/90 p-4 space-y-3">
              <div className="flex flex-wrap items-end gap-4">
                <div className="flex flex-col gap-1">
                  <span id="ctrl-once-label" className="text-[11px] font-medium text-gray-500">
                    Một vòng tay (API một lần)
                  </span>
                  <button
                    type="button"
                    aria-labelledby="ctrl-once-label"
                    onClick={() => void runNextInternal()}
                    disabled={running}
                    className="rounded-lg bg-orange-600 text-white px-4 py-2.5 text-sm font-semibold disabled:opacity-50 hover:bg-orange-700 shadow-sm"
                  >
                    {running
                      ? 'Đang chạy…'
                      : scanFromDb
                        ? 'Chạy 1 SP'
                        : 'Chạy 1 link tay'}
                  </button>
                </div>
                {scanFromDb ? (
                  <div className="flex flex-col gap-1">
                    <span id="ctrl-loop-label" className="text-[11px] font-medium text-gray-500">
                      Lặp tuần tự (~46–60 giây ngẫu nhiên / lần)
                    </span>
                    <button
                      type="button"
                      aria-labelledby="ctrl-loop-label"
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
                      className={`rounded-lg px-4 py-2.5 text-sm font-semibold border-2 transition-colors shadow-sm ${
                        auto
                          ? 'border-emerald-600 bg-emerald-50 text-emerald-950 hover:bg-emerald-100 disabled:opacity-50'
                          : 'border-slate-800 bg-slate-800 text-white hover:bg-slate-900 disabled:opacity-45'
                      }`}
                    >
                      {auto ? 'Đang lặp · bấm dừng' : 'Bật lặp'}
                    </button>
                  </div>
                ) : (
                  <p className="text-xs text-gray-600 max-w-[17rem] pb-1 leading-snug">
                    Chế độ <strong>dán tay</strong>: chỉ dùng nút cam. Để <strong>bật lặp</strong>, chọn radio{' '}
                    <strong>Theo DB</strong> phía trên.
                  </p>
                )}
              </div>
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 pt-2 border-t border-gray-200/90">
                <button
                  type="button"
                  onClick={resetPointers}
                  disabled={running}
                  title="Đặt lại chỉ báo cục bộ — không ép thứ tự queue trên server"
                  className="text-xs font-semibold text-gray-600 underline hover:text-gray-900 disabled:opacity-40"
                >
                  Đặt lại chỉ báo / đầu danh sách tay
                </button>
                <span className="text-[11px] text-gray-400 hidden sm:inline" aria-hidden>
                  ·
                </span>
                <p className="text-[11px] text-gray-500 leading-snug">
                  Hai nút to: cam = một lần API; kế bên = bật/tắt lặp (chỉ khi Theo DB). Dòng gạch chân chỉ đặt lại chỉ
                  báo trên tab — <strong>không</strong> gọi scrape.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <section className="mt-10" aria-labelledby="oos-heading">
        <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
          <div>
            <h2 id="oos-heading" className="text-lg font-semibold text-gray-900">
              Danh sách <span className="text-red-800">hết hàng trên nguồn</span>{' '}
              <span className="font-normal text-gray-600">(phiên làm việc; chỉ thêm khi scrape báo không đủ dữ liệu / xếp hết)</span>
            </h2>
            <p className="text-sm text-gray-600 mt-1 max-w-3xl">
              Khi kiểm tra thấy cờ «hết» trên nguồn, SP được <strong>ghi vào danh sách phiên</strong> để admin{' '}
              <strong>đánh dấu và quyết định cuối</strong> (có giữ trên cửa hàng hay không).{' '}
              Trong «Phản hồi hệ thống», badge «DB đã commit» nghĩa là đã{' '}
              <strong>cập nhật tồn/trạng thái nguồn</strong> cho các bản ghi khớp trong DB —{' '}
              <strong>không phải</strong> đã xóa sản khỏi CSDL.{' '}
              <strong>Xóa vĩnh viễn</strong> chỉ sau khi bạn bấm nút đỏ «Xóa sản khỏi DB cửa hàng» và xác nhận; đó là{' '}
              <strong>quyền quyết định cuối của admin</strong>. Captcha / lỗi đọc không vào đây — xem «Lần kiểm tra gần nhất».
              Ẩn tab hoặc refresh làm mất danh sách phiên; «Xóa dòng (tab)» chỉ gỡ khỏi trình duyệt.
            </p>
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
