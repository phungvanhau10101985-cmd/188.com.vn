'use client';

import type { AdminProductExcelImportCtrl } from '@/hooks/useAdminProductExcelImport';

export function AdminProductExcelImportHiddenInput({ ctrl }: { ctrl: AdminProductExcelImportCtrl }) {
  return (
    <input
      ref={ctrl.fileInputRef}
      type="file"
      accept=".xlsx,.xls"
      className="hidden"
      onChange={(e) => void ctrl.handleFileChange(e)}
      aria-hidden
      tabIndex={-1}
    />
  );
}

export function AdminProductExcelImportButton({
  ctrl,
  className,
}: {
  ctrl: AdminProductExcelImportCtrl;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={ctrl.openPicker}
      disabled={ctrl.importing}
      className={
        className ??
        'px-3 py-1.5 rounded-md border border-teal-600 bg-teal-600 text-white text-sm font-medium hover:bg-teal-700 disabled:opacity-40'
      }
      title="Chọn file .xlsx dữ liệu sản phẩm (cùng mẫu «Tải Excel nhập web») để tạo/cập nhật sản phẩm trên web."
      aria-label="Import file Excel dữ liệu sản phẩm"
    >
      {ctrl.importing ? 'Đang import…' : 'Import Excel dữ liệu SP'}
    </button>
  );
}

export function AdminProductExcelImportStatus({ ctrl }: { ctrl: AdminProductExcelImportCtrl }) {
  const { importing, importProgress, importDetailPanel, setImportDetailPanel, importCancelBusy, hasActiveJob } =
    ctrl;

  return (
    <>
      {importing && importProgress ? (
        <div
          className="rounded-md border border-teal-200 bg-teal-50/80 px-3 py-2 space-y-1.5"
          role="status"
          aria-live="polite"
          aria-label="Tiến trình import Excel dữ liệu sản phẩm"
        >
          <div className="h-1.5 rounded-full bg-slate-200 overflow-hidden">
            {importProgress.percent != null ? (
              <div
                className="h-full rounded-full bg-teal-600 transition-[width] duration-300 ease-out"
                style={{ width: `${Math.min(100, importProgress.percent)}%` }}
              />
            ) : (
              <div className="h-full w-full bg-teal-500/70 animate-pulse rounded-full" />
            )}
          </div>
          <p className="text-xs text-slate-800 leading-snug">{importProgress.message}</p>
          {importProgress.current != null && importProgress.total != null ? (
            <p className="text-[11px] text-slate-600">
              Dòng: {importProgress.current.toLocaleString()} / {importProgress.total.toLocaleString()}
              {importProgress.phase ? ` · ${importProgress.phase}` : ''}
            </p>
          ) : importProgress.phase ? (
            <p className="text-[11px] text-slate-600">{importProgress.phase}</p>
          ) : null}
          {importProgress.warn ? <p className="text-[11px] text-amber-800">{importProgress.warn}</p> : null}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-0.5">
            <button
              type="button"
              onClick={() => void ctrl.handleCancel()}
              disabled={importCancelBusy || !hasActiveJob}
              className="text-[11px] font-medium text-red-700 underline hover:text-red-900 disabled:cursor-not-allowed disabled:opacity-50 disabled:no-underline"
              aria-label="Hủy ngay import Excel đang chạy"
            >
              {importCancelBusy ? 'Đang hủy…' : 'Hủy ngay'}
            </button>
            <button
              type="button"
              onClick={ctrl.hideTracking}
              className="text-[11px] text-slate-500 underline hover:text-slate-700"
            >
              Ẩn theo dõi (job vẫn chạy ở server)
            </button>
          </div>
        </div>
      ) : null}

      {importDetailPanel ? (
        <div
          className={`rounded-md border p-3 text-sm ${
            importDetailPanel.variant === 'err'
              ? 'border-red-300 bg-red-50 text-slate-900'
              : importDetailPanel.variant === 'warn'
                ? 'border-amber-300 bg-amber-50 text-slate-900'
                : 'border-sky-200 bg-sky-50 text-slate-900'
          }`}
          role="region"
          aria-label={importDetailPanel.title}
        >
          <div className="flex justify-between gap-2 items-start mb-2">
            <span className="font-semibold">{importDetailPanel.title}</span>
            <button
              type="button"
              onClick={() => setImportDetailPanel(null)}
              className="text-xs shrink-0 px-2 py-1 rounded border border-slate-400/60 hover:bg-white/80 text-slate-700"
            >
              Đóng
            </button>
          </div>
          <pre className="whitespace-pre-wrap break-words max-h-[22rem] overflow-y-auto font-mono text-xs leading-relaxed text-slate-800">
            {importDetailPanel.body}
          </pre>
        </div>
      ) : null}
    </>
  );
}
