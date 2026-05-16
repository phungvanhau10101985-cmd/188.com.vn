'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  adminProductAPI,
  type AdminSourceStockBatchDbNextResult,
  type AdminSourceStockBatchOneMatched,
  type AdminSourceStockBatchOneResult,
  type AdminSourceStockQueueStats,
} from '@/lib/admin-api';

type Domain = '1688' | 'hibox';

/** Theo DB + bật lặp: khoảng cách tối thiểu giữa hai lần *bắt đầu* kiểm tra (sequential — chờ xong SP hiện tại). */
const ADMIN_SOURCE_DB_LOOP_MIN_INTERVAL_MS = 60_000;

/** Kết quả một lần gọi run-next (phục vụ lặp tuần tự). */
type RunNextOutcome = 'ok' | 'halt' | 'fail';

type OosRow = AdminSourceStockBatchOneMatched & {
  rowKey: string;
  sourceUrl: string;
  canonicalUrl: string;
  domain: Domain;
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
      domain: Domain;
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
  domainUsed: Domain,
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

export default function AdminSourceStockCheckPage() {
  const [scanFromDb, setScanFromDb] = useState(true);
  const [domain, setDomain] = useState<Domain>('1688');
  const [auto, setAuto] = useState(true);
  const [running, setRunning] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: 'ok' | 'info' | 'err'; msg: string } | null>(null);

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

  /** Luôn khớp render hiện tại — async loop đọc sau `await` không bị stale như chỉ state. */
  const autoGateRef = useRef(auto);
  const scanFromDbGateRef = useRef(scanFromDb);
  autoGateRef.current = auto;
  scanFromDbGateRef.current = scanFromDb;

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
      const dom = res.domain as Domain;

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
              reason || 'Phát hiện hết/đình chỉ trên trang nguồn (theo dấu hiệu trang 1688) — không gồm captcha chỉ đăng nhập.',
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
        });

        if (res.done) {
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
        } else if (isUnresolvedStockProbe(res.raw_status)) {
          showToast(
            'info',
            `Chưa kiểm tra được nguồn (captcha, chặn, lỗi đọc trang…) — không coi là hết hàng («${shortUrl}»${seedShort})${hint}`,
          );
        } else {
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
      manualCursorRef.current = i + 1;
      setManualCursor(i + 1);
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
        const remaining = ADMIN_SOURCE_DB_LOOP_MIN_INTERVAL_MS - elapsed;
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
      setDbCursorAfterId(0);
    } else {
      manualCursorRef.current = 0;
      setManualCursor(0);
    }
    setAuto(true);
    showToast(
      'info',
      'Đã bật lặp — chạy ngay một SP; các lần sau: chờ xong SP hiện tại rồi nghỉ thêm để mỗi lần bắt đầu cách nhau ít nhất ~60 giây.',
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
            kiểm tra cách nhau <strong>tối thiểu ~60 giây</strong> (nếu một SP chạy lâu hơn 60 giây thì SP kế bắt đầu ngay sau khi xong). Backend đọc{' '}
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
            Cookie cho 1688:{' '}
            <Link href="/admin/import-1688" className="text-orange-700 font-medium underline">
              Cookie 1688
            </Link>
            . Hi-box ép link về <code className="text-xs bg-gray-100 px-1 rounded">hibox.mn/v/…</code> trước khi
            scrape.
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
              placeholder={'https://detail.1688.com/offer/…\nhttps://hibox.mn/v/…'}
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
              Tên miền để kiểm tra
            </label>
            <select
              id="source-domain-select"
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm min-w-[14rem]"
              value={domain}
              onChange={(e) => setDomain(e.target.value as Domain)}
              disabled={running}
            >
              <option value="1688">detail.1688.com (cookie)</option>
              <option value="hibox">hibox.mn (+ quy đổi)</option>
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
                        Máy chủ đang chọn <strong>một SP kế trong hàng chờ</strong> và đọc nguồn{' '}
                        <strong>{domain === '1688' ? '1688 (cookie)' : 'hibox'}</strong>; URL trong DB chỉ hiện ở dưới sau khi
                        xong lần này.
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
                        ? 'Đang xử lý một SP — chờ xong lần này; lần tiếp chỉ bắt đầu sau đó và cách lần bắt đầu trước ít nhất ~60 giây (nếu lặp vẫn bật).'
                        : 'Chờ phản hồi máy chủ.'}
                    </span>
                  </div>
                </>
              ) : scanFromDb && auto ? (
                <>
                  <span className="flex h-2 w-2 rounded-full bg-emerald-500 animate-pulse shrink-0" aria-hidden />
                  <span className="font-semibold">Lặp đang bật</span>
                  <span className="text-emerald-900/95">
                    Khi không «Đang kiểm tra»: đang nghỉ giữa hai SP (ít nhất ~60 giây kể từ lần bắt đầu trước). Muốn dừng: bấm{' '}
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
                  isUnresolvedStockProbe(lastFinished.rawStatus ?? undefined) ? (
                    <div className="rounded-md bg-amber-50 border border-amber-300 px-3 py-2 text-amber-950 space-y-1.5 mt-1">
                      <p className="font-semibold">Chưa kiểm tra được nguồn</p>
                      <p className="text-amber-950/95 text-[12px]">
                        Login/captcha, chặn bảo mật, lỗi mạng hoặc scraper không coi là &quot;hết hàng&quot; —{' '}
                        <strong>tồn kho trong shop không đổi</strong>.
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
                      <p className="font-semibold">Đã có dấu hiệu hết / đình chỉ trên trang nguồn (1688)</p>
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
                      Lặp tuần tự (~60 giây tối thiểu / lần)
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
              <span className="font-normal text-gray-600">(phiên làm việc; chỉ thêm sau khi trang báo có cờ hết 1688)</span>
            </h2>
            <p className="text-sm text-gray-600 mt-1 max-w-3xl">
              Captcha, đăng nhập hay lỗi đọc trang không nằm ở đây — xem ô <strong>Lần kiểm tra gần nhất</strong> (ô vàng «Chưa
              kiểm tra được»). Ẩn tab hoặc refresh thì danh sách này mất; không xóa sản trong DB shop trừ khi bạn bấm nút đỏ
              bên phải. Mỗi dòng có thể <strong>xóa khỏi danh sách</strong> bằng nút trong cột đầu bảng — chỉ là dọn ô nhớ
              của trình duyệt.
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
              Sẽ gọi API xóa <strong>{oosDistinctDbIds.length}</strong> sản theo khóa <code className="text-xs bg-gray-100 px-1 rounded">products.id</code> đang có trong danh sách —
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
              const unresolvedProbe =
                !doneQueue && !r.classified_out_of_stock && isUnresolvedStockProbe(r.raw_status);
              const headline = doneQueue
                ? 'Hết danh sách DB trong bộ lọc'
                : r.classified_out_of_stock
                  ? 'Hết hàng trên nguồn (đã có cờ trang)'
                  : unresolvedProbe
                    ? 'Chưa kiểm tra được (chặn / lỗi đọc / captcha…)'
                    : 'Đọc OK — không xếp hết';
              const sub =
                typeof dbr.seed_product_db_id === 'number'
                  ? `SP hàng chờ #${dbr.seed_product_db_id} ${r.canonical_url || ''}`
                  : r.canonical_url || '';
              const summaryClass =
                doneQueue ? 'text-gray-800' : r.classified_out_of_stock ? 'text-red-700' : unresolvedProbe ? 'text-amber-900' : 'text-emerald-800';
              return (
                <details key={`recent-${idx}-${sub}-${idx}`} className="p-4 group">
                  <summary className="cursor-pointer font-medium text-gray-900 list-none flex flex-wrap gap-2 items-baseline">
                    <span className={summaryClass}>{headline}</span>
                    <span className="text-gray-500 font-mono text-xs truncate max-w-xl">{sub}</span>
                    {r.updates_committed ? (
                      <span className="text-xs bg-orange-50 text-orange-900 px-2 rounded border border-orange-100">
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
