'use client';

import { useState } from 'react';
import { adminProductAPI } from '@/lib/admin-api';

/** Tải file Excel báo cáo import — cột «Lý do bỏ qua» cho từng dòng. */
export function ImportExcelReportDownload({ jobId }: { jobId?: string | null }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!jobId) return null;

  return (
    <span className="inline-flex flex-col items-end gap-1">
      <button
        type="button"
        disabled={busy}
        onClick={() => {
          setBusy(true);
          setError(null);
          void adminProductAPI.downloadImportExcelJobReport(jobId).then(
            () => setBusy(false),
            (err: unknown) => {
              setBusy(false);
              setError(err instanceof Error ? err.message : 'Không tải được báo cáo');
            },
          );
        }}
        className="text-xs shrink-0 px-2 py-1 rounded border border-sky-700 bg-white text-sky-900 hover:bg-sky-50 disabled:opacity-50"
        aria-label="Tải báo cáo Excel lý do bỏ qua từng dòng"
      >
        {busy ? 'Đang tải báo cáo…' : 'Tải báo cáo Excel'}
      </button>
      {error ? <span className="max-w-[16rem] text-[11px] text-red-700 text-right">{error}</span> : null}
    </span>
  );
}
