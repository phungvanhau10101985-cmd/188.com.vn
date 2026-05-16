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

type OosRow = AdminSourceStockBatchOneMatched & {
  sourceUrl: string;
  canonicalUrl: string;
  domain: Domain;
  reason: string;
  checkedAtIso: string;
};

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
  const [includeInactiveProducts, setIncludeInactiveProducts] = useState(false);
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

  const urlsList = useMemo(() => parseUrls(urlsText), [urlsText]);

  /** Cột «DB id» trong bảng = `products.id` (để xóa thật trên máy chủ). */
  const oosDistinctDbIds = useMemo(() => {
    const s = new Set<number>();
    for (const row of oosRows) {
      if (typeof row.id === 'number' && row.id > 0) s.add(row.id);
    }
    return Array.from(s).sort((a, b) => a - b);
  }, [oosRows]);

  const runningRef = useRef(false);
  const manualCursorRef = useRef(0);

  useEffect(() => {
    runningRef.current = running;
  }, [running]);

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
        activeOnly: !includeInactiveProducts,
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
  }, [scanFromDb, domain, includeInactiveProducts]);

  const fillTextareaPreviewFromDb = useCallback(async () => {
    setLoadingPreviewUrls(true);
    setLastError(null);
    try {
      const res = await adminProductAPI.fetchSourceStockProductUrls({
        domain,
        limit: 5000,
        activeOnly: !includeInactiveProducts,
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
  }, [domain, includeInactiveProducts, showToast]);

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
            ...m,
            sourceUrl: attemptedUrl,
            canonicalUrl: res.canonical_url,
            domain: dom,
            reason: reason || 'Không đọc được nguồn hoặc hết — coi như hết hàng.',
            checkedAtIso: iso,
          });
        }
        return next.slice(0, 220);
      });
    },
    [],
  );

  const runNextInternal = useCallback(async (): Promise<boolean> => {
    if (scanFromDb) {
      setRunning(true);
      setLastError(null);
      try {
        const res = await adminProductAPI.runSourceStockBatchNextFromDb({
          domain,
          activeOnly: !includeInactiveProducts,
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
          setRecent((prev) => [res, ...prev].slice(0, 36));
          return false;
        }

        const tried = (res.seed_link_default || '').trim() || res.canonical_url || '';
        setDbCursorAfterId(res.cursor_after_product_id);
        setSessionChecks((n) => n + 1);
        if (typeof res.admin_batch_scan_cooldown_days === 'number') {
          setCooldownDays(res.admin_batch_scan_cooldown_days);
        }
        setRecent((prev) => [res, ...prev].slice(0, 36));
        bumpOosRows(res, tried);

        const shortUrl = tried.length > 86 ? `${tried.slice(0, 86)}…` : tried || '(thiếu link)';
        const seedShort =
          typeof res.seed_product_db_id === 'number' ? ` — DB id ${res.seed_product_db_id}` : '';
        if (!res.classified_out_of_stock) {
          showToast('ok', `OK${seedShort}: đọc nguồn được («${shortUrl}»)`);
        } else if (res.updates_committed) {
          showToast('info', `Hết/không đọc được${seedShort}: đã cập nhật tồn = 0 nếu khớp SP («${shortUrl}»)`);
        } else {
          showToast('info', `Hết/không đọc được${seedShort}, chưa khớp bản trong shop («${shortUrl}»)`);
        }
        return true;
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setLastError(msg);
        showToast('err', `${msg} — giữ nguyên, xem báo lỗi phía trên và thử lại.`);
        return false;
      } finally {
        setRunning(false);
        void refreshQueueStats();
      }
    }

    /* Chế độ dán tay */
    const q = parseUrls(urlsText);
    const i = manualCursorRef.current;

    if (!q.length) {
      showToast('err', 'Chưa có URL — điền mỗi dòng một link hoặc bật chế độ theo DB.');
      return false;
    }
    if (i >= q.length) {
      showToast('info', 'Đã hết ô danh sách — đặt lại chỉ số tay hoặc dán thêm.');
      setAuto(false);
      return false;
    }

    const url = q[i];
    setRunning(true);
    setLastError(null);
    try {
      const res = await adminProductAPI.runSourceStockBatchOne({ url, domain });
      manualCursorRef.current = i + 1;
      setManualCursor(i + 1);
      setSessionChecks((n) => n + 1);
      setRecent((prev) => [res, ...prev].slice(0, 36));
      bumpOosRows(res, url);

      const shortUrl = url.length > 86 ? `${url.slice(0, 86)}…` : url;
      if (!res.classified_out_of_stock) {
        showToast('ok', `OK — nguồn còn đọc được («${shortUrl}»)`);
      } else if (res.updates_committed) {
        showToast('info', `Đã đặt «hết hàng» và tồn = 0 nếu có SP khớp («${shortUrl}»)`);
      } else {
        showToast(
          'info',
          `Coi là không đọc được / hết nhưng chưa thấy sản phẩm trùng trong shop («${shortUrl}»)`,
        );
      }
      return true;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setLastError(msg);
      showToast('err', `${msg} — giữ nguyên chỉ số, vui lòng thử lại.`);
      return false;
    } finally {
      setRunning(false);
    }
  }, [
    bumpOosRows,
    cooldownDays,
    domain,
    includeInactiveProducts,
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
    const tick = () => {
      if (runningRef.current) return;
      void runNextRef.current();
    };
    tick();
    const id = window.setInterval(tick, 60_000);
    return () => window.clearInterval(id);
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
    showToast('info', 'Đã bật tự động — chạy ngay một lần và sau đó ~60 giây/lần cho tới khi hết SP hoặc bạn bấm tắt.');
  };

  return (
    <div className="p-6 max-w-5xl pb-28">
      <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Kiểm tra nguồn hàng</h1>
          <p className="text-sm text-gray-600 mt-1">
            Mặc định không cần nạp danh sách; với chế độ Theo DB tab mở và <strong>Auto bật</strong>: chạy lặp một SP
            mỗi ~60 giây đến khi bạn tắt hoặc không còn SP để xếp trong bộ lọc. Backend đọc <strong>PDP traffic</strong> từ bảng{' '}
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

        {scanFromDb && (
          <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer select-none">
            <input
              type="checkbox"
              className="rounded border-gray-300"
              checked={includeInactiveProducts}
              onChange={(e) => setIncludeInactiveProducts(e.target.checked)}
              disabled={running}
            />
            Gồm luôn sản đang inactive (still quét <code className="text-xs bg-gray-100 px-1">link_default</code>)
          </label>
        )}

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
                  Tổng phạm vi (link đủ dài + lọc miền + {queueStats.active_only ? 'chỉ active' : 'gồm inactive'}):{' '}
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

        <div className="flex flex-wrap gap-3 items-center pt-2">
          <button
            type="button"
            onClick={() => void runNextInternal()}
            disabled={running}
            className="rounded-lg bg-orange-600 text-white px-4 py-2 text-sm font-medium disabled:opacity-50 hover:bg-orange-700"
          >
            {running ? 'Đang chạy…' : scanFromDb ? 'Kiểm tra sản kế trong DB' : 'Kiểm tra link kế trong danh sách tay'}
          </button>
          <button
            type="button"
            onClick={resetPointers}
            disabled={running}
            className="rounded-lg border border-gray-300 bg-gray-50 px-4 py-2 text-sm font-medium hover:bg-gray-100 disabled:opacity-50"
          >
            Đặt lại đầu hàng chờ
          </button>
          <button
            type="button"
            onClick={() => void startAutoSequence()}
            disabled={running}
            className="rounded-lg bg-slate-800 text-white px-4 py-2 text-sm font-medium disabled:opacity-50 hover:bg-slate-900"
          >
            Bật tự động (đang bật sẵn Theo DB · ≈1 lần / phút)
          </button>
          <button
            type="button"
            onClick={() => {
              setAuto(false);
              showToast('info', 'Đã tắt tự động.');
            }}
            disabled={running && !auto}
            className="rounded-lg border border-gray-400 px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-50"
          >
            Tắt tự động
          </button>
          {auto && scanFromDb ? (
            <span className="text-sm text-emerald-700 font-semibold mt-2 w-full md:inline md:w-auto md:mt-0" aria-live="polite">
              ● Theo DB đang Auto — ~60 giây/lần; bấm «Tắt tự động» hoặc rời trang để dừng
            </span>
          ) : null}
        </div>
      </div>

      <section className="mt-10" aria-labelledby="oos-heading">
        <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
          <div>
            <h2 id="oos-heading" className="text-lg font-semibold text-gray-900">
              Danh sách coi là hết hàng / không đọc được <span className="font-normal text-gray-600">(chỉ lưu tạm trên tab trình duyệt)</span>
            </h2>
            <p className="text-sm text-gray-600 mt-1 max-w-3xl">
              Bộ nhớ chỉ của phiên làm việc: refresh tab hoặc đóng trình duyệt là mất danh sách này. Trên máy chủ vẫn có{' '}
              <strong>đánh dấu vòng kiểm tra TTL</strong>, <strong>tồn kho / trạng thái nguồn</strong> của sản như các lần
              đã commit — không nằm trong bảng dưới đây. Nút “ẩn trong trình duyệt” chỉ dọn ô nhớ của trang, không đổi DB.
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
                  <td colSpan={8} className="px-3 py-6 text-gray-500 text-center">
                    Chưa có SP nào bị đánh trong phiên làm việc này.
                  </td>
                </tr>
              ) : (
                oosRows.map((row, idx) => (
                  <tr key={`oos-${idx}-${row.checkedAtIso}-${row.id}-${idx}`} className="border-t border-gray-200 align-top">
                    <td className="px-3 py-2 whitespace-nowrap">{row.id > 0 ? row.id : '—'}</td>
                    <td className="px-3 py-2 font-mono text-xs max-w-[120px] break-all">{row.product_id ?? '—'}</td>
                    <td className="px-3 py-2 max-w-[200px]">{row.name}</td>
                    <td className="px-3 py-2 whitespace-nowrap">{row.domain}</td>
                    <td className="px-3 py-2 font-mono text-xs max-w-[200px] break-all">{row.sourceUrl}</td>
                    <td className="px-3 py-2 font-mono text-xs max-w-[200px] break-all">{row.canonicalUrl}</td>
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
              const headline =
                typeof dbr.done === 'boolean' && dbr.done
                  ? 'Hết danh sách DB trong bộ lọc'
                  : r.classified_out_of_stock
                    ? 'Hết / không đọc được'
                    : 'Đọc OK';
              const sub = typeof dbr.seed_product_db_id === 'number'
                ? `SP hàng chờ #${dbr.seed_product_db_id} ${r.canonical_url || ''}`
                : r.canonical_url || '';
              return (
                <details key={`recent-${idx}-${sub}-${idx}`} className="p-4 group">
                  <summary className="cursor-pointer font-medium text-gray-900 list-none flex flex-wrap gap-2 items-baseline">
                    <span className={r.classified_out_of_stock ? 'text-red-700' : 'text-emerald-800'}>{headline}</span>
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
