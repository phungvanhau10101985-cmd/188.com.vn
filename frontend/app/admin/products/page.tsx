'use client';

import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import {
  adminProductAPI,
  type AdminImport1688Draft,
  type AdminImport1688Job,
  type AdminImportExcelJob,
  type AdminProduct,
  type AdminProductsResponse,
} from '@/lib/admin-api';
import { getCatalogFeedApiBaseUrl, isNonPublicCatalogFeedBase } from '@/lib/api-base';
import { ImportDraftExcelCompare } from '@/components/admin/ImportDraftExcelCompare';

const PAGE_SIZE = 100;

/** Lưu job_id đang chạy để khôi phục khi reload trang giữa chừng. */
const IMPORT_JOB_STORAGE_KEY = 'admin:products:import_excel:job';

/** Nội dung panel + toast sau khi poll job import xong */
function formatImportExcelJobOutcome(job: AdminImportExcelJob): {
  panel: { variant: 'err' | 'warn' | 'ok'; title: string; body: string } | null;
  toast: { type: 'ok' | 'err'; msg: string };
} {
  if (job.status === 'error') {
    const parts: string[] = [];
    parts.push(job.detail?.trim() || job.message?.trim() || 'Import thất bại');
    if (job.total_rows != null) parts.push('', `Số dòng trong file (tham khảo): ${job.total_rows}`);
    if (job.errors?.length) {
      parts.push('', 'Chi tiết:');
      for (const line of job.errors.slice(0, 200)) parts.push(typeof line === 'string' ? line : String(line));
      if (job.errors.length > 200) parts.push(`… và ${job.errors.length - 200} dòng khác`);
    }
    if (job.warnings?.length) {
      parts.push('', 'Cảnh báo đi kèm:');
      for (const w of job.warnings.slice(0, 50)) parts.push(typeof w === 'string' ? w : String(w));
    }
    return {
      panel: { variant: 'err', title: 'Import thất bại', body: parts.join('\n') },
      toast: { type: 'err', msg: 'Import lỗi — xem chi tiết phía dưới ô Import.' },
    };
  }

  const d = job.result?.data;
  const rowErrs = job.result?.errors ?? [];
  const warns = job.result?.warnings ?? [];
  const headline = `Tạo mới ${d?.created ?? 0}, cập nhật ${d?.updated ?? 0} (${d?.success_rate ?? '—'} thành công, tổng xử lý ${d?.total_processed ?? 0}).`;

  if (!rowErrs.length && !warns.length) {
    return {
      panel: null,
      toast: { type: 'ok', msg: `Import xong: ${d?.created ?? 0} mới, ${d?.updated ?? 0} cập nhật` },
    };
  }

  const body: string[] = [headline];
  if (rowErrs.length) {
    body.push('', `Lỗi theo dòng (${rowErrs.length}):`);
    rowErrs.slice(0, 200).forEach((e) => body.push(typeof e === 'string' ? e : String(e)));
    if (rowErrs.length > 200) body.push(`… và ${rowErrs.length - 200} lỗi khác`);
  }
  if (warns.length) {
    body.push('', `Cảnh báo (${warns.length}):`);
    warns.slice(0, 80).forEach((w) => body.push(typeof w === 'string' ? w : String(w)));
    if (warns.length > 80) body.push(`… và ${warns.length - 80} cảnh báo khác`);
  }

  const variant = rowErrs.length ? 'warn' : 'ok';
  const toastMsg = rowErrs.length
    ? 'Import hoàn thành nhưng có lỗi ở một số dòng — xem chi tiết phía dưới ô Import.'
    : 'Import xong có cảnh báo — xem chi tiết phía dưới ô Import.';

  return {
    panel: {
      variant,
      title: rowErrs.length ? 'Import xong nhưng còn lỗi dòng' : 'Import xong (cảnh báo)',
      body: body.join('\n'),
    },
    toast: { type: 'ok', msg: toastMsg },
  };
}

/** Chuẩn hoá khớp backend: câu có URL, markdown, hoặc hibox.mn/v/… không có https */
function resolveImportLinkUrl(raw: string): string {
  const trimmed = raw.trim().replace(/^[\uFEFF\u200b-\u200d\u2060]+/, '');
  const httpMatch = trimmed.match(/\bhttps?:\/\/[^\s\]\)<>'"]+/i);
  if (httpMatch) return httpMatch[0].replace(/[,.;:"'”’)\]]+$/u, '').trim();

  const bareMatch = trimmed.match(
    /\b(?:www\.)?(?:[\w.-]+\.)*hibox\.mn(?::\d+)?(?:\/[a-z]{2,5})?\/v\/[^\s\]\)<>'",]+/i,
  );
  if (bareMatch) {
    const frag = bareMatch[0];
    return /^https?:\/\//i.test(frag) ? frag : `https://${frag.replace(/^\/+/, '')}`;
  }
  return trimmed;
}

/** Hibox không dùng CDN 1688 — backend sẽ bỏ bước tải ảnh Bunny khi client gửi download_images: false. */
function isHiboxProductUrl(raw: string): boolean {
  try {
    const resolved = resolveImportLinkUrl(raw);
    const absolute = /^[a-z][a-z0-9+.-]*:/i.test(resolved)
      ? resolved
      : `https://${resolved.replace(/^\/+/, '')}`;
    const u = new URL(absolute);
    let host = u.hostname.replace(/^www\./i, '').toLowerCase();
    host = host.endsWith('.') ? host.slice(0, -1) : host;
    if (host === 'hibox.mn' || host.endsWith('.hibox.mn')) return true;
    if (host === 'taobao1688.kz') {
      const id =
        u.searchParams.get('id')?.trim() ||
        u.searchParams.get('item_id')?.trim() ||
        u.searchParams.get('itemId')?.trim();
      return Boolean(id && /^[a-zA-Z0-9][\w.-]{1,220}$/.test(id));
    }
    return false;
  } catch {
    return false;
  }
}

export default function AdminProductsPage() {
  const [data, setData] = useState<AdminProductsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  /** Phân biệt lỗi API với danh sách rỗng thật */
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [searchName, setSearchName] = useState('');
  const [searchId, setSearchId] = useState('');
  const [page, setPage] = useState(1);
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);
  const [importing, setImporting] = useState(false);
  const [importProgress, setImportProgress] = useState<{
    message: string;
    percent: number | null;
    /** Phụ — current/total dòng từ server để admin biết ETA. */
    current?: number | null;
    total?: number | null;
    phase?: string | null;
    /** Cảnh báo poll lỗi tạm thời. */
    warn?: string | null;
  } | null>(null);
  /** Chi tiết lỗi/cảnh báo sau import (giữ đến khi import lại hoặc đóng) */
  const [importDetailPanel, setImportDetailPanel] = useState<{
    variant: 'err' | 'warn' | 'ok';
    title: string;
    body: string;
  } | null>(null);
  const [import1688Url, setImport1688Url] = useState('');
  const [importing1688, setImporting1688] = useState(false);
  const [import1688Progress, setImport1688Progress] = useState<{
    message: string;
    percent: number | null;
    phase?: string | null;
    warn?: string | null;
  } | null>(null);
  const [import1688Draft, setImport1688Draft] = useState<AdminImport1688Draft | null>(null);
  const [publishing1688, setPublishing1688] = useState(false);
  const [exporting1688Draft, setExporting1688Draft] = useState(false);
  const [excelBatchBusy, setExcelBatchBusy] = useState(false);
  const [excelBatchTrackToken, setExcelBatchTrackToken] = useState<string | null>(null);
  const [excelBatchHint, setExcelBatchHint] = useState<string | null>(null);
  const [lastExcelBatchDraftIds, setLastExcelBatchDraftIds] = useState<number[]>([]);
  const [bulkExport1688Busy, setBulkExport1688Busy] = useState(false);
  /** Cờ huỷ theo dõi (job vẫn chạy ở server). */
  const cancelTrackRef = useRef(false);
  const [exporting, setExporting] = useState(false);
  const [downloadingTemplate, setDownloadingTemplate] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const excelBatch1688InputRef = useRef<HTMLInputElement>(null);

  const [editing, setEditing] = useState<{ productId: string; field: string; value: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [selectedProductIds, setSelectedProductIds] = useState<Set<string>>(new Set());

  const catalogFeedBase = useMemo(() => getCatalogFeedApiBaseUrl(), []);
  const feedMerchantCenterTsv = `${catalogFeedBase}/import-export/export/merchant-center-feed.tsv`;
  const feedMetaCatalogTsv = `${catalogFeedBase}/import-export/export/meta-catalog-feed.tsv`;
  const feedTiktokCatalogTsv = `${catalogFeedBase}/import-export/export/tiktok-catalog-feed.tsv`;
  const feedUrlIsNonPublic = isNonPublicCatalogFeedBase(catalogFeedBase);

  const showToast = (type: 'ok' | 'err', msg: string, persistMs?: number) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), persistMs ?? 3000);
  };

  const fetchProducts = useCallback(async () => {
    setLoading(true);
    setFetchError(null);
    try {
      const res = await adminProductAPI.getProducts({
        skip: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
        q: searchName.trim() || undefined,
        product_id: searchId.trim() || undefined,
      });
      setData(res);
    } catch (e) {
      const msg =
        e instanceof Error ? e.message : 'Lỗi tải danh sách sản phẩm';
      setFetchError(msg.length > 400 ? `${msg.slice(0, 400)}…` : msg);
      showToast('err', msg.length > 220 ? `${msg.slice(0, 220)}…` : msg, 8000);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [page, searchName, searchId]);

  useEffect(() => {
    fetchProducts();
  }, [fetchProducts]);

  useEffect(() => {
    setSelectedProductIds(new Set());
  }, [data?.products, page]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    fetchProducts();
  };

  /** Poll job với backoff + chịu lỗi mạng tạm thời (503/timeout) — file 30k dòng có thể chạy vài phút. */
  const pollImportJob = useCallback(
    async (jobId: string): Promise<AdminImportExcelJob> => {
      let lastJob: AdminImportExcelJob | null = null;
      let consecutiveErrors = 0;
      let pollIdx = 0;

      for (;;) {
        if (cancelTrackRef.current) {
          if (lastJob) return lastJob;
          throw new Error('Đã dừng theo dõi job (job vẫn chạy ở server, refresh để xem lại).');
        }

        try {
          const job = await adminProductAPI.getImportExcelJob(jobId);
          consecutiveErrors = 0;
          lastJob = job;

          setImportProgress({
            message: job.message || 'Đang xử lý…',
            percent: job.percent ?? null,
            current: job.current ?? null,
            total: job.total ?? null,
            phase: job.phase || null,
            warn: null,
          });

          if (job.status === 'done' || job.status === 'error') return job;
        } catch (err) {
          consecutiveErrors += 1;
          const msg = err instanceof Error ? err.message : String(err);
          setImportProgress((prev) => ({
            message: prev?.message || 'Đang chờ server…',
            percent: prev?.percent ?? null,
            current: prev?.current ?? null,
            total: prev?.total ?? null,
            phase: prev?.phase ?? null,
            warn: `Mất kết nối tạm thời (${consecutiveErrors}): ${msg.slice(0, 120)} — đang thử lại.`,
          }));
          if (consecutiveErrors >= 30) {
            throw new Error(
              `Không thể theo dõi job sau ${consecutiveErrors} lần thử. Lỗi cuối: ${msg}\n` +
                `Job có thể vẫn đang chạy trên server (job_id=${jobId}). Reload trang để theo dõi tiếp.`,
            );
          }
        }

        pollIdx += 1;
        const delayMs = pollIdx <= 5 ? 800 : pollIdx <= 30 ? 2500 : 5000;
        await new Promise((r) => setTimeout(r, delayMs));
      }
    },
    [],
  );

  const pollImport1688Job = useCallback(async (jobId: string): Promise<AdminImport1688Job> => {
    let lastJob: AdminImport1688Job | null = null;
    for (let pollIdx = 0; ; pollIdx += 1) {
      try {
        const job = await adminProductAPI.getImport1688Job(jobId);
        lastJob = job;
        setImport1688Progress({
          message: job.message || 'Đang xử lý link 1688…',
          percent: job.percent ?? null,
          phase: job.phase || null,
          warn: job.warnings?.[0] || null,
        });
        if (job.status === 'done' || job.status === 'error' || job.status === 'published') return job;
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        setImport1688Progress((prev) => ({
          message: prev?.message || 'Đang chờ server…',
          percent: prev?.percent ?? null,
          phase: prev?.phase ?? null,
          warn: msg.slice(0, 180),
        }));
        if (pollIdx > 25) {
          if (lastJob) return lastJob;
          throw err;
        }
      }
      const delayMs = pollIdx <= 4 ? 1000 : 3000;
      await new Promise((r) => setTimeout(r, delayMs));
    }
  }, []);

  const handleImport1688 = async (e: React.FormEvent) => {
    e.preventDefault();
    const url = resolveImportLinkUrl(import1688Url);
    if (!url) {
      showToast('err', 'Vui lòng dán link sản phẩm (1688 hoặc Hibox)');
      return;
    }
    const fromHibox = isHiboxProductUrl(url);
    setImporting1688(true);
    setImport1688Draft(null);
    setImport1688Progress({
      message: fromHibox ? 'Đang gửi link Hibox lên server…' : 'Đang gửi link 1688 lên server…',
      percent: null,
    });
    try {
      // Giữ URL ảnh gốc trong draft/export; không tự tải ảnh về Bunny ở luồng import link.
      const started = await adminProductAPI.startImport1688(url, false, fromHibox ? 'hibox' : '1688');
      setImport1688Progress({
        message: fromHibox ? 'Đã nhận link, đang mở trang Hibox…' : 'Đã nhận link, đang mở trang 1688…',
        percent: null,
      });
      const job = await pollImport1688Job(started.job_id);
      if (job.status === 'error') {
        const body = [...(job.errors || []), ...(job.warnings || [])].filter(Boolean).join('\n');
        setImportDetailPanel({
          variant: 'err',
          title: fromHibox ? 'Import Hibox thất bại' : 'Import 1688 thất bại',
          body: body || job.message || 'Không đọc được dữ liệu từ link.',
        });
        showToast('err', job.message || (fromHibox ? 'Import Hibox thất bại' : 'Import 1688 thất bại'), 8000);
        return;
      }
      const draftId = job.draft_id ?? started.draft_id;
      const draft = await adminProductAPI.getImport1688Draft(draftId);
      setImport1688Draft(draft);
      const warnText = draft.warnings?.length ? ` Có ${draft.warnings.length} cảnh báo cần kiểm tra.` : '';
      showToast('ok', `Đã tạo draft từ ${fromHibox ? 'Hibox' : '1688'}.${warnText}`, 6000);
    } catch (err) {
      const msg = err instanceof Error ? err.message : fromHibox ? 'Import Hibox thất bại' : 'Import 1688 thất bại';
      setImportDetailPanel({
        variant: 'err',
        title: fromHibox ? 'Không thể import Hibox' : 'Không thể import 1688',
        body: msg,
      });
      showToast('err', msg, 9000);
    } finally {
      setImporting1688(false);
      setImport1688Progress(null);
    }
  };

  const updateImport1688ProductField = (field: string, value: string | number | boolean) => {
    setImport1688Draft((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        product_data: {
          ...(prev.product_data || {}),
          [field]: value,
        },
      };
    });
  };

  const saveImport1688Draft = async () => {
    if (!import1688Draft?.id || !import1688Draft.product_data) return;
    const saved = await adminProductAPI.updateImport1688Draft(import1688Draft.id, import1688Draft.product_data);
    setImport1688Draft(saved);
  };

  const handlePublishImport1688 = async () => {
    if (!import1688Draft?.id || !import1688Draft.product_data) return;
    setPublishing1688(true);
    try {
      await saveImport1688Draft();
      const res = await adminProductAPI.publishImport1688Draft(import1688Draft.id);
      showToast('ok', `${res.action === 'created' ? 'Đã tạo' : 'Đã cập nhật'} sản phẩm ${res.product_id}`, 6000);
      setImport1688Draft(null);
      setImport1688Url('');
      fetchProducts();
    } catch (err) {
      showToast('err', err instanceof Error ? err.message : 'Đăng sản phẩm thất bại', 9000);
    } finally {
      setPublishing1688(false);
    }
  };

  const handleExportImport1688Draft = async () => {
    if (!import1688Draft?.id || !import1688Draft.product_data) return;
    setExporting1688Draft(true);
    try {
      await saveImport1688Draft();
      await adminProductAPI.exportImport1688DraftExcel(import1688Draft.id);
      showToast('ok', 'Đã tải Excel draft 1688');
    } catch (err) {
      showToast('err', err instanceof Error ? err.message : 'Export draft 1688 thất bại', 8000);
    } finally {
      setExporting1688Draft(false);
    }
  };

  useEffect(() => {
    const token = excelBatchTrackToken;
    if (!token) return undefined;
    let cancelled = false;
    let iv: ReturnType<typeof setInterval> | null = null;
    let pollBusy = false;

    const stopInterval = () => {
      if (iv != null) {
        clearInterval(iv);
        iv = null;
      }
    };

    const tick = async () => {
      if (pollBusy) return;
      pollBusy = true;
      try {
        const st = await adminProductAPI.getImport1688ExcelBatchStatus(token);
        if (cancelled) return;
        const msg = `Batch (tuần tự): đã xong ${st.completed}/${st.total}${
          st.failed ? ` • lỗi ${st.failed}` : ''
        } • chờ ${st.pending}`;
        setExcelBatchHint(msg);
        if (st.pending <= 0) {
          stopInterval();
          setExcelBatchTrackToken(null);
          showToast('ok', `Batch xong: ${st.completed} draft, ${st.failed} lỗi.`, 7000);
        }
      } catch (err) {
        if (!cancelled) {
          setExcelBatchHint(err instanceof Error ? err.message : 'Không poll được trạng thái batch');
        }
      } finally {
        pollBusy = false;
      }
    };

    void tick();
    iv = setInterval(() => void tick(), 3500);

    return () => {
      cancelled = true;
      stopInterval();
    };
  }, [excelBatchTrackToken]);

  const handleExcelBatch1688Pick = () => {
    excelBatch1688InputRef.current?.click();
  };

  const handleExcelBatch1688Change = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const input = e.target;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    setExcelBatchBusy(true);
    setExcelBatchHint('Đang tải file và tạo draft cho từng dòng…');
    try {
      const res = await adminProductAPI.uploadImport1688ExcelBatch(file);
      setLastExcelBatchDraftIds(res.draft_ids ?? []);
      if (res.skipped?.length) {
        const head = res.skipped.slice(0, 4).join(' — ');
        showToast(
          'err',
          `${head}${res.skipped.length > 4 ? '…' : ''} (${res.skipped.length} dòng bỏ qua)`,
          14000,
        );
      }
      setExcelBatchTrackToken(res.batch_token);
      showToast('ok', `Đã nhận ${res.total} link. Server xử lý tuần tự (có thể vài phút).`, 6000);
    } catch (err) {
      setExcelBatchHint(null);
      showToast('err', err instanceof Error ? err.message : 'Upload batch thất bại', 10000);
    } finally {
      setExcelBatchBusy(false);
    }
  };

  const handleExportLastExcelBatch = async () => {
    const ids = lastExcelBatchDraftIds.filter((x) => typeof x === 'number' && x > 0);
    if (!ids.length) {
      showToast('err', 'Chưa có draft từ batch Excel. Hãy chạy import file trước.', 6000);
      return;
    }
    setBulkExport1688Busy(true);
    try {
      await adminProductAPI.exportImport1688DraftsExcelBulk(ids);
      showToast('ok', 'Đã tải Excel gộp các draft (chỉ dòng đã có dữ liệu).', 8000);
    } catch (err) {
      showToast('err', err instanceof Error ? err.message : 'Export gộp thất bại', 10000);
    } finally {
      setBulkExport1688Busy(false);
    }
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    cancelTrackRef.current = false;
    setImporting(true);
    setImportDetailPanel(null);
    const szMb = file.size / (1024 * 1024);
    setImportProgress({
      message:
        szMb >= 2
          ? `Đang tải file (${szMb.toFixed(1)} MB)… File lớn có thể vài phút.`
          : 'Đang tải file lên server…',
      percent: null,
    });
    try {
      const { job_id } = await adminProductAPI.startImportExcelAsync(file, false, (loaded, total) => {
        const pct = total > 0 ? Math.min(99, Math.round((loaded / total) * 100)) : 0;
        setImportProgress({
          message: `Đang tải lên ${pct}% (${(loaded / (1024 * 1024)).toFixed(2)} / ${(total / (1024 * 1024)).toFixed(2)} MB)`,
          percent: pct,
        });
      });

      try {
        localStorage.setItem(
          IMPORT_JOB_STORAGE_KEY,
          JSON.stringify({ job_id, started_at: Date.now(), file: file.name }),
        );
      } catch {
        /* localStorage có thể đầy / disabled — bỏ qua */
      }

      setImportProgress({
        message: 'Đã nhận file, đang xử lý trên server (file 30k dòng có thể vài phút)…',
        percent: null,
      });

      const job = await pollImportJob(job_id);

      try {
        localStorage.removeItem(IMPORT_JOB_STORAGE_KEY);
      } catch {
        /* noop */
      }

      const { panel, toast: tmsg } = formatImportExcelJobOutcome(job);
      if (panel) setImportDetailPanel(panel);
      showToast(tmsg.type, tmsg.msg, tmsg.type === 'err' || panel?.variant === 'warn' ? 8000 : 4500);

      if (job.status !== 'error') fetchProducts();
    } catch (err: unknown) {
      const raw = (err as Error)?.message || 'Import thất bại';
      setImportDetailPanel({
        variant: 'err',
        title: 'Không thể bắt đầu hoặc theo dõi import',
        body: raw,
      });
      showToast('err', raw, 9000);
    } finally {
      setImporting(false);
      setImportProgress(null);
      cancelTrackRef.current = false;
      e.target.value = '';
    }
  };

  /** Khi reload trang trong lúc đang chạy job — tự động khôi phục theo dõi. */
  useEffect(() => {
    let cancelled = false;
    (async () => {
      type StoredImportJob = { job_id?: string; started_at?: number; file?: string };
      let saved: StoredImportJob | null = null;
      try {
        const raw = localStorage.getItem(IMPORT_JOB_STORAGE_KEY);
        saved = raw ? (JSON.parse(raw) as StoredImportJob) : null;
      } catch {
        saved = null;
      }
      if (!saved?.job_id) return;
      // Bỏ qua job > 6h trước (có thể đã rớt)
      if (saved.started_at && Date.now() - saved.started_at > 6 * 60 * 60 * 1000) {
        try {
          localStorage.removeItem(IMPORT_JOB_STORAGE_KEY);
        } catch {
          /* noop */
        }
        return;
      }

      cancelTrackRef.current = false;
      setImporting(true);
      setImportProgress({
        message: `Khôi phục theo dõi job đang chạy (file: ${saved.file || '?'})…`,
        percent: null,
      });
      try {
        const job = await pollImportJob(saved.job_id);
        if (cancelled) return;
        try {
          localStorage.removeItem(IMPORT_JOB_STORAGE_KEY);
        } catch {
          /* noop */
        }
        const { panel, toast: tmsg } = formatImportExcelJobOutcome(job);
        if (panel) setImportDetailPanel(panel);
        showToast(tmsg.type, tmsg.msg, 6000);
        if (job.status !== 'error') fetchProducts();
      } catch (err) {
        if (cancelled) return;
        const msg = (err as Error)?.message || 'Lỗi khôi phục job';
        setImportDetailPanel({ variant: 'err', title: 'Không khôi phục được job', body: msg });
      } finally {
        if (!cancelled) {
          setImporting(false);
          setImportProgress(null);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleExport = async () => {
    setExporting(true);
    try {
      await adminProductAPI.exportExcel();
      showToast('ok', 'Đã tải file Excel xuống');
    } catch {
      showToast('err', 'Export thất bại');
    } finally {
      setExporting(false);
    }
  };

  const handleDownloadTemplate = async () => {
    setDownloadingTemplate(true);
    try {
      await adminProductAPI.downloadSampleTemplate();
      showToast('ok', 'Đã tải file mẫu xuống');
    } catch {
      showToast('err', 'Tải file mẫu thất bại');
    } finally {
      setDownloadingTemplate(false);
    }
  };

  const startEdit = (productId: string, field: string, value: string | number) => {
    setEditing({ productId, field, value: String(value ?? '') });
  };

  const cancelEdit = () => {
    setEditing(null);
  };

  const saveEdit = async () => {
    if (!editing || !data?.products) return;
    const product = data.products.find((p) => p.product_id === editing.productId);
    if (!product) return;
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {};
      if (editing.field === 'name') payload.name = editing.value;
      if (editing.field === 'price') payload.price = parseFloat(editing.value) || 0;
      if (editing.field === 'product_id') payload.product_id = editing.value;
      if (editing.field === 'brand_name') payload.brand_name = editing.value;
      if (editing.field === 'category') payload.category = editing.value;
      if (editing.field === 'code') payload.code = editing.value;
      await adminProductAPI.updateProduct(editing.productId, payload as Partial<AdminProduct>);
      showToast('ok', 'Đã lưu');
      setEditing(null);
      fetchProducts();
    } catch {
      showToast('err', 'Lưu thất bại');
    } finally {
      setSaving(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent, productId: string, field: string) => {
    if (e.key === 'Enter') saveEdit();
    if (e.key === 'Escape') cancelEdit();
  };

  const totalPages = data?.total_pages ?? 1;
  const currentPageIds = useMemo(() => (data?.products || []).map((p) => p.product_id), [data?.products]);
  const allSelectedOnPage = currentPageIds.length > 0 && currentPageIds.every((id) => selectedProductIds.has(id));

  const toggleSelectAllOnPage = () => {
    setSelectedProductIds((prev) => {
      const next = new Set(prev);
      if (allSelectedOnPage) {
        currentPageIds.forEach((id) => next.delete(id));
      } else {
        currentPageIds.forEach((id) => next.add(id));
      }
      return next;
    });
  };

  const toggleSelectOne = (productId: string) => {
    setSelectedProductIds((prev) => {
      const next = new Set(prev);
      if (next.has(productId)) next.delete(productId);
      else next.add(productId);
      return next;
    });
  };

  const handleDeleteSelected = async () => {
    if (selectedProductIds.size === 0) return;
    if (!confirm(`Xóa ${selectedProductIds.size} sản phẩm đang chọn?`)) return;
    setDeleting(true);
    try {
      await Promise.all(Array.from(selectedProductIds).map((id) => adminProductAPI.deleteProduct(id)));
      showToast('ok', `Đã xóa ${selectedProductIds.size} sản phẩm`);
      await fetchProducts();
    } catch (err: unknown) {
      showToast('err', (err as Error)?.message || 'Xóa thất bại');
    } finally {
      setDeleting(false);
    }
  };

  return (
      <div className="p-6">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">Quản lý sản phẩm</h1>

        {/* Toolbar: search, import, export */}
        <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6">
          <form onSubmit={handleSearch} className="flex flex-wrap items-end gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Tên sản phẩm</label>
              <input
                type="text"
                value={searchName}
                onChange={(e) => setSearchName(e.target.value)}
                placeholder="Tìm theo tên..."
                className="w-56 rounded-lg border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">ID hoặc SKU</label>
              <input
                type="text"
                value={searchId}
                onChange={(e) => setSearchId(e.target.value)}
                placeholder="ID sản phẩm hoặc mã SKU..."
                className="w-48 rounded-lg border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
            <button type="submit" className="px-4 py-2 bg-slate-700 text-white rounded-lg hover:bg-slate-800 text-sm font-medium">
              Tìm kiếm
            </button>
            <button
              type="button"
              onClick={toggleSelectAllOnPage}
              disabled={!data?.products?.length}
              className="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 text-sm font-medium disabled:opacity-70"
            >
              {allSelectedOnPage ? 'Bỏ chọn trang' : 'Chọn tất trang'}
            </button>
            <button
              type="button"
              onClick={handleDeleteSelected}
              disabled={selectedProductIds.size === 0 || deleting}
              className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 text-sm font-medium disabled:opacity-70"
            >
              {deleting ? 'Đang xóa...' : `Xóa (${selectedProductIds.size})`}
            </button>
            <div className="flex-1" />
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.xls"
              className="hidden"
              onChange={handleImport}
            />
            <button
              type="button"
              onClick={handleDownloadTemplate}
              disabled={downloadingTemplate}
              className="px-4 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600 text-sm font-medium disabled:opacity-70"
            >
              {downloadingTemplate ? 'Đang tải...' : 'Tải file mẫu'}
            </button>
            <div className="flex flex-col items-end gap-1 min-w-[10rem]">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={importing}
                className="px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 text-sm font-medium disabled:opacity-70 w-full sm:w-auto"
              >
                {importing ? 'Đang import...' : 'Import Excel'}
              </button>
              {importing && importProgress ? (
                <div className="w-full max-w-[22rem] space-y-1">
                  <div className="h-2 rounded-full bg-gray-200 overflow-hidden">
                    {importProgress.percent != null ? (
                      <div
                        className="h-full rounded-full bg-emerald-600 transition-[width] duration-300 ease-out"
                        style={{ width: `${Math.min(100, importProgress.percent)}%` }}
                      />
                    ) : (
                      <div className="h-full w-full bg-emerald-500/70 animate-pulse rounded-full" />
                    )}
                  </div>
                  <p className="text-xs text-gray-600 leading-snug text-right line-clamp-3">
                    {importProgress.message}
                  </p>
                  {importProgress.current != null && importProgress.total != null ? (
                    <p className="text-[11px] text-gray-500 text-right">
                      Dòng: {importProgress.current.toLocaleString()} / {importProgress.total.toLocaleString()}
                      {importProgress.phase ? ` · ${importProgress.phase}` : ''}
                    </p>
                  ) : importProgress.phase ? (
                    <p className="text-[11px] text-gray-500 text-right">{importProgress.phase}</p>
                  ) : null}
                  {importProgress.warn ? (
                    <p className="text-[11px] text-amber-700 leading-snug text-right">
                      {importProgress.warn}
                    </p>
                  ) : null}
                  <div className="flex justify-end">
                    <button
                      type="button"
                      onClick={() => {
                        cancelTrackRef.current = true;
                      }}
                      className="text-[11px] text-gray-500 underline hover:text-gray-700"
                    >
                      Ẩn theo dõi (job vẫn chạy ở server)
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
            <button
              type="button"
              onClick={handleExport}
              disabled={exporting}
              className="px-4 py-2 bg-[#ea580c] text-white rounded-lg hover:bg-[#c2410c] text-sm font-medium disabled:opacity-70"
            >
              {exporting ? 'Đang export...' : 'Export Excel'}
            </button>
          </form>
          {importDetailPanel ? (
            <div
              className={`mt-3 rounded-lg border p-3 text-sm ${
                importDetailPanel.variant === 'err'
                  ? 'border-red-300 bg-red-50 text-gray-900'
                  : importDetailPanel.variant === 'warn'
                    ? 'border-amber-300 bg-amber-50 text-gray-900'
                    : 'border-sky-200 bg-sky-50 text-gray-900'
              }`}
            >
              <div className="flex justify-between gap-2 items-start mb-2">
                <span className="font-semibold">{importDetailPanel.title}</span>
                <button
                  type="button"
                  onClick={() => setImportDetailPanel(null)}
                  className="text-xs shrink-0 px-2 py-1 rounded border border-gray-400/60 hover:bg-white/80 text-gray-700"
                >
                  Đóng
                </button>
              </div>
              <pre className="whitespace-pre-wrap break-words max-h-[22rem] overflow-y-auto font-mono text-xs leading-relaxed text-gray-800">
                {importDetailPanel.body}
              </pre>
            </div>
          ) : null}
          <div id="import-1688" className="mt-4 scroll-mt-24 rounded-xl border border-orange-100 bg-orange-50/50 p-4">
            <form onSubmit={handleImport1688} className="flex flex-col lg:flex-row gap-3 lg:items-end">
              <div className="flex-1">
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <label className="block text-sm font-semibold text-gray-800">Import từ link (1688 / Hibox)</label>
                  <a
                    href="/admin/import-1688"
                    className="rounded-full border border-orange-200 bg-white px-2.5 py-1 text-xs font-medium text-orange-700 hover:bg-orange-100"
                  >
                    Nhập cookie 1688
                  </a>
                </div>
                <input
                  type="url"
                  value={import1688Url}
                  onChange={(e) => setImport1688Url(e.target.value)}
                  placeholder="1688, hibox.mn/v/… hoặc taobao1688.kz/item?id=…"
                  className="w-full rounded-lg border border-orange-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-300"
                />
                <p className="mt-1 text-xs text-gray-600">
                  1688: Playwright + cookie trong `.env` (ảnh CDN có thể tải về Bunny). Hibox: không cần cookie; ảnh giữ URL gốc. Luôn có bước
                  draft trước khi đăng hoặc export Excel khớp cột import.
                </p>
              </div>
              <button
                type="submit"
                disabled={importing1688 || !import1688Url.trim()}
                className="px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 text-sm font-medium disabled:opacity-70"
              >
                {importing1688 ? 'Đang lấy dữ liệu...' : 'Lấy dữ liệu'}
              </button>
            </form>
            <input
              ref={excelBatch1688InputRef}
              type="file"
              accept=".xlsx,.xls"
              className="hidden"
              onChange={handleExcelBatch1688Change}
            />
            <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-start sm:gap-x-3 sm:gap-y-2">
              <button
                type="button"
                onClick={handleExcelBatch1688Pick}
                disabled={excelBatchBusy}
                className="rounded-lg border border-orange-300 bg-white px-3 py-2 text-left text-sm font-medium text-orange-900 hover:bg-orange-100 disabled:opacity-70"
              >
                {excelBatchBusy
                  ? 'Đang upload…'
                  : 'Import file Excel (cột link F từ dòng 2; shop / giá từ cùng dòng vào nháp)'}
              </button>
              <button
                type="button"
                onClick={handleExportLastExcelBatch}
                disabled={
                  bulkExport1688Busy || !lastExcelBatchDraftIds.some((id) => typeof id === 'number' && id > 0)
                }
                className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-800 hover:bg-gray-50 disabled:opacity-70"
              >
                {bulkExport1688Busy ? 'Đang tải…' : 'Export Excel các draft của batch vừa upload'}
              </button>
            </div>
            {excelBatchHint ? <p className="mt-1 text-xs text-gray-700">{excelBatchHint}</p> : null}

            {importing1688 && import1688Progress ? (
              <div className="mt-3 rounded-lg border border-orange-200 bg-white p-3">
                <div className="h-2 rounded-full bg-gray-200 overflow-hidden">
                  {import1688Progress.percent != null ? (
                    <div
                      className="h-full rounded-full bg-orange-600 transition-[width] duration-300 ease-out"
                      style={{ width: `${Math.min(100, import1688Progress.percent)}%` }}
                    />
                  ) : (
                    <div className="h-full w-full bg-orange-500/70 animate-pulse rounded-full" />
                  )}
                </div>
                <p className="mt-2 text-xs text-gray-700">{import1688Progress.message}</p>
                {import1688Progress.phase ? <p className="text-[11px] text-gray-500">{import1688Progress.phase}</p> : null}
                {import1688Progress.warn ? <p className="mt-1 text-[11px] text-amber-700">{import1688Progress.warn}</p> : null}
              </div>
            ) : null}

            {import1688Draft?.product_data ? (
              <div className="mt-4 rounded-xl border border-orange-200 bg-white p-4">
                <div className="flex flex-col lg:flex-row gap-4">
                  <div className="w-full lg:w-40 shrink-0">
                    {import1688Draft.product_data.main_image ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={String(import1688Draft.product_data.main_image)}
                        alt={String(import1688Draft.product_data.name || 'Ảnh sản phẩm 1688')}
                        className="h-40 w-full object-cover rounded-lg border border-gray-200 bg-gray-50"
                      />
                    ) : (
                      <div className="h-40 rounded-lg border border-dashed border-gray-300 bg-gray-50 flex items-center justify-center text-xs text-gray-500">
                        Chưa có ảnh
                      </div>
                    )}
                    <p className="mt-2 text-xs text-gray-500">
                      {(import1688Draft.product_data.images as string[] | undefined)?.length || 0} ảnh
                    </p>
                  </div>
                  <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div className="md:col-span-2">
                      <label className="block text-xs font-medium text-gray-700 mb-1">Tên sản phẩm</label>
                      <input
                        value={String(import1688Draft.product_data.name || '')}
                        onChange={(e) => updateImport1688ProductField('name', e.target.value)}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-700 mb-1">ID sản phẩm</label>
                      <input
                        value={String(import1688Draft.product_data.product_id || '')}
                        onChange={(e) => updateImport1688ProductField('product_id', e.target.value)}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-700 mb-1">Giá</label>
                      <input
                        type="number"
                        value={Number(import1688Draft.product_data.price || 0)}
                        onChange={(e) => updateImport1688ProductField('price', Number(e.target.value) || 0)}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-700 mb-1">Shop</label>
                      <input
                        value={String(import1688Draft.product_data.shop_name || '')}
                        onChange={(e) => updateImport1688ProductField('shop_name', e.target.value)}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-700 mb-1">Mã SKU (cột sku)</label>
                      <input
                        value={String(import1688Draft.product_data.code ?? '')}
                        onChange={(e) => updateImport1688ProductField('code', e.target.value)}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-700 mb-1">Shop ID</label>
                      <input
                        value={String(import1688Draft.product_data.shop_id ?? '')}
                        onChange={(e) => updateImport1688ProductField('shop_id', e.target.value)}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-700 mb-1">Xuất xứ</label>
                      <input
                        value={String(import1688Draft.product_data.origin ?? '')}
                        onChange={(e) => updateImport1688ProductField('origin', e.target.value)}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-700 mb-1">Link nguồn (product_url)</label>
                      <input
                        value={String(import1688Draft.product_data.link_default ?? '')}
                        onChange={(e) => updateImport1688ProductField('link_default', e.target.value)}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono text-xs"
                      />
                    </div>
                    <div className="md:col-span-2">
                      <label className="block text-xs font-medium text-gray-700 mb-1">Link video (video_url)</label>
                      <input
                        value={String(import1688Draft.product_data.video_link ?? '')}
                        onChange={(e) => updateImport1688ProductField('video_link', e.target.value)}
                        placeholder="https://cloud.video.taobao.com/…mp4"
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-700 mb-1">Danh mục cấp 1</label>
                      <input
                        value={String(import1688Draft.product_data.category ?? '')}
                        onChange={(e) => updateImport1688ProductField('category', e.target.value)}
                        placeholder="VD: Thời trang nữ"
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-700 mb-1">Danh mục cấp 2</label>
                      <input
                        value={String(import1688Draft.product_data.subcategory ?? '')}
                        onChange={(e) => updateImport1688ProductField('subcategory', e.target.value)}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-700 mb-1">Danh mục cấp 3</label>
                      <input
                        value={String(import1688Draft.product_data.sub_subcategory ?? '')}
                        onChange={(e) => updateImport1688ProductField('sub_subcategory', e.target.value)}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                      />
                    </div>
                    <div className="md:col-span-2">
                      <label className="block text-xs font-medium text-gray-700 mb-1">Mô tả</label>
                      <textarea
                        value={String(import1688Draft.product_data.description || '')}
                        onChange={(e) => updateImport1688ProductField('description', e.target.value)}
                        rows={3}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                      />
                    </div>
                  </div>
                </div>
                <ImportDraftExcelCompare productData={import1688Draft.product_data as Record<string, unknown>} />
                {import1688Draft.warnings?.length ? (
                  <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                    {import1688Draft.warnings.slice(0, 4).map((w) => (
                      <p key={w}>{w}</p>
                    ))}
                  </div>
                ) : null}
                <div className="mt-4 flex flex-wrap gap-2 justify-end">
                  <button
                    type="button"
                    onClick={saveImport1688Draft}
                    className="px-4 py-2 rounded-lg border border-gray-300 bg-white text-gray-700 text-sm font-medium hover:bg-gray-50"
                  >
                    Lưu nháp
                  </button>
                  <button
                    type="button"
                    onClick={handleExportImport1688Draft}
                    disabled={exporting1688Draft}
                    className="px-4 py-2 rounded-lg bg-amber-500 text-white text-sm font-medium hover:bg-amber-600 disabled:opacity-70"
                  >
                    {exporting1688Draft ? 'Đang export...' : 'Export Excel'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setImport1688Draft(null)}
                    className="px-4 py-2 rounded-lg border border-gray-300 bg-white text-gray-700 text-sm font-medium hover:bg-gray-50"
                  >
                    Đóng
                  </button>
                  <button
                    type="button"
                    onClick={handlePublishImport1688}
                    disabled={publishing1688}
                    className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700 disabled:opacity-70"
                  >
                    {publishing1688 ? 'Đang đăng...' : 'Đăng ngay'}
                  </button>
                </div>
              </div>
            ) : null}
          </div>
          <div className="mt-4 pt-4 border-t border-gray-100 space-y-2 text-sm text-gray-700">
            <p className="text-xs text-gray-600 leading-snug">
              <strong className="font-medium text-gray-800">Nguồn cấp kiểu URL:</strong> mỗi đường link dưới đây là{' '}
              <strong className="font-medium text-gray-800">địa chỉ file TSV nằm trên máy chủ</strong>, mở được qua Internet.
              Google / Meta / TikTok <strong className="font-medium text-gray-800">tự kéo file qua HTTP(S) theo lịch</strong> — bạn{' '}
              <strong className="font-medium text-gray-800">không</strong> tải file về máy rồi upload tay. Chỉ cần dán URL vào mục
              nguồn cấp dữ liệu (scheduled fetch / URL máy chủ). Mở link trong trình duyệt chỉ để kiểm tra nhanh nội dung.
            </p>
            {feedUrlIsNonPublic ? (
              <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900 text-xs leading-snug">
                Các nền tảng chỉ truy cập được URL <strong className="font-semibold">HTTPS công khai</strong> (domain thật trên mạng), không phải{' '}
                <code className="text-[11px]">localhost</code>. Trên production hãy đặt{' '}
                <code className="text-[11px]">NEXT_PUBLIC_SITE_URL</code> hoặc{' '}
                <code className="text-[11px]">NEXT_PUBLIC_CATALOG_FEED_API_BASE_URL</code> trỏ tới base{' '}
                <code className="text-[11px]">…/api/v1</code> công khai, rồi dán các URL dưới đây vào cấu hình nguồn cấp.
              </p>
            ) : (
              <p className="text-xs text-gray-500 leading-snug">
                Dán nguyên URL (kèm <code className="text-[11px]">https://</code>) vào Merchant Center / Commerce Manager / TikTok Ads — họ tải file trực tiếp từ địa chỉ đó.
              </p>
            )}
            <p>
              <span className="font-medium text-gray-800">Google Merchant Center</span>{' '}
              <a
                href={feedMerchantCenterTsv}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-700 hover:underline break-all"
              >
                {feedMerchantCenterTsv}
              </a>
              <span className="text-gray-500"> — Nguồn dữ liệu URL máy chủ · file TSV online (tab), không phải upload file tải về.</span>
            </p>
            <p>
              <span className="font-medium text-gray-800">Meta (Facebook / Instagram) catalogue</span>{' '}
              <a
                href={feedMetaCatalogTsv}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-700 hover:underline break-all"
              >
                {feedMetaCatalogTsv}
              </a>
              <span className="text-gray-500"> — Commerce Manager · Data feed theo lịch (scheduled) · URL trỏ file trên mạng · cột theo catalogue Meta (`fb_product_category` trong `.env`).</span>
            </p>
            <p>
              <span className="font-medium text-gray-800">TikTok catalogue</span>{' '}
              <a
                href={feedTiktokCatalogTsv}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-700 hover:underline break-all"
              >
                {feedTiktokCatalogTsv}
              </a>
              <span className="text-gray-500"> — Ads Manager · Lịch tải feed qua URL · file TSV online · ID mục là `sku_id` (= product_id).</span>
            </p>
          </div>
        </div>

        {/* Table */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          {loading ? (
            <div className="p-12 text-center text-gray-500">Đang tải...</div>
          ) : fetchError ? (
            <div className="p-12 text-center space-y-4">
              <p className="text-red-600 whitespace-pre-wrap max-w-2xl mx-auto">{fetchError}</p>
              <button
                type="button"
                onClick={() => fetchProducts()}
                className="inline-flex items-center px-4 py-2 rounded-lg bg-gray-900 text-white text-sm hover:bg-gray-800"
              >
                Thử lại
              </button>
            </div>
          ) : data ? (
            <>
              <div className="px-4 py-2.5 border-b border-gray-100 bg-gray-50/90 text-sm text-gray-700">
                <span className="font-semibold tabular-nums text-gray-900">
                  {data.total.toLocaleString('vi-VN')}
                </span>{' '}
                sản phẩm trong danh sách
                {totalPages > 1 ? (
                  <span className="text-gray-500">
                    {' '}
                    · Trang này:{' '}
                    <span className="tabular-nums text-gray-700">{data.products.length.toLocaleString('vi-VN')}</span>
                    {' / '}
                    <span className="tabular-nums text-gray-700">{data.total.toLocaleString('vi-VN')}</span>
                  </span>
                ) : null}
              </div>
              {!data.products?.length ? (
                <div className="p-12 text-center text-gray-500">Không có sản phẩm nào.</div>
              ) : (
                <>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-gray-50 border-b border-gray-200">
                          <th className="text-left py-3 px-4 font-semibold text-gray-700 w-10">
                            <input
                              type="checkbox"
                              checked={allSelectedOnPage}
                              onChange={toggleSelectAllOnPage}
                              aria-label="Chọn tất cả sản phẩm trong trang"
                            />
                          </th>
                          <th className="text-left py-3 px-4 font-semibold text-gray-700 w-28">ID</th>
                          <th className="text-left py-3 px-4 font-semibold text-gray-700">Tên</th>
                          <th className="text-left py-3 px-4 font-semibold text-gray-700 w-24">Giá</th>
                          <th className="text-left py-3 px-4 font-semibold text-gray-700 w-32">Thương hiệu</th>
                          <th className="text-left py-3 px-4 font-semibold text-gray-700 w-28">Danh mục</th>
                          <th className="text-left py-3 px-4 font-semibold text-gray-700 w-20">Trạng thái</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.products.map((p) => (
                      <tr key={p.id} className="border-b border-gray-100 hover:bg-gray-50/50">
                        <td className="py-2 px-4">
                          <input
                            type="checkbox"
                            checked={selectedProductIds.has(p.product_id)}
                            onChange={() => toggleSelectOne(p.product_id)}
                            aria-label={`Chọn sản phẩm ${p.product_id}`}
                          />
                        </td>
                        <td className="py-2 px-4">
                          {editing?.productId === p.product_id && editing?.field === 'product_id' ? (
                            <input
                              autoFocus
                              value={editing.value}
                              onChange={(e) => setEditing((x) => x ? { ...x, value: e.target.value } : null)}
                              onBlur={saveEdit}
                              onKeyDown={(e) => handleKeyDown(e, p.product_id, 'product_id')}
                              className="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                            />
                          ) : (
                            <span
                              className="cursor-pointer text-blue-600 hover:underline"
                              onClick={() => startEdit(p.product_id, 'product_id', p.product_id ?? '')}
                              title="Bấm để sửa"
                            >
                              {(p as AdminProduct).product_id || p.id}
                            </span>
                          )}
                        </td>
                        <td className="py-2 px-4">
                          {editing?.productId === p.product_id && editing?.field === 'name' ? (
                            <input
                              autoFocus
                              value={editing.value}
                              onChange={(e) => setEditing((x) => x ? { ...x, value: e.target.value } : null)}
                              onBlur={saveEdit}
                              onKeyDown={(e) => handleKeyDown(e, p.product_id, 'name')}
                              className="w-full rounded border border-gray-300 px-2 py-1"
                            />
                          ) : (
                            <span
                              className="cursor-pointer hover:bg-gray-100 rounded px-1 -mx-1 line-clamp-2"
                              onClick={() => startEdit(p.product_id, 'name', p.name ?? '')}
                              title="Bấm để sửa"
                            >
                              {p.name || '—'}
                            </span>
                          )}
                        </td>
                        <td className="py-2 px-4">
                          {editing?.productId === p.product_id && editing?.field === 'price' ? (
                            <input
                              type="number"
                              autoFocus
                              value={editing.value}
                              onChange={(e) => setEditing((x) => x ? { ...x, value: e.target.value } : null)}
                              onBlur={saveEdit}
                              onKeyDown={(e) => handleKeyDown(e, p.product_id, 'price')}
                              className="w-full rounded border border-gray-300 px-2 py-1"
                            />
                          ) : (
                            <span
                              className="cursor-pointer hover:bg-gray-100 rounded px-1 -mx-1"
                              onClick={() => startEdit(p.product_id, 'price', p.price ?? 0)}
                              title="Bấm để sửa"
                            >
                              {typeof p.price === 'number' ? new Intl.NumberFormat('vi-VN').format(p.price) : p.price}
                            </span>
                          )}
                        </td>
                        <td className="py-2 px-4">
                          {editing?.productId === p.product_id && editing?.field === 'brand_name' ? (
                            <input
                              autoFocus
                              value={editing.value}
                              onChange={(e) => setEditing((x) => x ? { ...x, value: e.target.value } : null)}
                              onBlur={saveEdit}
                              onKeyDown={(e) => handleKeyDown(e, p.product_id, 'brand_name')}
                              className="w-full rounded border border-gray-300 px-2 py-1"
                            />
                          ) : (
                            <span
                              className="cursor-pointer hover:bg-gray-100 rounded px-1 -mx-1"
                              onClick={() => startEdit(p.product_id, 'brand_name', p.brand_name ?? '')}
                              title="Bấm để sửa"
                            >
                              {p.brand_name || '—'}
                            </span>
                          )}
                        </td>
                        <td className="py-2 px-4">
                          {editing?.productId === p.product_id && editing?.field === 'category' ? (
                            <input
                              autoFocus
                              value={editing.value}
                              onChange={(e) => setEditing((x) => x ? { ...x, value: e.target.value } : null)}
                              onBlur={saveEdit}
                              onKeyDown={(e) => handleKeyDown(e, p.product_id, 'category')}
                              className="w-full rounded border border-gray-300 px-2 py-1"
                            />
                          ) : (
                            <span
                              className="cursor-pointer hover:bg-gray-100 rounded px-1 -mx-1"
                              onClick={() => startEdit(p.product_id, 'category', p.category ?? '')}
                              title="Bấm để sửa"
                            >
                              {p.category || '—'}
                            </span>
                          )}
                        </td>
                        <td className="py-2 px-4">
                          <span className={p.is_active !== false ? 'text-green-600' : 'text-gray-400'}>
                            {p.is_active !== false ? 'Hiển thị' : 'Ẩn'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination: 100 sản phẩm 1 trang */}
              <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3 bg-gray-50">
                <span className="text-sm text-gray-600">
                  Trang {page} / {totalPages} — Tổng {data.total} sản phẩm (100/trang)
                </span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page <= 1}
                    className="px-3 py-1.5 rounded border border-gray-300 text-sm font-medium disabled:opacity-50 hover:bg-gray-100"
                  >
                    Trước
                  </button>
                  <button
                    type="button"
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page >= totalPages}
                    className="px-3 py-1.5 rounded border border-gray-300 text-sm font-medium disabled:opacity-50 hover:bg-gray-100"
                  >
                    Sau
                  </button>
                </div>
              </div>
                </>
              )}
            </>
          ) : null}
        </div>

        {toast && (
          <div
            className={`fixed bottom-4 right-4 px-4 py-2 rounded-lg shadow-lg text-white text-sm ${
              toast.type === 'ok' ? 'bg-green-600' : 'bg-red-600'
            }`}
          >
            {toast.msg}
          </div>
        )}
      </div>
  );
}
