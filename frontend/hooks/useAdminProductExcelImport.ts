'use client';

import { useCallback, useEffect, useRef, useState, type ChangeEvent } from 'react';
import { adminProductAPI, type AdminImportExcelJob } from '@/lib/admin-api';
import {
  ADMIN_PRODUCT_EXCEL_IMPORT_JOB_STORAGE_KEY,
  formatImportExcelJobOutcome,
  type ImportExcelJobDetailPanel,
} from '@/lib/import-excel-job-outcome';

export type AdminProductExcelImportProgress = {
  message: string;
  percent: number | null;
  current?: number | null;
  total?: number | null;
  phase?: string | null;
  warn?: string | null;
  cancel_requested?: boolean;
};

type ToastFn = (type: 'ok' | 'err', msg: string) => void;

export function useAdminProductExcelImport(opts: { onToast: ToastFn }) {
  const { onToast } = opts;
  const [importing, setImporting] = useState(false);
  const [importProgress, setImportProgress] = useState<AdminProductExcelImportProgress | null>(null);
  const [importCancelBusy, setImportCancelBusy] = useState(false);
  const [importDetailPanel, setImportDetailPanel] = useState<ImportExcelJobDetailPanel | null>(null);
  const [hasActiveJob, setHasActiveJob] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const activeImportJobIdRef = useRef<string | null>(null);
  const cancelTrackRef = useRef(false);
  const importUserCancelledRef = useRef(false);

  const pollImportJob = useCallback(async (jobId: string): Promise<AdminImportExcelJob> => {
    let lastJob: AdminImportExcelJob | null = null;
    let consecutiveErrors = 0;
    let pollIdx = 0;

    for (;;) {
      if (cancelTrackRef.current) {
        if (lastJob?.status === 'cancelled') return lastJob;
        if (importUserCancelledRef.current) {
          return (
            lastJob ?? {
              job_id: jobId,
              status: 'cancelled',
              phase: 'cancelled',
              current: 0,
              total: null,
              percent: null,
              message: 'Import đã hủy ngay.',
            }
          );
        }
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
          cancel_requested: Boolean(job.cancel_requested),
        });
        if (job.status === 'done' || job.status === 'error' || job.status === 'cancelled') return job;
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
  }, []);

  const handleCancel = useCallback(async () => {
    const jobId = activeImportJobIdRef.current;
    if (!jobId || importCancelBusy) return;
    setImportCancelBusy(true);
    cancelTrackRef.current = true;
    importUserCancelledRef.current = true;
    try {
      const job = await adminProductAPI.cancelImportExcelJob(jobId);
      setImportProgress((prev) =>
        prev
          ? {
              ...prev,
              message: job.message || 'Import đã hủy ngay.',
              cancel_requested: true,
              phase: 'cancelled',
            }
          : prev,
      );
      setImporting(false);
      setImportProgress(null);
      activeImportJobIdRef.current = null;
      setHasActiveJob(false);
      try {
        localStorage.removeItem(ADMIN_PRODUCT_EXCEL_IMPORT_JOB_STORAGE_KEY);
      } catch {
        /* noop */
      }
      const { panel, toast: tmsg } = formatImportExcelJobOutcome(job);
      if (panel) setImportDetailPanel(panel);
      onToast(tmsg.type, tmsg.msg);
    } catch (err) {
      onToast('err', err instanceof Error ? err.message : 'Không thể hủy import');
    } finally {
      setImportCancelBusy(false);
    }
  }, [importCancelBusy, onToast]);

  const handleFileChange = useCallback(
    async (e: ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      cancelTrackRef.current = false;
      importUserCancelledRef.current = false;
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
        activeImportJobIdRef.current = job_id;
        setHasActiveJob(true);
        try {
          localStorage.setItem(
            ADMIN_PRODUCT_EXCEL_IMPORT_JOB_STORAGE_KEY,
            JSON.stringify({ job_id, started_at: Date.now(), file: file.name }),
          );
        } catch {
          /* localStorage có thể đầy / disabled */
        }
        setImportProgress({
          message: 'Đã nhận file, đang xử lý trên server (file 30k dòng có thể vài phút)…',
          percent: null,
        });
        const job = await pollImportJob(job_id);
        if (importUserCancelledRef.current) {
          importUserCancelledRef.current = false;
          return;
        }
        try {
          localStorage.removeItem(ADMIN_PRODUCT_EXCEL_IMPORT_JOB_STORAGE_KEY);
        } catch {
          /* noop */
        }
        const { panel, toast: tmsg } = formatImportExcelJobOutcome(job);
        if (panel) setImportDetailPanel(panel);
        onToast(tmsg.type, tmsg.msg);
      } catch (err: unknown) {
        const raw = (err as Error)?.message || 'Import thất bại';
        setImportDetailPanel({
          variant: 'err',
          title: 'Không thể bắt đầu hoặc theo dõi import',
          body: raw,
        });
        onToast('err', raw);
      } finally {
        setImporting(false);
        setImportProgress(null);
        cancelTrackRef.current = false;
        activeImportJobIdRef.current = null;
        setHasActiveJob(false);
        e.target.value = '';
      }
    },
    [onToast, pollImportJob],
  );

  const openPicker = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const hideTracking = useCallback(() => {
    cancelTrackRef.current = true;
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      type StoredImportJob = { job_id?: string; started_at?: number; file?: string };
      let saved: StoredImportJob | null = null;
      try {
        const raw = localStorage.getItem(ADMIN_PRODUCT_EXCEL_IMPORT_JOB_STORAGE_KEY);
        saved = raw ? (JSON.parse(raw) as StoredImportJob) : null;
      } catch {
        saved = null;
      }
      if (!saved?.job_id) return;
      if (saved.started_at && Date.now() - saved.started_at > 6 * 60 * 60 * 1000) {
        try {
          localStorage.removeItem(ADMIN_PRODUCT_EXCEL_IMPORT_JOB_STORAGE_KEY);
        } catch {
          /* noop */
        }
        return;
      }

      cancelTrackRef.current = false;
      activeImportJobIdRef.current = saved.job_id;
      setHasActiveJob(true);
      setImporting(true);
      setImportProgress({
        message: `Khôi phục theo dõi job đang chạy (file: ${saved.file || '?'})…`,
        percent: null,
      });
      try {
        const job = await pollImportJob(saved.job_id);
        if (cancelled) return;
        try {
          localStorage.removeItem(ADMIN_PRODUCT_EXCEL_IMPORT_JOB_STORAGE_KEY);
        } catch {
          /* noop */
        }
        const { panel, toast: tmsg } = formatImportExcelJobOutcome(job);
        if (panel) setImportDetailPanel(panel);
        onToast(tmsg.type, tmsg.msg);
      } catch (err) {
        if (cancelled) return;
        const msg = (err as Error)?.message || 'Lỗi khôi phục job';
        setImportDetailPanel({ variant: 'err', title: 'Không khôi phục được job', body: msg });
      } finally {
        if (!cancelled) {
          setImporting(false);
          setImportProgress(null);
          activeImportJobIdRef.current = null;
          setHasActiveJob(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // Chỉ khôi phục một lần khi mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    importing,
    importProgress,
    importCancelBusy,
    importDetailPanel,
    setImportDetailPanel,
    hasActiveJob,
    fileInputRef,
    handleFileChange,
    openPicker,
    handleCancel,
    hideTracking,
  };
}

export type AdminProductExcelImportCtrl = ReturnType<typeof useAdminProductExcelImport>;
