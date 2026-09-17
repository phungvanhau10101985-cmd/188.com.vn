import type { AdminImportExcelJob } from '@/lib/admin-api';

/** Cùng key giữa Quản lý sản phẩm và Parse listing — F5 / đổi trang vẫn theo dõi được job. */
export const ADMIN_PRODUCT_EXCEL_IMPORT_JOB_STORAGE_KEY = 'admin:products:import_excel:job';

export type ImportExcelJobDetailPanel = {
  variant: 'err' | 'warn' | 'ok';
  title: string;
  body: string;
};

/** Nội dung panel + toast sau khi poll job import Excel sản phẩm xong. */
export function formatImportExcelJobOutcome(job: AdminImportExcelJob): {
  panel: ImportExcelJobDetailPanel | null;
  toast: { type: 'ok' | 'err'; msg: string };
} {
  if (job.status === 'cancelled') {
    const parts: string[] = [job.message?.trim() || 'Import đã hủy ngay.'];
    if (job.current != null && job.total != null) {
      parts.push(
        '',
        `Tiến trình khi hủy: ${job.current.toLocaleString()} / ${job.total.toLocaleString()} dòng (${job.phase || '—'}).`,
      );
    }
    parts.push('', 'Các dòng đã commit trước khi hủy vẫn giữ trên DB.');
    return {
      panel: { variant: 'warn', title: 'Import đã hủy', body: parts.join('\n') },
      toast: { type: 'err', msg: 'Đã hủy import Excel.' },
    };
  }

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
  const skipped = job.result?.skipped ?? [];
  const skippedFromData = typeof d?.skipped_count === 'number' ? d.skipped_count : undefined;
  const skippedCount = skippedFromData ?? skipped.length;
  const deletedCount = typeof d?.deleted === 'number' ? d.deleted : 0;
  const headline = `Tạo mới ${d?.created ?? 0}, cập nhật ${d?.updated ?? 0}, xóa khỏi DB ${deletedCount}, bỏ qua ${skippedCount}. Không lỗi: ${d?.success_rate ?? '—'}. Tổng dòng file: ${d?.total_processed ?? 0}.`;

  if (!rowErrs.length && !warns.length && skippedCount === 0) {
    return {
      panel: null,
      toast: {
        type: 'ok',
        msg: `Import xong: ${d?.created ?? 0} mới, ${d?.updated ?? 0} cập nhật${deletedCount ? `, ${deletedCount} đã xóa` : ''}`,
      },
    };
  }

  const body: string[] = [headline];
  if (skippedCount > 0) {
    body.push('', `Bỏ qua — trùng ID nguồn hoặc SKU (${skippedCount}):`);
    if (skipped.length) {
      skipped.slice(0, 200).forEach((s) => body.push(typeof s === 'string' ? s : String(s)));
      if (skipped.length > 200) body.push(`… và ${skipped.length - 200} dòng bỏ qua khác`);
    } else {
      body.push('(Chi tiết từng dòng không có trong phản hồi — kiểm tra log server.)');
    }
  }
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

  const variant = rowErrs.length ? 'warn' : warns.length ? 'warn' : 'ok';
  const toastMsg = rowErrs.length
    ? 'Import hoàn thành nhưng có lỗi ở một số dòng — xem chi tiết phía dưới ô Import.'
    : skippedCount > 0
      ? `Import xong — ${skippedCount} dòng bỏ qua (trùng ID/SKU); xem báo cáo.`
      : 'Import xong có cảnh báo — xem chi tiết phía dưới ô Import.';

  return {
    panel: {
      variant,
      title: rowErrs.length
        ? 'Import xong nhưng còn lỗi dòng'
        : skippedCount > 0
          ? 'Import xong (có dòng bỏ qua)'
          : 'Import xong (cảnh báo)',
      body: body.join('\n'),
    },
    toast: { type: 'ok', msg: toastMsg },
  };
}
