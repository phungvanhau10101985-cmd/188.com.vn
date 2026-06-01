'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react';
import {
  adminCodSettlementAPI,
  adminFreightSettlementAPI,
  adminOrderAPI,
  adminShippingAPI,
  type AdminOrder,
  type EmsCodSettlementImportResult,
  type EmsCodSettlementRow,
  type EmsFreightSettlementImportResult,
  type EmsFreightSettlementRow,
  type EmsShippingImportBatch,
  type EmsShippingImportReport,
  type EmsShippingImportReportRow,
  type EmsShippingImportResult,
  type EmsShippingImportBatchesResult,
  type EmsShippingImportRow,
  type EmsShippingOperationsStats,
  type EmsShippingTimelineGranularity,
  type EmsShippingTimelineItem,
  type EmsShippingTimelineParams,
  type EmsShippingTimelinePreset,
  type EmsShippingTimelineRecordsParams,
  type EmsShippingTimelineStats,
  type EmsTrackingRefreshJob,
  type OpsBucketKey,
  type ShopReturnConfirmResult,
  type ShopReturnConfirmRow,
} from '@/lib/admin-api';

const EMS_LIST_PAGE_SIZES = [25, 50, 100] as const;
const EMS_LIST_DEFAULT_PAGE_SIZE = 50;
const EMS_SEARCH_PREVIEW_LIMIT = 5;
const OPS_LIST_PAGE_SIZE = 25;
const EMS_TRACKING_JOB_STORAGE_KEY = 'admin_ems_tracking_job_id';
const TIMELINE_GRANULARITY_LABELS: Record<EmsShippingTimelineGranularity, string> = {
  year: 'Năm',
  month: 'Tháng',
  week: 'Tuần',
  day: 'Ngày',
};

const TIMELINE_BUCKET_LABELS: Record<OpsBucketKey, string> = {
  total: 'Tổng vận đơn',
  in_transit: 'Đang giao',
  delivered: 'Giao OK',
  returned: 'Đơn hoàn chưa trả shop',
  pending: 'Chưa rõ EMS',
  has_cod: 'Có COD',
  cod_in_transit_unpaid: 'COD đang giao · chưa trả',
  cod_delivered_unpaid: 'Giao OK · EMS chưa trả COD',
  cod_paid: 'COD EMS trả shop',
  cod_returned_unpaid: 'COD hoàn · chưa trả',
  cod_pending_unpaid: 'COD chưa rõ trạng thái',
  freight_unsettled: 'Chưa đối soát cước',
  shop_linked: 'Ghép đơn shop',
  shop_return_received: 'Đơn hoàn đã trả shop',
  shop_shipping: 'Đơn shop đang giao',
};

type TimelineFilterState = {
  dateFrom: string;
  dateTo: string;
  year: string;
  preset: EmsShippingTimelinePreset | null;
};

const EMPTY_TIMELINE_FILTER: TimelineFilterState = {
  dateFrom: '',
  dateTo: '',
  year: '',
  preset: null,
};

function buildTimelineApiParams(
  granularity: EmsShippingTimelineGranularity,
  filter: TimelineFilterState,
): EmsShippingTimelineParams {
  const params: EmsShippingTimelineParams = { granularity };
  if (filter.preset) {
    params.preset = filter.preset;
    return params;
  }
  if (granularity === 'year' && filter.year) {
    params.year = Number(filter.year);
    return params;
  }
  if (filter.dateFrom) params.date_from = filter.dateFrom;
  if (filter.dateTo) params.date_to = filter.dateTo;
  return params;
}

type TimelineBucketContext = {
  periodKey?: string;
  periodLabel?: string;
  recordsParams?: Omit<EmsShippingTimelineRecordsParams, 'bucket' | 'skip' | 'limit'>;
};

function buildTimelineRecordsQuery(
  granularity: EmsShippingTimelineGranularity,
  filter: TimelineFilterState,
  context: TimelineBucketContext | null,
  items: EmsShippingTimelineItem[] | undefined,
): Omit<EmsShippingTimelineRecordsParams, 'bucket' | 'skip' | 'limit'> {
  if (context?.recordsParams) {
    return { granularity, ...context.recordsParams };
  }
  if (context?.periodKey) {
    return { granularity, period_key: context.periodKey };
  }
  const filterParams = buildTimelineApiParams(granularity, filter);
  if (filterParams.preset || filterParams.year || filterParams.date_from || filterParams.date_to) {
    return {
      granularity,
      preset: filterParams.preset,
      year: filterParams.year,
      date_from: filterParams.date_from,
      date_to: filterParams.date_to,
    };
  }
  if (items?.length) {
    const starts = items.map((item) => item.period_start).sort();
    const ends = items.map((item) => item.period_end).sort();
    return {
      granularity,
      date_from: starts[0],
      date_to: ends[ends.length - 1],
    };
  }
  return { granularity };
}

function TimelineCountButton({
  count,
  onClick,
  className,
}: {
  count: number;
  onClick?: () => void;
  className?: string;
}) {
  if (count <= 0) {
    return <span className={`tabular-nums text-gray-400 ${className ?? ''}`}>0</span>;
  }
  if (!onClick) {
    return <span className={`tabular-nums ${className ?? ''}`}>{count.toLocaleString('vi-VN')}</span>;
  }
  return (
    <button
      type="button"
      onClick={onClick}
      className={`tabular-nums font-medium underline decoration-dotted underline-offset-2 hover:decoration-solid ${className ?? ''}`}
    >
      {count.toLocaleString('vi-VN')}
    </button>
  );
}

function TimelineCodCountCell({
  count,
  amount,
  onClick,
  className,
  amountClassName,
}: {
  count: number;
  amount: number;
  onClick?: () => void;
  className?: string;
  amountClassName?: string;
}) {
  return (
    <div className="flex flex-col items-end gap-0.5">
      <TimelineCountButton count={count} onClick={onClick} className={className} />
      <span
        className={`text-xs tabular-nums whitespace-nowrap ${amount > 0 ? amountClassName ?? 'text-gray-500' : 'text-gray-400'}`}
      >
        {formatVnd(amount)}
      </span>
    </div>
  );
}

function monthInputToDateRange(value: string): { from: string; to: string } | null {
  if (!/^\d{4}-\d{2}$/.test(value)) return null;
  const [year, month] = value.split('-').map(Number);
  const lastDay = new Date(year, month, 0).getDate();
  return {
    from: `${value}-01`,
    to: `${value}-${String(lastDay).padStart(2, '0')}`,
  };
}

function formatStaleSeconds(seconds?: number | null): string {
  if (seconds == null || seconds < 0) return '—';
  if (seconds < 60) return `${seconds} giây`;
  const mins = Math.floor(seconds / 60);
  if (mins < 60) return `${mins} phút`;
  const hours = Math.floor(mins / 60);
  const remMins = mins % 60;
  return remMins > 0 ? `${hours} giờ ${remMins} phút` : `${hours} giờ`;
}

const SYNC_LABELS: Record<string, string> = {
  matched: 'Khớp',
  in_progress: 'Đang xử lý',
  mismatch: 'Lệch trạng thái',
  unlinked: 'Chưa ghép đơn shop',
  order_not_found: 'Chưa ghép đơn shop',
  ems_not_found: 'Không tra được EMS',
  parse_error: 'Lỗi dữ liệu',
};

const ORDER_STATUS_TEXTS: Record<string, string> = {
  pending: 'Chờ xác nhận',
  waiting_deposit: 'Chờ đặt cọc',
  deposit_paid: 'Chờ gửi hàng',
  confirmed: 'Chờ gửi hàng',
  processing: 'Chờ gửi hàng',
  shipping: 'Chờ nhận hàng',
  delivered: 'Đã nhận hàng',
  completed: 'Đã đánh giá',
  returned: 'Đơn hoàn đã trả shop',
  cancelled: 'Đã hủy',
};

const ORDER_STATUS_BADGE: Record<string, string> = {
  pending: 'bg-gray-100 text-gray-800 border-gray-200',
  waiting_deposit: 'bg-amber-100 text-amber-900 border-amber-200',
  deposit_paid: 'bg-blue-100 text-blue-800 border-blue-200',
  confirmed: 'bg-blue-100 text-blue-800 border-blue-200',
  processing: 'bg-blue-100 text-blue-800 border-blue-200',
  shipping: 'bg-indigo-100 text-indigo-900 border-indigo-200',
  delivered: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  completed: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  cancelled: 'bg-red-100 text-red-800 border-red-200',
};

const TIMELINE_STEP_LABELS: Record<string, string> = {
  deposit_confirmed: 'Đã xác nhận đơn',
  tq_preparing: 'TQ chuẩn bị & đóng gói',
  tq_warehouse: 'Hàng về kho TQ',
  international_shipping: 'Vận chuyển quốc tế (TQ → VN)',
  at_customs: 'Thủ tục cửa khẩu',
  domestic_shipping: 'Hàng về shop đóng gói',
  awaiting_confirm: 'EMS đang giao — chờ bạn nhận hàng',
};

function orderStatusLabel(status: string | null | undefined): string {
  if (!status) return '—';
  return ORDER_STATUS_TEXTS[status] || status;
}

function emsShopOrderStatusLabel(row: EmsShippingImportRow): string {
  if (row.return_to_shop_label) return row.return_to_shop_label;
  if (!row.order_status) return '—';
  if (row.order_id && (row.reference_code || row.ems_reference_code)) {
    const st = row.order_status;
    if (st === 'shipping') return 'EMS đang giao tới bạn';
    if (st === 'delivered' || st === 'completed') return orderStatusLabel(st);
    if (st === 'deposit_paid' || st === 'confirmed' || st === 'processing') {
      return 'Đã gửi EMS';
    }
  }
  return orderStatusLabel(row.order_status);
}

function emsTimelineLabel(stepKey: string | null | undefined): string {
  if (!stepKey) return '—';
  return TIMELINE_STEP_LABELS[stepKey] || stepKey;
}

type ShipmentTimeline = Awaited<ReturnType<typeof adminOrderAPI.getOrderShipmentTimeline>>;

type OrderStatusModalState = {
  row: EmsShippingImportRow;
  loading: boolean;
  error: string | null;
  order: AdminOrder | null;
  timeline: ShipmentTimeline | null;
};

const SYNC_BADGE: Record<string, string> = {
  matched: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  in_progress: 'bg-blue-100 text-blue-800 border-blue-200',
  mismatch: 'bg-amber-100 text-amber-900 border-amber-200',
  unlinked: 'bg-slate-100 text-slate-800 border-slate-200',
  order_not_found: 'bg-slate-100 text-slate-800 border-slate-200',
  ems_not_found: 'bg-orange-100 text-orange-900 border-orange-200',
  parse_error: 'bg-gray-100 text-gray-800 border-gray-200',
};

const COD_RECONCILE_LABELS: Record<string, string> = {
  matched: 'Khớp tiền',
  amount_mismatch: 'Lệch tiền',
  record_not_found: 'Không có trong DB',
  parse_error: 'Lỗi dữ liệu',
};

const COD_RECONCILE_BADGE: Record<string, string> = {
  matched: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  amount_mismatch: 'bg-amber-100 text-amber-900 border-amber-200',
  record_not_found: 'bg-red-100 text-red-800 border-red-200',
  parse_error: 'bg-gray-100 text-gray-800 border-gray-200',
};

const FREIGHT_RECONCILE_LABELS: Record<string, string> = {
  settled: 'Đã đối soát',
  already_settled: 'Đã đối soát trước',
  record_not_found: 'Không có trong DB',
  parse_error: 'Lỗi dữ liệu',
};

const FREIGHT_RECONCILE_BADGE: Record<string, string> = {
  settled: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  already_settled: 'bg-orange-100 text-orange-900 border-orange-200',
  record_not_found: 'bg-red-100 text-red-800 border-red-200',
  parse_error: 'bg-gray-100 text-gray-800 border-gray-200',
};

type FilterKey = 'all' | EmsShippingImportRow['sync_status'];
type CodFilterKey = 'all' | EmsCodSettlementRow['reconcile_status'];
type FreightFilterKey = 'all' | EmsFreightSettlementRow['reconcile_status'];

function rowKey(row: EmsShippingImportRow): string {
  if (row.id != null) return String(row.id);
  return `${row.row_number}:${row.reference_code}:${row.order_code || ''}`;
}

function formatVnd(amount: number | null | undefined): string {
  if (amount == null || !Number.isFinite(amount)) return '—';
  return `${Math.round(amount).toLocaleString('vi-VN')} đ`;
}

function formatCodAmount(amount: number | null | undefined): string {
  if (amount == null || !Number.isFinite(amount)) return '—';
  if (amount === 0) return 'Không thu hộ (0 đ)';
  return formatVnd(amount);
}

function formatCodPaidDate(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const iso = /^(\d{4})-(\d{2})-(\d{2})/.exec(raw.trim());
  if (iso) return `${iso[3]}/${iso[2]}/${iso[1]}`;
  return raw.trim();
}

function formatCodPaidDisplay(row: EmsShippingImportRow): ReactNode {
  if ((row.cod_settlement_status || '').trim().toLowerCase() !== 'matched') {
    return '—';
  }
  const amount = row.cod_paid_amount ?? row.cod_amount ?? null;
  const paidDate = formatCodPaidDate(row.cod_paid_date);
  if (amount == null && !paidDate) return '—';
  return (
    <>
      <span>{formatVnd(amount)}</span>
      {paidDate ? (
        <span className="block text-xs text-emerald-700 mt-0.5 font-medium">EMS trả shop: {paidDate}</span>
      ) : null}
    </>
  );
}

function formatCodCollectedHint(row: EmsShippingImportRow): ReactNode {
  if ((row.cod_settlement_status || '').trim().toLowerCase() === 'matched') return null;
  if (!row.cod_amount || row.cod_amount <= 0) return null;
  const phase = (row.ems_phase || '').trim().toLowerCase();
  const status = (row.ems_status || '').toLowerCase();
  const collected =
    phase === 'cod_collected' ||
    phase === 'delivered' ||
    status.includes('phát thành công') ||
    status.includes('[cod]đã thu tiền') ||
    status.includes('đã thu tiền bưu tá');
  if (!collected) return null;
  return (
    <span className="block text-xs text-amber-800 mt-0.5 font-medium">
      EMS đã thu COD từ khách — chưa trả shop (chờ file đối soát)
    </span>
  );
}

const IMPORT_ACTION_LABELS: Record<string, string> = {
  created: 'Thêm mới',
  updated: 'Cập nhật',
};

const SHOP_RETURN_ROW_STATUS: Record<string, { label: string; badge: string }> = {
  confirmed: { label: 'Đã xác nhận', badge: 'bg-emerald-100 text-emerald-800 border-emerald-200' },
  not_found: { label: 'Không tìm thấy', badge: 'bg-red-100 text-red-800 border-red-200' },
  invalid_code: { label: 'Mã không hợp lệ', badge: 'bg-red-100 text-red-800 border-red-200' },
  already_returned: { label: 'Đã hoàn trước đó', badge: 'bg-amber-100 text-amber-900 border-amber-200' },
  invalid_status: { label: 'Trạng thái đơn không hợp lệ', badge: 'bg-amber-100 text-amber-900 border-amber-200' },
  ems_not_return: { label: 'EMS chưa báo hoàn', badge: 'bg-orange-100 text-orange-900 border-orange-200' },
  ems_not_linked: { label: 'Chưa có EMS', badge: 'bg-orange-100 text-orange-900 border-orange-200' },
  duplicate: { label: 'Trùng trong file', badge: 'bg-slate-100 text-slate-700 border-slate-200' },
};

function formatEmsImportBatchLabel(batch: EmsShippingImportBatch): string {
  const when = batch.created_at
    ? new Date(batch.created_at).toLocaleString('vi-VN', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : `#${batch.id}`;
  const file = batch.source_filename?.trim();
  const stats = `${batch.order_count.toLocaleString('vi-VN')} đơn · +${batch.created_count}/~${batch.updated_count}`;
  return file ? `${when} · ${file} · ${stats}` : `${when} · ${stats}`;
}

function EmsImportReportPanel({
  report,
  listExpanded,
  onToggleList,
  title = 'Báo cáo import',
}: {
  report: EmsShippingImportReport;
  listExpanded: boolean;
  onToggleList: () => void;
  title?: string;
}) {
  const listSummary = `${report.order_count.toLocaleString('vi-VN')} đơn · ${formatVnd(report.total_cod_amount)} COD · ${report.created} thêm · ${report.updated} cập nhật`;

  return (
    <div className="space-y-3 pt-1">
      <div className="bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-4 text-sm text-emerald-950">
        <p className="font-semibold text-emerald-900 mb-3">{title}</p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div>
            <div className="text-xs text-emerald-800/80 mb-1">Số đơn import</div>
            <TimelineCountButton
              count={report.order_count}
              onClick={report.order_count > 0 ? onToggleList : undefined}
              className="text-2xl text-emerald-900"
            />
            {report.order_count > 0 ? (
              <p className="text-xs text-emerald-700/80 mt-0.5">Bấm số để {listExpanded ? 'ẩn' : 'xem'} danh sách</p>
            ) : null}
          </div>
          <div>
            <div className="text-xs text-emerald-800/80 mb-1">Tổng COD</div>
            <div className="text-2xl font-semibold tabular-nums text-emerald-900">{formatVnd(report.total_cod_amount)}</div>
          </div>
          <div>
            <div className="text-xs text-emerald-800/80 mb-1">Thêm mới / Cập nhật</div>
            <div className="text-lg font-semibold tabular-nums">
              {report.created.toLocaleString('vi-VN')} / {report.updated.toLocaleString('vi-VN')}
            </div>
          </div>
          <div>
            <div className="text-xs text-emerald-800/80 mb-1">Đồng bộ đơn shop</div>
            <div className="text-lg font-semibold tabular-nums">{report.orders_synced.toLocaleString('vi-VN')}</div>
          </div>
        </div>
        {report.skipped_no_reference > 0 ? (
          <p className="text-xs text-amber-800 mt-3">
            {report.skipped_no_reference.toLocaleString('vi-VN')} dòng bỏ qua (thiếu mã vận đơn cột A).
          </p>
        ) : null}
      </div>

      {listExpanded && report.rows.length > 0 ? (
        <CollapsibleListPanel
          title="Danh sách đơn đã import"
          summary={listSummary}
          expanded
          onToggle={onToggleList}
        >
          <div className="overflow-x-auto rounded-xl border border-gray-200">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 text-gray-600">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">#</th>
                  <th className="px-3 py-2 text-left font-medium">Mã vận đơn</th>
                  <th className="px-3 py-2 text-left font-medium">Mã đơn shop</th>
                  <th className="px-3 py-2 text-left font-medium">Tên khách</th>
                  <th className="px-3 py-2 text-right font-medium">COD</th>
                  <th className="px-3 py-2 text-left font-medium">Thao tác</th>
                  <th className="px-3 py-2 text-left font-medium">Đối chiếu</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {report.rows.map((row: EmsShippingImportReportRow) => (
                  <tr key={rowKey(row)} className="hover:bg-gray-50/80">
                    <td className="px-3 py-2.5 text-gray-500 tabular-nums">{row.row_number || '—'}</td>
                    <td className="px-3 py-2.5 font-mono text-gray-900">{row.reference_code || '—'}</td>
                    <td className="px-3 py-2.5">
                      {row.order_code ? (
                        row.order_id ? (
                          <Link
                            href={`/admin/orders?q=${encodeURIComponent(row.order_code)}`}
                            className="text-emerald-700 hover:underline font-medium"
                          >
                            {row.order_code}
                          </Link>
                        ) : (
                          <span className="font-medium text-gray-800">{row.order_code}</span>
                        )
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-gray-700 max-w-[200px] truncate" title={row.recipient_label || ''}>
                      {row.recipient_label || '—'}
                    </td>
                    <td className="px-3 py-2.5 text-right tabular-nums font-medium">{formatCodAmount(row.cod_amount)}</td>
                    <td className="px-3 py-2.5">
                      <span
                        className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${
                          row.import_action === 'created'
                            ? 'bg-emerald-100 text-emerald-800 border-emerald-200'
                            : 'bg-sky-100 text-sky-800 border-sky-200'
                        }`}
                      >
                        {IMPORT_ACTION_LABELS[row.import_action || ''] || row.import_action || '—'}
                      </span>
                    </td>
                    <td className="px-3 py-2.5">
                      <span
                        className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${
                          SYNC_BADGE[row.sync_status] || SYNC_BADGE.parse_error
                        }`}
                      >
                        {SYNC_LABELS[row.sync_status] || row.sync_status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="bg-gray-50 font-semibold text-gray-900">
                <tr>
                  <td colSpan={4} className="px-3 py-2.5 text-right">
                    Tổng ({report.order_count} đơn)
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-emerald-800">
                    {formatVnd(report.total_cod_amount)}
                  </td>
                  <td colSpan={2} />
                </tr>
              </tfoot>
            </table>
          </div>
        </CollapsibleListPanel>
      ) : null}
    </div>
  );
}

function CollapsibleListPanel({
  title,
  summary,
  expanded,
  onToggle,
  children,
}: {
  title: string;
  summary: string;
  expanded: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <div className="pt-2 border-t border-gray-100">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="w-full flex items-start sm:items-center justify-between gap-3 rounded-lg px-2 py-2.5 text-left hover:bg-gray-50 transition"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex h-5 w-5 shrink-0 items-center justify-center text-gray-500 transition-transform ${
                expanded ? 'rotate-90' : ''
              }`}
              aria-hidden
            >
              ▶
            </span>
            <span className="text-base font-semibold text-gray-900">{title}</span>
          </div>
          {!expanded && summary ? (
            <p className="text-sm text-gray-500 mt-1 ml-7 line-clamp-2">{summary}</p>
          ) : null}
        </div>
        <span className="text-sm text-emerald-700 shrink-0 font-medium whitespace-nowrap">
          {expanded ? 'Thu gọn' : 'Mở rộng'}
        </span>
      </button>
      {expanded ? <div className="space-y-4 mt-2">{children}</div> : null}
    </div>
  );
}

function OpsStatCard({
  label,
  count,
  amount,
  color,
  active,
  onClick,
  compact = false,
}: {
  label: string;
  count: number;
  amount?: number;
  color: string;
  active: boolean;
  onClick: () => void;
  compact?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-xl border px-3 py-3 text-left transition hover:ring-2 hover:ring-emerald-100 w-full ${
        active ? 'border-emerald-500 ring-2 ring-emerald-100 bg-white' : 'border-gray-200 bg-gray-50'
      } ${compact ? 'py-2' : ''}`}
    >
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`${compact ? 'text-lg' : 'text-2xl'} font-semibold tabular-nums ${color}`}>
        {Number(count).toLocaleString('vi-VN')}
      </div>
      {amount !== undefined ? (
        <div className="text-xs tabular-nums text-gray-500 mt-0.5">{formatVnd(amount)}</div>
      ) : null}
    </button>
  );
}

function DetailField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-gray-500">{label}</dt>
      <dd className="mt-0.5 text-sm text-gray-900 break-words">{children}</dd>
    </div>
  );
}

function EmsSearchResultCard({
  row,
  onViewStatus,
  onRefresh,
  refreshing,
}: {
  row: EmsShippingImportRow;
  onViewStatus: (row: EmsShippingImportRow) => void;
  onRefresh?: (row: EmsShippingImportRow) => void;
  refreshing?: boolean;
}) {
  return (
    <article className="rounded-xl border border-emerald-200 bg-emerald-50/40 p-4 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="font-semibold text-gray-900 font-mono">{row.reference_code || '—'}</div>
          <div className="text-sm text-gray-600 mt-0.5">
            {row.order_code ? (
              row.order_id ? (
                <Link
                  href={`/admin/orders?q=${encodeURIComponent(row.order_code)}`}
                  className="text-emerald-700 hover:underline font-medium"
                >
                  {row.order_code}
                </Link>
              ) : (
                <span className="font-medium">{row.order_code}</span>
              )
            ) : (
              <span className="text-gray-500">Chưa có mã đơn shop</span>
            )}
          </div>
        </div>
        <span
          className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-medium ${
            SYNC_BADGE[row.sync_status] || SYNC_BADGE.parse_error
          }`}
        >
          {SYNC_LABELS[row.sync_status] || row.sync_status}
        </span>
      </div>

      <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-3">
        <DetailField label="Mã EMS">{row.ems_tracking_code || '—'}</DetailField>
        <DetailField label="Mã vận đơn shop (đã lưu)">{row.tracking_number_saved || '—'}</DetailField>
        <DetailField label="Thu hộ (COD)">{formatCodAmount(row.cod_amount)}</DetailField>
        <DetailField label="COD EMS trả shop">
          {formatCodPaidDisplay(row)}
          {formatCodCollectedHint(row)}
        </DetailField>
        <DetailField label="Cước EMS">{formatVnd(row.freight_amount)}</DetailField>
        <DetailField label="Trạng thái EMS">
          {row.ems_status || row.ems_error || '—'}
          {row.ems_phase ? ` (${row.ems_phase})` : ''}
        </DetailField>
        <DetailField label="Trạng thái đơn shop">
          {row.order_status ? emsShopOrderStatusLabel(row) : '—'}
        </DetailField>
        <DetailField label="Người nhận">
          <span className="line-clamp-2">{row.recipient_label || '—'}</span>
        </DetailField>
        {row.current_step_key ? (
          <DetailField label="Timeline shop">
            {emsTimelineLabel(row.current_step_key)}
          </DetailField>
        ) : null}
      </dl>

      {row.sync_message ? (
        <p className="text-xs text-gray-600 bg-white/70 rounded-lg px-3 py-2 border border-emerald-100">
          {row.sync_message}
        </p>
      ) : null}

      {row.order_code ? (
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => onViewStatus(row)}
            className="text-sm font-medium text-emerald-700 hover:text-emerald-900 hover:underline"
          >
            Xem chi tiết trạng thái đơn shop →
          </button>
          {row.id != null && onRefresh ? (
            <button
              type="button"
              onClick={() => onRefresh(row)}
              disabled={refreshing}
              className="text-sm font-medium text-indigo-700 hover:text-indigo-900 hover:underline disabled:opacity-50"
            >
              {refreshing ? 'Đang tra EMS…' : 'Tra lại EMS'}
            </button>
          ) : null}
        </div>
      ) : row.id != null && onRefresh ? (
        <button
          type="button"
          onClick={() => onRefresh(row)}
          disabled={refreshing}
          className="text-sm font-medium text-indigo-700 hover:text-indigo-900 hover:underline disabled:opacity-50"
        >
          {refreshing ? 'Đang tra EMS…' : 'Tra lại EMS'}
        </button>
      ) : null}
    </article>
  );
}

export default function AdminShippingPage() {
  const fileRef = useRef<HTMLInputElement>(null);
  const codFileRef = useRef<HTMLInputElement>(null);
  const freightFileRef = useRef<HTMLInputElement>(null);
  const shopReturnFileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [codFile, setCodFile] = useState<File | null>(null);
  const [freightFile, setFreightFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [codLoading, setCodLoading] = useState(false);
  const [freightLoading, setFreightLoading] = useState(false);
  const [listLoading, setListLoading] = useState(true);
  const [codListLoading, setCodListLoading] = useState(true);
  const [freightListLoading, setFreightListLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [codError, setCodError] = useState<string | null>(null);
  const [freightError, setFreightError] = useState<string | null>(null);
  const [result, setResult] = useState<EmsShippingImportResult | null>(null);
  const [codResult, setCodResult] = useState<EmsCodSettlementImportResult | null>(null);
  const [freightResult, setFreightResult] = useState<EmsFreightSettlementImportResult | null>(null);
  const [filter, setFilter] = useState<FilterKey>('all');
  const [listPage, setListPage] = useState(1);
  const [listPageSize, setListPageSize] = useState<number>(EMS_LIST_DEFAULT_PAGE_SIZE);
  const [searchInput, setSearchInput] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [codFilter, setCodFilter] = useState<CodFilterKey>('all');
  const [freightFilter, setFreightFilter] = useState<FreightFilterKey>('all');
  const [selectedBatchId, setSelectedBatchId] = useState<number | null>(null);
  const [selectedFreightBatchId, setSelectedFreightBatchId] = useState<number | null>(null);
  const [codListExpanded, setCodListExpanded] = useState(false);
  const [freightListExpanded, setFreightListExpanded] = useState(false);
  const [shopReturnText, setShopReturnText] = useState('');
  const [shopReturnFile, setShopReturnFile] = useState<File | null>(null);
  const [shopReturnLoading, setShopReturnLoading] = useState(false);
  const [shopReturnError, setShopReturnError] = useState<string | null>(null);
  const [shopReturnResult, setShopReturnResult] = useState<ShopReturnConfirmResult | null>(null);
  const [shopReturnListExpanded, setShopReturnListExpanded] = useState(true);
  const [emsTableExpanded, setEmsTableExpanded] = useState(true);
  const [importReportListExpanded, setImportReportListExpanded] = useState(false);
  const [emsImportBatches, setEmsImportBatches] = useState<EmsShippingImportBatchesResult | null>(null);
  const [emsImportBatchesLoading, setEmsImportBatchesLoading] = useState(true);
  const [selectedEmsImportBatchId, setSelectedEmsImportBatchId] = useState<number | null>(null);
  const [opsStats, setOpsStats] = useState<EmsShippingOperationsStats | null>(null);
  const [opsStatsLoading, setOpsStatsLoading] = useState(true);
  const [opsStatsError, setOpsStatsError] = useState<string | null>(null);
  const [timelineGranularity, setTimelineGranularity] = useState<EmsShippingTimelineGranularity>('month');
  const [timelineFilter, setTimelineFilter] = useState<TimelineFilterState>(EMPTY_TIMELINE_FILTER);
  const [timelineMonthPick, setTimelineMonthPick] = useState('');
  const [timelineStats, setTimelineStats] = useState<EmsShippingTimelineStats | null>(null);
  const [timelineLoading, setTimelineLoading] = useState(true);
  const [timelineError, setTimelineError] = useState<string | null>(null);
  const [activeOpsBucket, setActiveOpsBucket] = useState<OpsBucketKey | null>(null);
  const [opsBucketLabel, setOpsBucketLabel] = useState('');
  const [opsBucketRows, setOpsBucketRows] = useState<EmsShippingImportRow[]>([]);
  const [opsBucketTotal, setOpsBucketTotal] = useState(0);
  const [opsBucketPage, setOpsBucketPage] = useState(1);
  const [opsBucketLoading, setOpsBucketLoading] = useState(false);
  const [opsBucketError, setOpsBucketError] = useState<string | null>(null);
  const [timelineBucketContext, setTimelineBucketContext] = useState<TimelineBucketContext | null>(null);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [deleteConfirmKeys, setDeleteConfirmKeys] = useState<string[] | null>(null);
  const [orderStatusModal, setOrderStatusModal] = useState<OrderStatusModalState | null>(null);
  const [trackingJob, setTrackingJob] = useState<EmsTrackingRefreshJob | null>(null);
  const [trackingResumeLoading, setTrackingResumeLoading] = useState(false);
  const [refreshingEms, setRefreshingEms] = useState(false);
  const trackingPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const trackingLastProcessedRef = useRef(0);

  const loadRecords = useCallback(async (options?: { silent?: boolean }) => {
    const silent = options?.silent ?? false;
    if (!silent) {
      setListLoading(true);
      setError(null);
    }
    try {
      const skip = (listPage - 1) * listPageSize;
      const data = await adminShippingAPI.listEmsRecords({
        skip,
        limit: listPageSize,
        sync_status: filter === 'all' ? undefined : filter,
        q: appliedSearch.trim() || undefined,
      });
      const filteredTotal = data.pagination?.filtered_total ?? data.rows.length;
      const maxPage = Math.max(1, Math.ceil(filteredTotal / listPageSize));
      if (filteredTotal > 0 && listPage > maxPage) {
        setListPage(maxPage);
        return;
      }
      setResult(data);
    } catch (err) {
      if (!silent) {
        setError(err instanceof Error ? err.message : 'Không tải được bảng vận chuyển');
      }
    } finally {
      if (!silent) {
        setListLoading(false);
      }
    }
  }, [appliedSearch, filter, listPage, listPageSize]);

  const loadEmsImportBatches = useCallback(async () => {
    setEmsImportBatchesLoading(true);
    try {
      const data = await adminShippingAPI.listEmsImportBatches(30);
      setEmsImportBatches(data);
      setSelectedEmsImportBatchId((prev) => {
        if (prev != null && data.batches.some((b) => b.id === prev)) return prev;
        return data.batches[0]?.id ?? null;
      });
    } catch {
      /* im lặng — báo cáo cũ không chặn trang */
    } finally {
      setEmsImportBatchesLoading(false);
    }
  }, []);

  const loadCodSettlements = useCallback(async () => {
    setCodListLoading(true);
    setCodError(null);
    try {
      const data = await adminCodSettlementAPI.listBatches();
      setCodResult(data);
      setSelectedBatchId((prev) => {
        if (prev != null && data.batches.some((b) => b.id === prev)) return prev;
        return data.batches[0]?.id ?? null;
      });
    } catch (err) {
      setCodError(err instanceof Error ? err.message : 'Không tải được đối soát COD');
    } finally {
      setCodListLoading(false);
    }
  }, []);

  const loadFreightSettlements = useCallback(async () => {
    setFreightListLoading(true);
    setFreightError(null);
    try {
      const data = await adminFreightSettlementAPI.listBatches();
      setFreightResult(data);
      setSelectedFreightBatchId((prev) => {
        if (prev != null && data.batches.some((b) => b.id === prev)) return prev;
        return data.batches[0]?.id ?? null;
      });
    } catch (err) {
      setFreightError(err instanceof Error ? err.message : 'Không tải được đối soát cước');
    } finally {
      setFreightListLoading(false);
    }
  }, []);

  const loadTimelineStats = useCallback(
    async (
      granularity: EmsShippingTimelineGranularity,
      filter: TimelineFilterState = timelineFilter,
    ) => {
      setTimelineLoading(true);
      setTimelineError(null);
      try {
        const data = await adminShippingAPI.getTimelineStats(buildTimelineApiParams(granularity, filter));
        setTimelineStats(data);
      } catch (err) {
        setTimelineError(err instanceof Error ? err.message : 'Không tải được thống kê theo thời gian');
      } finally {
        setTimelineLoading(false);
      }
    },
    [timelineFilter],
  );

  const loadOpsStats = useCallback(async (options?: { silent?: boolean }) => {
    const silent = options?.silent ?? false;
    if (!silent) {
      setOpsStatsLoading(true);
      setTimelineLoading(true);
      setOpsStatsError(null);
      setTimelineError(null);
    }
    const timelineParams = buildTimelineApiParams(timelineGranularity, timelineFilter);
    const [opsResult, timelineResult] = await Promise.allSettled([
      adminShippingAPI.getOperationsStats(),
      adminShippingAPI.getTimelineStats(timelineParams),
    ]);
    if (opsResult.status === 'fulfilled') {
      setOpsStats(opsResult.value);
      if (!silent) setOpsStatsError(null);
    } else if (!silent) {
      setOpsStats(null);
      setOpsStatsError(
        opsResult.reason instanceof Error ? opsResult.reason.message : 'Không tải được tổng quan vận hành',
      );
    }
    if (timelineResult.status === 'fulfilled') {
      setTimelineStats(timelineResult.value);
      if (!silent) setTimelineError(null);
    } else if (!silent) {
      setTimelineStats(null);
      setTimelineError(
        timelineResult.reason instanceof Error
          ? timelineResult.reason.message
          : 'Không tải được thống kê theo thời gian',
      );
    }
    if (!silent) {
      setOpsStatsLoading(false);
      setTimelineLoading(false);
    }
  }, [timelineFilter, timelineGranularity]);

  const loadOpsBucketRecords = useCallback(
    async (bucket: OpsBucketKey, page: number, context?: TimelineBucketContext | null) => {
      setOpsBucketLoading(true);
      setOpsBucketError(null);
      try {
        const skip = (page - 1) * OPS_LIST_PAGE_SIZE;
        const timelineContext = context === undefined ? timelineBucketContext : context;
        const data = timelineContext
          ? await adminShippingAPI.listTimelineRecords({
              bucket,
              skip,
              limit: OPS_LIST_PAGE_SIZE,
              ...buildTimelineRecordsQuery(
                timelineGranularity,
                timelineFilter,
                timelineContext,
                timelineStats?.items,
              ),
            })
          : await adminShippingAPI.listOperationsRecords({
              bucket,
              skip,
              limit: OPS_LIST_PAGE_SIZE,
            });
        setActiveOpsBucket(bucket);
        setOpsBucketLabel(data.bucket_label);
        setOpsBucketRows(data.rows);
        setOpsBucketTotal(data.pagination.filtered_total ?? data.rows.length);
        setOpsBucketPage(page);
      } catch (err) {
        setOpsBucketError(err instanceof Error ? err.message : 'Không tải được danh sách');
        setOpsBucketRows([]);
      } finally {
        setOpsBucketLoading(false);
      }
    },
    [timelineBucketContext, timelineFilter, timelineGranularity, timelineStats?.items],
  );

  const closeOpsBucketModal = useCallback(() => {
    setActiveOpsBucket(null);
    setTimelineBucketContext(null);
    setOpsBucketRows([]);
    setOpsBucketError(null);
    setOpsBucketPage(1);
  }, []);

  const openOpsBucket = useCallback(
    (bucket: OpsBucketKey, label: string) => {
      setTimelineBucketContext(null);
      setOpsBucketLabel(label);
      setActiveOpsBucket(bucket);
      void loadOpsBucketRecords(bucket, 1, null);
    },
    [loadOpsBucketRecords],
  );

  const openTimelineBucket = useCallback(
    (item: EmsShippingTimelineItem, bucket: OpsBucketKey) => {
      const context: TimelineBucketContext = {
        periodKey: item.period_key,
        periodLabel: item.period_label,
      };
      setTimelineBucketContext(context);
      setOpsBucketLabel(`${TIMELINE_BUCKET_LABELS[bucket]} — ${item.period_label}`);
      setActiveOpsBucket(bucket);
      void loadOpsBucketRecords(bucket, 1, context);
    },
    [loadOpsBucketRecords],
  );

  const openTimelineBucketTotals = useCallback(
    (bucket: OpsBucketKey) => {
      const context: TimelineBucketContext = {
        periodLabel: timelineStats?.filter_label || 'Tổng các kỳ hiển thị',
        recordsParams: buildTimelineRecordsQuery(
          timelineGranularity,
          timelineFilter,
          null,
          timelineStats?.items,
        ),
      };
      setTimelineBucketContext(context);
      setOpsBucketLabel(`${TIMELINE_BUCKET_LABELS[bucket]} — ${context.periodLabel}`);
      setActiveOpsBucket(bucket);
      void loadOpsBucketRecords(bucket, 1, context);
    },
    [loadOpsBucketRecords, timelineFilter, timelineGranularity, timelineStats?.filter_label, timelineStats?.items],
  );

  const opsBucketTotalPages = Math.max(1, Math.ceil(opsBucketTotal / OPS_LIST_PAGE_SIZE));

  const stopTrackingPoll = useCallback(() => {
    if (trackingPollRef.current) {
      clearInterval(trackingPollRef.current);
      trackingPollRef.current = null;
    }
  }, []);

  const startTrackingPoll = useCallback(
    (jobId: string) => {
      stopTrackingPoll();
      trackingLastProcessedRef.current = 0;
      if (typeof window !== 'undefined') {
        sessionStorage.setItem(EMS_TRACKING_JOB_STORAGE_KEY, jobId);
      }
      const poll = async () => {
        try {
          const job = await adminShippingAPI.getEmsTrackingRefreshJob(jobId);
          setTrackingJob(job);
          if (job.processed !== trackingLastProcessedRef.current) {
            trackingLastProcessedRef.current = job.processed;
            void loadOpsStats({ silent: true });
            void loadRecords({ silent: true });
          }
          if (job.status === 'completed' || job.status === 'failed') {
            stopTrackingPoll();
            if (typeof window !== 'undefined') {
              sessionStorage.removeItem(EMS_TRACKING_JOB_STORAGE_KEY);
            }
            await loadRecords({ silent: true });
            await loadOpsStats({ silent: true });
          }
        } catch {
          /* thử lại lần poll sau */
        }
      };
      void poll();
      trackingPollRef.current = setInterval(() => void poll(), 2500);
    },
    [loadOpsStats, loadRecords, stopTrackingPoll],
  );

  const runEmsTrackingRefresh = useCallback(
    async (payload: {
      ids?: number[];
      q?: string;
      sync_status?: string;
      non_terminal_only?: boolean;
    }) => {
      setRefreshingEms(true);
      setError(null);
      try {
        const data = await adminShippingAPI.enqueueEmsTrackingRefresh(payload);
        if (data.job_id) {
          startTrackingPoll(data.job_id);
        } else if (data.queued === 0 && payload.non_terminal_only) {
          setError(null);
        } else {
          setError(data.message || 'Không khởi chạy được tra EMS.');
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Không thể tra lại EMS');
      } finally {
        setRefreshingEms(false);
      }
    },
    [startTrackingPoll],
  );

  const refreshEmsRow = useCallback(
    (row: EmsShippingImportRow) => {
      if (row.id == null) return;
      void runEmsTrackingRefresh({ ids: [row.id] });
    },
    [runEmsTrackingRefresh],
  );

  const resumeTrackingJob = useCallback(async () => {
    if (!trackingJob?.job_id) return;
    setTrackingResumeLoading(true);
    setError(null);
    try {
      const job = await adminShippingAPI.resumeEmsTrackingRefreshJob(trackingJob.job_id);
      setTrackingJob(job);
      if (job.resume_ok) {
        startTrackingPoll(job.job_id);
      } else {
        setError(job.resume_message || 'Không thể tiếp tục job tra EMS trên server.');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thể tiếp tục job tra EMS');
    } finally {
      setTrackingResumeLoading(false);
    }
  }, [startTrackingPoll, trackingJob?.job_id]);

  useEffect(() => () => stopTrackingPoll(), [stopTrackingPoll]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const savedJobId = sessionStorage.getItem(EMS_TRACKING_JOB_STORAGE_KEY);
    if (savedJobId) {
      startTrackingPoll(savedJobId);
      return;
    }
    void (async () => {
      const active = await adminShippingAPI.getActiveEmsTrackingRefreshJob();
      if (active?.job_id) {
        startTrackingPoll(active.job_id);
      }
    })();
  }, [startTrackingPoll]);

  useEffect(() => {
    void loadRecords();
    void loadEmsImportBatches();
    void loadCodSettlements();
    void loadFreightSettlements();
    void loadOpsStats();
  }, [loadRecords, loadEmsImportBatches, loadCodSettlements, loadFreightSettlements, loadOpsStats]);

  const selectTimelineGranularity = useCallback(
    (granularity: EmsShippingTimelineGranularity) => {
      const nextFilter = { ...EMPTY_TIMELINE_FILTER };
      setTimelineGranularity(granularity);
      setTimelineFilter(nextFilter);
      setTimelineMonthPick('');
      void loadTimelineStats(granularity, nextFilter);
    },
    [loadTimelineStats],
  );

  const applyTimelinePreset = useCallback(
    (preset: EmsShippingTimelinePreset) => {
      const nextFilter: TimelineFilterState = { ...EMPTY_TIMELINE_FILTER, preset };
      setTimelineFilter(nextFilter);
      setTimelineMonthPick('');
      void loadTimelineStats(timelineGranularity, nextFilter);
    },
    [loadTimelineStats, timelineGranularity],
  );

  const applyTimelineDateRange = useCallback(
    (dateFrom: string, dateTo: string) => {
      const nextFilter: TimelineFilterState = {
        ...EMPTY_TIMELINE_FILTER,
        dateFrom,
        dateTo: dateTo || dateFrom,
      };
      setTimelineFilter(nextFilter);
      void loadTimelineStats(timelineGranularity, nextFilter);
    },
    [loadTimelineStats, timelineGranularity],
  );

  const applyTimelineYear = useCallback(
    (year: string) => {
      const nextFilter: TimelineFilterState = { ...EMPTY_TIMELINE_FILTER, year };
      setTimelineFilter(nextFilter);
      void loadTimelineStats('year', nextFilter);
    },
    [loadTimelineStats],
  );

  const clearTimelineFilter = useCallback(() => {
    const nextFilter = { ...EMPTY_TIMELINE_FILTER };
    setTimelineFilter(nextFilter);
    setTimelineMonthPick('');
    void loadTimelineStats(timelineGranularity, nextFilter);
  }, [loadTimelineStats, timelineGranularity]);

  const applyFilter = useCallback((next: FilterKey) => {
    setFilter(next);
    setListPage(1);
    setSelectedKeys(new Set());
  }, []);

  const submitSearch = useCallback(
    (e?: FormEvent) => {
      e?.preventDefault();
      const next = searchInput.trim();
      setAppliedSearch(next);
      setListPage(1);
      setSelectedKeys(new Set());
      if (next) {
        void runEmsTrackingRefresh({ q: next, non_terminal_only: true });
      }
    },
    [runEmsTrackingRefresh, searchInput],
  );

  const clearSearch = useCallback(() => {
    setSearchInput('');
    setAppliedSearch('');
    setListPage(1);
    setSelectedKeys(new Set());
  }, []);

  const pageRows = result?.rows ?? [];

  const listPagination = result?.pagination;
  const filteredTotal = listPagination?.filtered_total ?? pageRows.length;
  const totalRows = listPagination?.total ?? result?.summary.total_rows ?? 0;
  const totalPages = Math.max(1, Math.ceil(filteredTotal / listPageSize));
  const displayFrom = filteredTotal === 0 ? 0 : (listPage - 1) * listPageSize + 1;
  const displayTo = Math.min(listPage * listPageSize, filteredTotal);

  const pageKeyList = useMemo(() => pageRows.map(rowKey), [pageRows]);

  const allPageSelected =
    pageKeyList.length > 0 && pageKeyList.every((key) => selectedKeys.has(key));

  const somePageSelected = pageKeyList.some((key) => selectedKeys.has(key));

  const selectedRecordIds = useMemo(
    () =>
      pageRows
        .filter((row) => selectedKeys.has(rowKey(row)) && row.id != null)
        .map((row) => row.id as number),
    [pageRows, selectedKeys],
  );

  const runManualEmsRefresh = useCallback(() => {
    if (selectedRecordIds.length > 0) {
      void runEmsTrackingRefresh({ ids: selectedRecordIds });
      return;
    }
    if (appliedSearch.trim()) {
      void runEmsTrackingRefresh({ q: appliedSearch.trim() });
      return;
    }
    if (filter !== 'all') {
      void runEmsTrackingRefresh({ sync_status: filter });
      return;
    }
    setError('Chọn dòng, nhập mã tra cứu, hoặc chọn bộ lọc trạng thái trước khi tra EMS.');
  }, [appliedSearch, filter, runEmsTrackingRefresh, selectedRecordIds]);

  const activeEmsImportBatch = useMemo(() => {
    if (!emsImportBatches?.batches.length) return null;
    if (selectedEmsImportBatchId != null) {
      return (
        emsImportBatches.batches.find((b) => b.id === selectedEmsImportBatchId) ??
        emsImportBatches.batches[0]
      );
    }
    return emsImportBatches.batches[0];
  }, [emsImportBatches, selectedEmsImportBatchId]);

  const activeEmsImportReport = activeEmsImportBatch?.import_report ?? null;

  const activeCodBatch = useMemo(() => {
    if (!codResult?.batches.length) return null;
    if (selectedBatchId != null) {
      return codResult.batches.find((b) => b.id === selectedBatchId) ?? codResult.batches[0];
    }
    return codResult.batches[0];
  }, [codResult, selectedBatchId]);

  const filteredCodRows = useMemo(() => {
    if (!activeCodBatch) return [];
    if (codFilter === 'all') return activeCodBatch.rows;
    return activeCodBatch.rows.filter((row) => row.reconcile_status === codFilter);
  }, [activeCodBatch, codFilter]);

  const codSummary = useMemo(() => {
    if (activeCodBatch) {
      return {
        total_rows: activeCodBatch.total_rows,
        matched: activeCodBatch.matched_count,
        amount_mismatch: activeCodBatch.amount_mismatch_count,
        record_not_found: activeCodBatch.record_not_found_count,
        parse_error: activeCodBatch.parse_error_count,
        total_paid_amount: activeCodBatch.total_paid_amount,
        total_db_cod_amount: activeCodBatch.total_db_cod_amount,
        total_amount_difference: activeCodBatch.total_amount_difference,
      };
    }
    return codResult?.summary ?? null;
  }, [activeCodBatch, codResult]);

  const activeFreightBatch = useMemo(() => {
    if (!freightResult?.batches.length) return null;
    if (selectedFreightBatchId != null) {
      return freightResult.batches.find((b) => b.id === selectedFreightBatchId) ?? freightResult.batches[0];
    }
    return freightResult.batches[0];
  }, [freightResult, selectedFreightBatchId]);

  const filteredFreightRows = useMemo(() => {
    if (!activeFreightBatch) return [];
    if (freightFilter === 'all') return activeFreightBatch.rows;
    return activeFreightBatch.rows.filter((row) => row.reconcile_status === freightFilter);
  }, [activeFreightBatch, freightFilter]);

  const freightSummary = useMemo(() => {
    if (activeFreightBatch) {
      return {
        total_rows: activeFreightBatch.total_rows,
        settled: activeFreightBatch.settled_count,
        already_settled: activeFreightBatch.already_settled_count,
        record_not_found: activeFreightBatch.record_not_found_count,
        parse_error: activeFreightBatch.parse_error_count,
        high_fee_warning_count: activeFreightBatch.high_fee_warning_count,
        total_freight_amount: activeFreightBatch.total_freight_amount,
      };
    }
    return freightResult?.summary ?? null;
  }, [activeFreightBatch, freightResult]);

  const codListCollapseSummary = useMemo(() => {
    if (!codSummary) return '';
    return `${codSummary.total_rows.toLocaleString('vi-VN')} mã · ${codSummary.matched.toLocaleString('vi-VN')} khớp · ${codSummary.amount_mismatch.toLocaleString('vi-VN')} lệch · ${formatVnd(codSummary.total_paid_amount)} đã trả`;
  }, [codSummary]);

  const freightListCollapseSummary = useMemo(() => {
    if (!freightSummary) return '';
    return `${freightSummary.total_rows.toLocaleString('vi-VN')} mã · ${freightSummary.settled.toLocaleString('vi-VN')} đối soát · ${formatVnd(freightSummary.total_freight_amount)} tổng cước`;
  }, [freightSummary]);

  const runImport = useCallback(async () => {
    if (!file) {
      setError('Chọn file Excel trước.');
      return;
    }
    setLoading(true);
    setError(null);
    setDeleteConfirmKeys(null);
    try {
      const data = await adminShippingAPI.importEmsExcel(file);
      setListPage(1);
      setFilter('all');
      setSearchInput('');
      setAppliedSearch('');
      setSelectedKeys(new Set());
      setResult(data);
      if (data.batches?.length) {
        setEmsImportBatches({ ok: true, batches: data.batches, import_batch: data.import_batch ?? data.batches[0] });
        setSelectedEmsImportBatchId(data.import_batch?.id ?? data.batches[0]?.id ?? null);
      } else {
        await loadEmsImportBatches();
      }
      setImportReportListExpanded(true);
      setEmsTableExpanded(true);
      if (data.tracking_refresh_job_id) {
        startTrackingPoll(data.tracking_refresh_job_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import thất bại');
    } finally {
      setLoading(false);
    }
  }, [file, loadEmsImportBatches, startTrackingPoll]);

  const runCodImport = useCallback(async () => {
    if (!codFile) {
      setCodError('Chọn file đối soát COD trước.');
      return;
    }
    setCodLoading(true);
    setCodError(null);
    try {
      const data = await adminCodSettlementAPI.importExcel(codFile);
      setCodResult(data);
      setSelectedBatchId(data.import_batch?.id ?? data.batches[0]?.id ?? null);
      setCodFilter('all');
      setCodListExpanded(true);
      await loadRecords();
      await loadOpsStats();
    } catch (err) {
      setCodError(err instanceof Error ? err.message : 'Import đối soát COD thất bại');
    } finally {
      setCodLoading(false);
    }
  }, [codFile, loadRecords, loadOpsStats]);

  const runShopReturnConfirm = useCallback(async () => {
    const text = shopReturnText.trim();
    if (!text && !shopReturnFile) {
      setShopReturnError('Nhập mã đơn (DHxxx) hoặc chọn file Excel.');
      return;
    }
    setShopReturnLoading(true);
    setShopReturnError(null);
    try {
      let data: ShopReturnConfirmResult;
      if (shopReturnFile) {
        data = await adminShippingAPI.confirmShopReturnsExcel(shopReturnFile);
      } else {
        data = await adminShippingAPI.confirmShopReturns({ text });
      }
      setShopReturnResult(data);
      setShopReturnListExpanded(true);
      if (data.confirmed_count > 0) {
        await loadRecords({ silent: true });
        await loadOpsStats();
      }
    } catch (err) {
      setShopReturnError(err instanceof Error ? err.message : 'Xác nhận hoàn thất bại');
    } finally {
      setShopReturnLoading(false);
    }
  }, [shopReturnFile, shopReturnText, loadRecords, loadOpsStats]);

  const runFreightImport = useCallback(async () => {
    if (!freightFile) {
      setFreightError('Chọn file đối soát cước trước.');
      return;
    }
    setFreightLoading(true);
    setFreightError(null);
    try {
      const data = await adminFreightSettlementAPI.importExcel(freightFile);
      setFreightResult(data);
      setSelectedFreightBatchId(data.import_batch?.id ?? data.batches[0]?.id ?? null);
      setFreightFilter('all');
      setFreightListExpanded(true);
      await loadRecords();
      await loadOpsStats();
    } catch (err) {
      setFreightError(err instanceof Error ? err.message : 'Import đối soát cước thất bại');
    } finally {
      setFreightLoading(false);
    }
  }, [freightFile, loadRecords, loadOpsStats]);

  const toggleRow = (key: string, checked: boolean) => {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (checked) next.add(key);
      else next.delete(key);
      return next;
    });
  };

  const toggleAllFiltered = () => {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (allPageSelected) {
        pageKeyList.forEach((key) => next.delete(key));
      } else {
        pageKeyList.forEach((key) => next.add(key));
      }
      return next;
    });
  };

  const requestDelete = (keys: string[]) => {
    if (!keys.length) return;
    setDeleteConfirmKeys(keys);
  };

  const confirmDelete = async () => {
    if (!deleteConfirmKeys?.length) {
      setDeleteConfirmKeys(null);
      return;
    }
    const ids = deleteConfirmKeys
      .map((key) => Number(key))
      .filter((id) => Number.isFinite(id) && id > 0);
    if (!ids.length) {
      setError('Không xác định được dòng cần xóa. Tải lại trang và thử lại.');
      setDeleteConfirmKeys(null);
      return;
    }

    setDeleting(true);
    setError(null);
    try {
      await adminShippingAPI.deleteEmsRecords(ids);
      setDeleteConfirmKeys(null);
      setSelectedKeys(new Set());
      await loadRecords();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Xóa thất bại');
    } finally {
      setDeleting(false);
    }
  };

  const deletePreviewRows = useMemo(() => {
    if (!result || !deleteConfirmKeys?.length) return [];
    const keySet = new Set(deleteConfirmKeys);
    return result.rows.filter((row) => keySet.has(rowKey(row)));
  }, [result, deleteConfirmKeys]);

  const openOrderStatusModal = useCallback(async (row: EmsShippingImportRow) => {
    if (!row.order_code?.trim()) {
      setOrderStatusModal({
        row,
        loading: false,
        error: 'Dòng này không có mã đơn shop (DHxxx).',
        order: null,
        timeline: null,
      });
      return;
    }

    setOrderStatusModal({ row, loading: true, error: null, order: null, timeline: null });
    try {
      const order = await adminOrderAPI.lookupOrderByCode(row.order_code);
      const timeline = await adminOrderAPI.getOrderShipmentTimeline(order.id);
      setOrderStatusModal({
        row,
        loading: false,
        error: null,
        order,
        timeline,
      });
    } catch (err) {
      setOrderStatusModal({
        row,
        loading: false,
        error: err instanceof Error ? err.message : 'Không tải được trạng thái đơn',
        order: null,
        timeline: null,
      });
    }
  }, []);

  const showTable = result != null;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">
      <div>
        <p className="text-sm text-gray-500">
          <Link href="/admin/orders" className="text-emerald-700 hover:underline">
            ← Đơn hàng
          </Link>
        </p>
        <h1 className="text-2xl font-bold text-gray-900 mt-2">Quản lý vận chuyển EMS</h1>
        <p className="mt-1 text-sm text-gray-600">
          Import file <strong>gui ems.xlsx</strong>: cột <strong>D</strong> mã tham chiếu, cột <strong>J</strong> tên người nhận
          (tách <code>DHxxx</code>), cột <strong>P (TONG_TIEN_THU_HO)</strong> tổng tiền thu hộ.
          Khi khớp mã đơn shop, timeline cập nhật <strong>「Shop đã gửi EMS giao hàng」</strong>.
        </p>
      </div>

      <section className="bg-white border border-gray-200 rounded-xl p-4 sm:p-5 shadow-sm">
        <h2 className="text-base font-semibold text-gray-900">Tra cứu vận đơn</h2>
        <p className="mt-1 text-sm text-gray-500">
          Tìm theo <strong>mã đơn shop</strong> (DH/DC), <strong>mã tham chiếu</strong> (cột A file EMS),{' '}
          <strong>mã EMS</strong> hoặc mã vận đơn đã lưu trên đơn shop. Nếu đơn{' '}
          <strong>chưa giao / chưa thu COD xong</strong>, hệ thống tự tra EMS ngay.
        </p>
        <form onSubmit={submitSearch} className="mt-3 flex flex-col sm:flex-row gap-2">
          <input
            type="search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="VD: DH033, H19052609, EH044086535VN, DC37667…"
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
            aria-label="Tra cứu mã đơn, mã tham chiếu hoặc mã EMS"
          />
          <div className="flex gap-2 shrink-0">
            <button
              type="submit"
              disabled={listLoading || refreshingEms}
              className="rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {refreshingEms && appliedSearch === searchInput.trim() ? 'Đang tra EMS…' : 'Tra cứu'}
            </button>
            {appliedSearch ? (
              <button
                type="button"
                onClick={() => void runEmsTrackingRefresh({ q: appliedSearch })}
                disabled={refreshingEms || listLoading}
                className="rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-2.5 text-sm font-medium text-indigo-800 hover:bg-indigo-100 disabled:opacity-50"
              >
                Tra lại EMS
              </button>
            ) : null}
            {appliedSearch ? (
              <button
                type="button"
                onClick={clearSearch}
                disabled={listLoading}
                className="rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >
                Xóa lọc
              </button>
            ) : null}
          </div>
        </form>
        {appliedSearch ? (
          <div className="mt-4 border-t border-gray-100 pt-4">
            {listLoading && !result ? (
              <p className="text-sm text-gray-500 py-2">
                Đang tra cứu «{appliedSearch}»{refreshingEms ? ' và kiểm tra EMS mới nhất…' : '…'}
              </p>
            ) : pageRows.length === 0 ? (
              <div className="rounded-lg bg-gray-50 border border-gray-200 px-4 py-3 text-sm text-gray-600">
                Không tìm thấy dòng nào khớp <strong className="font-mono text-gray-900">{appliedSearch}</strong>.
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-sm text-gray-700">
                  <strong>{filteredTotal}</strong> kết quả cho{' '}
                  <strong className="font-mono text-emerald-800">{appliedSearch}</strong>
                  {filteredTotal > EMS_SEARCH_PREVIEW_LIMIT
                    ? ` · hiển thị ${EMS_SEARCH_PREVIEW_LIMIT} dòng đầu`
                    : null}
                </p>
                {pageRows.slice(0, EMS_SEARCH_PREVIEW_LIMIT).map((row) => (
                  <EmsSearchResultCard
                    key={rowKey(row)}
                    row={row}
                    onViewStatus={(r) => void openOrderStatusModal(r)}
                    onRefresh={refreshEmsRow}
                    refreshing={refreshingEms}
                  />
                ))}
                {filteredTotal > EMS_SEARCH_PREVIEW_LIMIT ? (
                  <p className="text-sm text-gray-500">
                    Còn {filteredTotal - EMS_SEARCH_PREVIEW_LIMIT} dòng — xem trong{' '}
                    <a href="#ems-shipping-table" className="text-emerald-700 hover:underline font-medium">
                      bảng vận chuyển bên dưới
                    </a>
                    .
                  </p>
                ) : null}
              </div>
            )}
          </div>
        ) : null}
      </section>

      <section className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold text-gray-900">Tổng quan vận hành</h2>
          <button
            type="button"
            onClick={() => void loadOpsStats()}
            disabled={opsStatsLoading}
            className="text-sm text-emerald-700 hover:underline disabled:opacity-50"
          >
            Làm mới
          </button>
        </div>
        {opsStatsLoading && !opsStats ? (
          <p className="text-sm text-gray-500 py-4 text-center">Đang tải thống kê…</p>
        ) : opsStats ? (
          <div className="space-y-4">
            <p className="text-sm text-gray-600">
              Theo <strong>{opsStats.total_ems_records.toLocaleString('vi-VN')}</strong> dòng vận đơn EMS ·{' '}
              <strong>{opsStats.total_with_cod.toLocaleString('vi-VN')}</strong> dòng có thu hộ COD
            </p>

            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
                Trạng thái vận chuyển (cộng = tổng dòng)
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                {(
                  [
                    ['total', 'Tổng vận đơn', opsStats.total_ems_records, opsStats.total_cod_sum ?? 0, 'text-gray-900'],
                    ['in_transit', 'Đang giao', opsStats.in_transit_count, opsStats.in_transit_cod_total ?? 0, 'text-blue-800'],
                    ['delivered', 'Giao thành công', opsStats.delivered_count, opsStats.delivered_cod_total ?? 0, 'text-emerald-800'],
                    ['returned', 'Đơn hoàn chưa trả shop', opsStats.returned_count, opsStats.returned_cod_total ?? 0, 'text-orange-800'],
                    [
                      'shop_return_received',
                      'Đơn hoàn đã trả shop',
                      opsStats.shop_return_received_count,
                      opsStats.return_shop_received_cod_total ?? 0,
                      'text-orange-900',
                    ],
                    ['pending', 'Chưa rõ EMS', opsStats.pending_status_count, opsStats.pending_cod_total ?? 0, 'text-slate-600'],
                  ] as const
                ).map(([bucket, label, count, amount, color]) => (
                  <OpsStatCard
                    key={bucket}
                    label={label}
                    count={count}
                    amount={amount}
                    color={color}
                    active={activeOpsBucket === bucket}
                    onClick={() => openOpsBucket(bucket, label)}
                  />
                ))}
              </div>
              <p className="mt-1.5 text-xs text-gray-500 tabular-nums">
                {opsStats.in_transit_count +
                  opsStats.delivered_count +
                  opsStats.returned_count +
                  (opsStats.return_shop_received_count ?? opsStats.shop_return_received_count) +
                  opsStats.pending_status_count}{' '}
                = {opsStats.in_transit_count} + {opsStats.delivered_count} + {opsStats.returned_count} +{' '}
                {opsStats.return_shop_received_count ?? opsStats.shop_return_received_count} +{' '}
                {opsStats.pending_status_count}
                {opsStats.in_transit_count +
                  opsStats.delivered_count +
                  opsStats.returned_count +
                  (opsStats.return_shop_received_count ?? opsStats.shop_return_received_count) +
                  opsStats.pending_status_count ===
                opsStats.total_ems_records
                  ? ' ✓'
                  : ' (lệch — F5)'}
              </p>
            </div>

            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
                Thu hộ COD (cộng = dòng có COD)
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                {(
                  [
                    ['has_cod', 'Có COD', opsStats.total_with_cod, opsStats.total_cod_amount ?? 0, 'text-gray-900'],
                    [
                      'cod_in_transit_unpaid',
                      'Đang giao · chưa trả',
                      opsStats.cod_in_transit_unpaid_count,
                      opsStats.cod_in_transit_unpaid_total,
                      'text-indigo-800',
                    ],
                    [
                      'cod_delivered_unpaid',
                      'Giao OK · chưa trả',
                      opsStats.cod_delivered_unpaid_count,
                      opsStats.cod_delivered_unpaid_total,
                      'text-amber-800',
                    ],
                    ['cod_paid', 'COD EMS trả shop', opsStats.cod_paid_count, opsStats.cod_paid_total, 'text-emerald-800'],
                    [
                      'cod_returned_unpaid',
                      'Hoàn · chưa trả',
                      opsStats.cod_returned_unpaid_count,
                      opsStats.cod_returned_unpaid_total ?? 0,
                      'text-orange-800',
                    ],
                    ...(opsStats.cod_pending_unpaid_count > 0
                      ? ([
                          [
                            'cod_pending_unpaid',
                            'COD chưa rõ EMS',
                            opsStats.cod_pending_unpaid_count,
                            opsStats.cod_pending_unpaid_total ?? 0,
                            'text-slate-600',
                          ],
                        ] as const)
                      : []),
                  ] as const
                ).map(([bucket, label, count, amount, color]) => (
                  <OpsStatCard
                    key={bucket}
                    label={label}
                    count={count}
                    amount={amount}
                    color={color}
                    active={activeOpsBucket === bucket}
                    onClick={() => openOpsBucket(bucket, label)}
                  />
                ))}
              </div>
              <p className="mt-1.5 text-xs text-gray-500 tabular-nums">
                {opsStats.cod_in_transit_unpaid_count +
                  opsStats.cod_delivered_unpaid_count +
                  opsStats.cod_paid_count +
                  opsStats.cod_returned_unpaid_count +
                  opsStats.cod_pending_unpaid_count}{' '}
                = {opsStats.cod_in_transit_unpaid_count} + {opsStats.cod_delivered_unpaid_count} +{' '}
                {opsStats.cod_paid_count} + {opsStats.cod_returned_unpaid_count} +{' '}
                {opsStats.cod_pending_unpaid_count}
                {opsStats.cod_in_transit_unpaid_count +
                  opsStats.cod_delivered_unpaid_count +
                  opsStats.cod_paid_count +
                  opsStats.cod_returned_unpaid_count +
                  opsStats.cod_pending_unpaid_count ===
                opsStats.total_with_cod
                  ? ' ✓'
                  : ' (lệch — F5)'}
                {opsStats.cod_pending_unpaid_count > 0
                  ? ` · ${opsStats.cod_pending_unpaid_count} dòng COD chưa rõ trạng thái EMS`
                  : ''}
              </p>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-1 border-t border-gray-100">
              {(
                [
                  ['shop_linked', 'Ghép đơn shop', opsStats.shop_linked_count, 'text-emerald-800'],
                  ['freight_unsettled', 'Chưa đối soát cước', opsStats.freight_unsettled_count, 'text-violet-800'],
                  ['shop_shipping', 'Đơn shop đang giao', opsStats.shop_shipping_orders, 'text-blue-700'],
                ] as const
              ).map(([bucket, label, count, color]) => (
                <OpsStatCard
                  key={bucket}
                  label={label}
                  count={count}
                  color={color}
                  compact
                  active={activeOpsBucket === bucket}
                  onClick={() => openOpsBucket(bucket, label)}
                />
              ))}
            </div>

            <p className="text-xs text-gray-500 pt-1 border-t border-gray-100">
              Dòng dưới mỗi ô là tổng tiền thu hộ COD của nhóm đó (đồng).
            </p>
          </div>
        ) : null}
      </section>

      <section className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Theo dõi theo thời gian</h2>
            <p className="text-sm text-gray-600 mt-1">
              Thống kê vận đơn EMS theo ngày import vào hệ thống (múi giờ Việt Nam).
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {(Object.keys(TIMELINE_GRANULARITY_LABELS) as EmsShippingTimelineGranularity[]).map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => selectTimelineGranularity(key)}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium border transition-colors ${
                  timelineGranularity === key
                    ? 'bg-emerald-600 text-white border-emerald-600'
                    : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
                }`}
              >
                {TIMELINE_GRANULARITY_LABELS[key]}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-end gap-3 rounded-lg border border-gray-100 bg-gray-50/80 px-4 py-3">
          {timelineGranularity === 'day' ? (
            <>
              <label className="text-sm text-gray-700">
                Từ ngày
                <input
                  type="date"
                  value={timelineFilter.dateFrom}
                  onChange={(e) => setTimelineFilter((prev) => ({ ...prev, dateFrom: e.target.value, preset: null }))}
                  className="mt-1 block rounded-lg border border-gray-200 px-3 py-1.5 text-sm"
                />
              </label>
              <label className="text-sm text-gray-700">
                Đến ngày
                <input
                  type="date"
                  value={timelineFilter.dateTo}
                  onChange={(e) => setTimelineFilter((prev) => ({ ...prev, dateTo: e.target.value, preset: null }))}
                  className="mt-1 block rounded-lg border border-gray-200 px-3 py-1.5 text-sm"
                />
              </label>
              <button
                type="button"
                onClick={() => applyTimelineDateRange(timelineFilter.dateFrom, timelineFilter.dateTo || timelineFilter.dateFrom)}
                disabled={!timelineFilter.dateFrom || timelineLoading}
                className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                Xem theo ngày
              </button>
            </>
          ) : null}

          {timelineGranularity === 'week' ? (
            <>
              <button
                type="button"
                onClick={() => applyTimelinePreset('this_week')}
                className={`rounded-lg px-3 py-2 text-sm font-medium border ${
                  timelineFilter.preset === 'this_week'
                    ? 'bg-emerald-600 text-white border-emerald-600'
                    : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
                }`}
              >
                Tuần này
              </button>
              <button
                type="button"
                onClick={() => applyTimelinePreset('last_week')}
                className={`rounded-lg px-3 py-2 text-sm font-medium border ${
                  timelineFilter.preset === 'last_week'
                    ? 'bg-emerald-600 text-white border-emerald-600'
                    : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
                }`}
              >
                Tuần trước
              </button>
              <label className="text-sm text-gray-700">
                Từ
                <input
                  type="date"
                  value={timelineFilter.dateFrom}
                  onChange={(e) => setTimelineFilter((prev) => ({ ...prev, dateFrom: e.target.value, preset: null }))}
                  className="mt-1 block rounded-lg border border-gray-200 px-3 py-1.5 text-sm"
                />
              </label>
              <label className="text-sm text-gray-700">
                Đến
                <input
                  type="date"
                  value={timelineFilter.dateTo}
                  onChange={(e) => setTimelineFilter((prev) => ({ ...prev, dateTo: e.target.value, preset: null }))}
                  className="mt-1 block rounded-lg border border-gray-200 px-3 py-1.5 text-sm"
                />
              </label>
              <button
                type="button"
                onClick={() => applyTimelineDateRange(timelineFilter.dateFrom, timelineFilter.dateTo)}
                disabled={!timelineFilter.dateFrom || !timelineFilter.dateTo || timelineLoading}
                className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >
                Áp dụng khoảng
              </button>
            </>
          ) : null}

          {timelineGranularity === 'month' ? (
            <>
              <button
                type="button"
                onClick={() => applyTimelinePreset('this_month')}
                className={`rounded-lg px-3 py-2 text-sm font-medium border ${
                  timelineFilter.preset === 'this_month'
                    ? 'bg-emerald-600 text-white border-emerald-600'
                    : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
                }`}
              >
                Tháng này
              </button>
              <button
                type="button"
                onClick={() => applyTimelinePreset('last_month')}
                className={`rounded-lg px-3 py-2 text-sm font-medium border ${
                  timelineFilter.preset === 'last_month'
                    ? 'bg-emerald-600 text-white border-emerald-600'
                    : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
                }`}
              >
                Tháng trước
              </button>
              <label className="text-sm text-gray-700">
                Chọn tháng
                <input
                  type="month"
                  value={timelineMonthPick}
                  onChange={(e) => setTimelineMonthPick(e.target.value)}
                  className="mt-1 block rounded-lg border border-gray-200 px-3 py-1.5 text-sm"
                />
              </label>
              <button
                type="button"
                onClick={() => {
                  const range = monthInputToDateRange(timelineMonthPick);
                  if (!range) return;
                  applyTimelineDateRange(range.from, range.to);
                }}
                disabled={!timelineMonthPick || timelineLoading}
                className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >
                Xem tháng
              </button>
            </>
          ) : null}

          {timelineGranularity === 'year' ? (
            <label className="text-sm text-gray-700">
              Chọn năm
              <select
                value={timelineFilter.year}
                onChange={(e) => {
                  const value = e.target.value;
                  if (!value) {
                    clearTimelineFilter();
                    return;
                  }
                  applyTimelineYear(value);
                }}
                className="mt-1 block min-w-[140px] rounded-lg border border-gray-200 px-3 py-1.5 text-sm bg-white"
              >
                <option value="">Tất cả các năm</option>
                {(timelineStats?.available_years ?? []).map((y) => (
                  <option key={y} value={String(y)}>
                    {y}
                  </option>
                ))}
              </select>
            </label>
          ) : null}

          {timelineFilter.preset || timelineFilter.dateFrom || timelineFilter.dateTo || timelineFilter.year ? (
            <button
              type="button"
              onClick={clearTimelineFilter}
              className="rounded-lg px-3 py-2 text-sm font-medium text-gray-600 hover:text-gray-900 hover:underline"
            >
              Xóa lọc
            </button>
          ) : null}
        </div>

        {timelineStats?.filter_label ? (
          <p className="text-sm text-emerald-800 bg-emerald-50 border border-emerald-100 rounded-lg px-3 py-2">
            Đang lọc: <strong>{timelineStats.filter_label}</strong>
          </p>
        ) : null}

        {timelineError ? (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
            {timelineError}{' '}
            <button
              type="button"
              onClick={() => void loadTimelineStats(timelineGranularity)}
              className="underline font-medium"
            >
              Thử lại
            </button>
          </div>
        ) : null}

        {timelineLoading && !timelineStats ? (
          <p className="text-sm text-gray-500 py-4 text-center">Đang tải thống kê theo thời gian…</p>
        ) : timelineStats?.items.length ? (
          <div className="space-y-3">
            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="min-w-full text-sm">
                <thead className="bg-gray-50 text-gray-600">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">
                      {TIMELINE_GRANULARITY_LABELS[timelineStats.granularity]}
                    </th>
                    <th className="px-3 py-2 text-right font-medium">Tổng</th>
                    <th className="px-3 py-2 text-right font-medium">Đang giao</th>
                    <th className="px-3 py-2 text-right font-medium">Giao OK</th>
                    <th className="px-3 py-2 text-right font-medium">Hoàn chưa trả shop</th>
                    <th className="px-3 py-2 text-right font-medium">Đã trả shop</th>
                    <th className="px-3 py-2 text-right font-medium">Chưa rõ</th>
                    <th className="px-3 py-2 text-right font-medium">Có COD</th>
                    <th className="px-3 py-2 text-right font-medium">Giao OK · chưa trả COD</th>
                    <th className="px-3 py-2 text-right font-medium">COD EMS trả shop</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {timelineStats.items.map((item) => (
                    <tr key={item.period_key} className="hover:bg-gray-50/80">
                      <td className="px-3 py-2.5 text-gray-900">
                        <div className="font-medium">{item.period_label}</div>
                        {item.period_start !== item.period_end ? (
                          <div className="text-xs text-gray-500">
                            {item.period_start.slice(8, 10)}/{item.period_start.slice(5, 7)} –{' '}
                            {item.period_end.slice(8, 10)}/{item.period_end.slice(5, 7)}/{item.period_end.slice(0, 4)}
                          </div>
                        ) : null}
                      </td>
                      <td className="px-3 py-2.5 text-right font-medium">
                        <TimelineCodCountCell
                          count={item.total}
                          amount={item.total_cod_sum ?? 0}
                          onClick={() => openTimelineBucket(item, 'total')}
                          className="text-gray-900 hover:text-gray-950"
                          amountClassName="text-gray-600"
                        />
                      </td>
                      <td className="px-3 py-2.5 text-right text-blue-800">
                        <TimelineCodCountCell
                          count={item.in_transit_count}
                          amount={item.in_transit_cod_total ?? 0}
                          onClick={() => openTimelineBucket(item, 'in_transit')}
                          className="text-blue-800 hover:text-blue-950"
                          amountClassName="text-blue-700/90"
                        />
                      </td>
                      <td className="px-3 py-2.5 text-right text-emerald-800">
                        <TimelineCodCountCell
                          count={item.delivered_count}
                          amount={item.delivered_cod_total ?? 0}
                          onClick={() => openTimelineBucket(item, 'delivered')}
                          className="text-emerald-800 hover:text-emerald-950"
                          amountClassName="text-emerald-700/90"
                        />
                      </td>
                      <td className="px-3 py-2.5 text-right text-orange-800">
                        <TimelineCodCountCell
                          count={item.returned_count}
                          amount={item.returned_cod_total ?? 0}
                          onClick={() => openTimelineBucket(item, 'returned')}
                          className="text-orange-800 hover:text-orange-950"
                          amountClassName="text-orange-700/90"
                        />
                      </td>
                      <td className="px-3 py-2.5 text-right text-orange-900">
                        <TimelineCodCountCell
                          count={item.return_shop_received_count ?? 0}
                          amount={item.return_shop_received_cod_total ?? 0}
                          onClick={() => openTimelineBucket(item, 'shop_return_received')}
                          className="text-orange-900 hover:text-orange-950"
                          amountClassName="text-orange-800/90"
                        />
                      </td>
                      <td className="px-3 py-2.5 text-right text-slate-600">
                        <TimelineCodCountCell
                          count={item.pending_status_count}
                          amount={item.pending_cod_total ?? 0}
                          onClick={() => openTimelineBucket(item, 'pending')}
                          className="text-slate-600 hover:text-slate-900"
                          amountClassName="text-slate-500"
                        />
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <TimelineCodCountCell
                          count={item.total_with_cod}
                          amount={item.total_cod_amount}
                          onClick={() => openTimelineBucket(item, 'has_cod')}
                          className="text-gray-800 hover:text-gray-950"
                          amountClassName="text-gray-600"
                        />
                      </td>
                      <td className="px-3 py-2.5 text-right text-amber-800">
                        <TimelineCodCountCell
                          count={item.cod_delivered_unpaid_count ?? 0}
                          amount={item.cod_delivered_unpaid_total ?? 0}
                          onClick={() => openTimelineBucket(item, 'cod_delivered_unpaid')}
                          className="text-amber-800 hover:text-amber-950"
                          amountClassName="text-amber-700/90"
                        />
                      </td>
                      <td className="px-3 py-2.5 text-right text-emerald-700">
                        <TimelineCodCountCell
                          count={item.cod_paid_count}
                          amount={item.cod_paid_total ?? 0}
                          onClick={() => openTimelineBucket(item, 'cod_paid')}
                          className="text-emerald-700 hover:text-emerald-900"
                          amountClassName="text-emerald-700/90"
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
                {timelineStats.totals.total > 0 ? (
                  <tfoot className="bg-emerald-50/70 text-emerald-950">
                    <tr>
                      <td className="px-3 py-2.5 font-semibold">
                        Tổng ({timelineStats.items.length} kỳ hiển thị)
                      </td>
                      <td className="px-3 py-2.5 text-right font-semibold">
                        <TimelineCodCountCell
                          count={timelineStats.totals.total}
                          amount={timelineStats.totals.total_cod_sum ?? 0}
                          onClick={() => openTimelineBucketTotals('total')}
                          className="text-emerald-950 hover:text-emerald-900"
                          amountClassName="text-emerald-900"
                        />
                      </td>
                      <td className="px-3 py-2.5 text-right font-semibold">
                        <TimelineCodCountCell
                          count={timelineStats.totals.in_transit_count}
                          amount={timelineStats.totals.in_transit_cod_total ?? 0}
                          onClick={() => openTimelineBucketTotals('in_transit')}
                          className="text-blue-900 hover:text-blue-950"
                          amountClassName="text-blue-900"
                        />
                      </td>
                      <td className="px-3 py-2.5 text-right font-semibold">
                        <TimelineCodCountCell
                          count={timelineStats.totals.delivered_count}
                          amount={timelineStats.totals.delivered_cod_total ?? 0}
                          onClick={() => openTimelineBucketTotals('delivered')}
                          className="text-emerald-900 hover:text-emerald-950"
                          amountClassName="text-emerald-900"
                        />
                      </td>
                      <td className="px-3 py-2.5 text-right font-semibold">
                        <TimelineCodCountCell
                          count={timelineStats.totals.returned_count}
                          amount={timelineStats.totals.returned_cod_total ?? 0}
                          onClick={() => openTimelineBucketTotals('returned')}
                          className="text-orange-900 hover:text-orange-950"
                          amountClassName="text-orange-900"
                        />
                      </td>
                      <td className="px-3 py-2.5 text-right font-semibold">
                        <TimelineCodCountCell
                          count={timelineStats.totals.return_shop_received_count ?? 0}
                          amount={timelineStats.totals.return_shop_received_cod_total ?? 0}
                          onClick={() => openTimelineBucketTotals('shop_return_received')}
                          className="text-orange-950 hover:text-orange-900"
                          amountClassName="text-orange-900"
                        />
                      </td>
                      <td className="px-3 py-2.5 text-right font-semibold">
                        <TimelineCodCountCell
                          count={timelineStats.totals.pending_status_count}
                          amount={timelineStats.totals.pending_cod_total ?? 0}
                          onClick={() => openTimelineBucketTotals('pending')}
                          className="text-slate-700 hover:text-slate-900"
                          amountClassName="text-slate-600"
                        />
                      </td>
                      <td className="px-3 py-2.5 text-right font-semibold">
                        <TimelineCodCountCell
                          count={timelineStats.totals.total_with_cod}
                          amount={timelineStats.totals.total_cod_amount}
                          onClick={() => openTimelineBucketTotals('has_cod')}
                          className="text-emerald-950 hover:text-emerald-900"
                          amountClassName="text-emerald-900"
                        />
                      </td>
                      <td className="px-3 py-2.5 text-right font-semibold text-amber-900">
                        <TimelineCodCountCell
                          count={timelineStats.totals.cod_delivered_unpaid_count ?? 0}
                          amount={timelineStats.totals.cod_delivered_unpaid_total ?? 0}
                          onClick={() => openTimelineBucketTotals('cod_delivered_unpaid')}
                          className="text-amber-900 hover:text-amber-950"
                          amountClassName="text-amber-900"
                        />
                      </td>
                      <td className="px-3 py-2.5 text-right font-semibold">
                        <TimelineCodCountCell
                          count={timelineStats.totals.cod_paid_count}
                          amount={timelineStats.totals.cod_paid_total ?? 0}
                          onClick={() => openTimelineBucketTotals('cod_paid')}
                          className="text-emerald-800 hover:text-emerald-950"
                          amountClassName="text-emerald-800"
                        />
                      </td>
                    </tr>
                  </tfoot>
                ) : null}
              </table>
            </div>
            <p className="text-xs text-gray-500">
              Hiển thị tối đa {timelineStats.limit} kỳ gần nhất · múi giờ {timelineStats.timezone}
              {' · '}
              Bấm số để xem danh sách mã · Dòng dưới mỗi số là tổng tiền thu hộ COD của nhóm (đ)
              {' · '}
              Giao OK · chưa trả COD = đã giao, EMS chưa trả tiền thu hộ về shop
              {' · '}
              COD EMS trả shop = chỉ khi import file đối soát COD
            </p>
          </div>
        ) : timelineError ? null : (
          <p className="text-sm text-gray-500 py-4 text-center">
            {timelineStats?.filter_label
              ? 'Không có vận đơn nào trong khoảng thời gian đã chọn.'
              : 'Chưa có dữ liệu vận đơn để thống kê.'}
          </p>
        )}
      </section>

      <section className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm space-y-4">
        <h2 className="text-lg font-semibold text-gray-900">1. Upload file Excel gửi EMS</h2>
        <p className="text-sm text-gray-600">
          File <strong>file gui ems.xlsx</strong>: cột <strong>A</strong> mã vận đơn, <strong>I</strong> mã đơn shop
          (DHxxx/DCxxx), <strong>G</strong> COD, <strong>D</strong> tên khách. Import lần 2: mã cột A đã có thì{' '}
          <strong>cập nhật</strong> COD/đơn/tên; mã mới thì <strong>thêm dòng</strong>. Tra EMS chạy{' '}
          <strong>nền trên server</strong> theo thứ tự (progress bar bên dưới). Cron hàng ngày cập nhật đơn đang giao.
        </p>
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx,.xlsm"
            className="block w-full text-sm text-gray-700 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-emerald-50 file:text-emerald-700 hover:file:bg-emerald-100"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setError(null);
            }}
          />
          <button
            type="button"
            onClick={runImport}
            disabled={loading || !file || listLoading}
            className="inline-flex items-center justify-center rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {loading ? 'Đang tra EMS…' : 'Import & đối chiếu'}
          </button>
        </div>
        {file ? <p className="text-xs text-gray-500">Đã chọn: {file.name}</p> : null}

        {emsImportBatchesLoading ? (
          <p className="text-sm text-gray-500">Đang tải lịch sử báo cáo import…</p>
        ) : emsImportBatches?.batches.length ? (
          <div className="space-y-3 border-t border-gray-100 pt-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-sm font-semibold text-gray-900">
                Lịch sử báo cáo import ({emsImportBatches.batches.length})
              </h3>
              {emsImportBatches.batches.length > 1 ? (
                <label className="text-sm text-gray-600 flex items-center gap-2 min-w-0">
                  <span className="shrink-0">Mở báo cáo</span>
                  <select
                    value={selectedEmsImportBatchId ?? ''}
                    onChange={(e) => {
                      setSelectedEmsImportBatchId(Number(e.target.value));
                      setImportReportListExpanded(false);
                    }}
                    className="min-w-0 max-w-full rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
                  >
                    {emsImportBatches.batches.map((batch) => (
                      <option key={batch.id} value={batch.id}>
                        {formatEmsImportBatchLabel(batch)}
                      </option>
                    ))}
                  </select>
                </label>
              ) : activeEmsImportBatch ? (
                <span className="text-xs text-gray-500 truncate max-w-md" title={formatEmsImportBatchLabel(activeEmsImportBatch)}>
                  {formatEmsImportBatchLabel(activeEmsImportBatch)}
                </span>
              ) : null}
            </div>
            {activeEmsImportReport && !loading ? (
              <EmsImportReportPanel
                report={activeEmsImportReport}
                listExpanded={importReportListExpanded}
                onToggleList={() => setImportReportListExpanded((v) => !v)}
                title={
                  selectedEmsImportBatchId === emsImportBatches.batches[0]?.id
                    ? 'Báo cáo import mới nhất'
                    : 'Báo cáo import đã lưu'
                }
              />
            ) : null}
          </div>
        ) : !loading ? (
          <p className="text-xs text-gray-500">
            Chưa có báo cáo import nào được lưu. Sau khi «Import & đối chiếu», báo cáo sẽ xuất hiện ở đây để mở lại.
          </p>
        ) : null}
      </section>

      <section className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm space-y-4">
        <h2 className="text-lg font-semibold text-gray-900">2. Import đối soát COD EMS trả shop</h2>
        <p className="text-sm text-gray-600">
          File <strong>Doi soat cod (Shop 188).xls</strong>: cột <strong>C</strong> mã vận chuyển EMS, cột{' '}
          <strong>D</strong> số tiền EMS đã trả shop (vd. 5,200,000), ô <strong>E1</strong> ngày trả tiền.
          Chỉ sau bước này hệ thống mới ghi <strong>COD EMS trả shop</strong> — hành trình «[COD]Đã thu tiền» là
          bưu tá thu khách, chưa phải trả shop.
        </p>
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <input
            ref={codFileRef}
            type="file"
            accept=".xls,.xlsx,.xlsm"
            className="block w-full text-sm text-gray-700 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
            onChange={(e) => {
              setCodFile(e.target.files?.[0] ?? null);
              setCodError(null);
            }}
          />
          <button
            type="button"
            onClick={() => void runCodImport()}
            disabled={codLoading || !codFile || codListLoading}
            className="inline-flex items-center justify-center rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {codLoading ? 'Đang đối chiếu COD…' : 'Import đối soát COD'}
          </button>
        </div>
        {codFile ? <p className="text-xs text-gray-500">Đã chọn: {codFile.name}</p> : null}

        {codError ? (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
            {codError}{' '}
            <button type="button" onClick={() => void loadCodSettlements()} className="underline font-medium">
              Thử lại
            </button>
          </div>
        ) : null}

        {codResult?.import_batch && !codLoading ? (
          <div className="bg-blue-50 border border-blue-200 text-blue-900 rounded-lg px-4 py-3 text-sm">
            Đối soát ngày{' '}
            <strong>{codResult.import_batch.payment_date || '—'}</strong>:{' '}
            <strong>{codResult.import_batch.matched_count}</strong> khớp ·{' '}
            <strong>{codResult.import_batch.amount_mismatch_count}</strong> lệch tiền ·{' '}
            <strong>{codResult.import_batch.record_not_found_count}</strong> không có trong DB · tổng trả{' '}
            <strong>{formatVnd(codResult.import_batch.total_paid_amount)}</strong>
            {codResult.import_batch.total_amount_difference !== 0 ? (
              <>
                {' '}
                · chênh lệch tổng{' '}
                <strong>{formatVnd(Math.abs(codResult.import_batch.total_amount_difference))}</strong>
              </>
            ) : null}
          </div>
        ) : null}

        {codResult?.warnings?.length ? (
          <div className="bg-amber-50 border border-amber-200 text-amber-900 rounded-lg px-4 py-3 text-sm space-y-1">
            {codResult.warnings.map((w) => (
              <p key={w}>{w}</p>
            ))}
          </div>
        ) : null}

        {codListLoading ? (
          <div className="bg-gray-50 border border-gray-200 rounded-xl px-4 py-8 text-center text-sm text-gray-500">
            Đang tải lịch sử đối soát COD…
          </div>
        ) : codResult?.batches.length ? (
          <CollapsibleListPanel
            title="Danh sách đối soát COD"
            summary={codListCollapseSummary}
            expanded={codListExpanded}
            onToggle={() => setCodListExpanded((v) => !v)}
          >
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              {[
                ['Tổng mã', codSummary?.total_rows ?? 0, 'all'],
                ['Khớp tiền', codSummary?.matched ?? 0, 'matched'],
                ['Lệch tiền', codSummary?.amount_mismatch ?? 0, 'amount_mismatch'],
                ['Không có DB', codSummary?.record_not_found ?? 0, 'record_not_found'],
                ['Lỗi parse', codSummary?.parse_error ?? 0, 'parse_error'],
              ].map(([label, count, key]) => (
                <button
                  key={String(key)}
                  type="button"
                  onClick={() => setCodFilter(key as CodFilterKey)}
                  className={`rounded-xl border px-3 py-3 text-left transition ${
                    codFilter === key ? 'border-blue-500 ring-2 ring-blue-100' : 'border-gray-200 bg-white'
                  }`}
                >
                  <div className="text-xs text-gray-500">{label}</div>
                  <div className="text-xl font-semibold text-gray-900">{count}</div>
                </button>
              ))}
              <div className="rounded-xl border border-gray-200 bg-white px-3 py-3">
                <div className="text-xs text-gray-500">Tổng đã trả</div>
                <div className="text-lg font-semibold text-blue-800">{formatVnd(codSummary?.total_paid_amount ?? 0)}</div>
                <div className="text-xs text-gray-500 mt-1">
                  DB thu hộ: {formatVnd(codSummary?.total_db_cod_amount ?? 0)}
                </div>
              </div>
            </div>

            <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
              <div className="px-4 py-3 border-b border-gray-100 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="text-base font-semibold text-gray-900">Bảng đối soát COD</h3>
                  <span className="text-sm text-gray-500">{filteredCodRows.length} dòng</span>
                </div>
                {codResult.batches.length > 1 ? (
                  <label className="text-sm text-gray-600 flex items-center gap-2">
                    Ngày trả tiền
                    <select
                      value={selectedBatchId ?? ''}
                      onChange={(e) => setSelectedBatchId(Number(e.target.value))}
                      className="rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
                    >
                      {codResult.batches.map((batch) => (
                        <option key={batch.id} value={batch.id}>
                          {batch.payment_date || batch.created_at?.slice(0, 10) || `#${batch.id}`}
                          {batch.source_filename ? ` · ${batch.source_filename}` : ''}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : activeCodBatch?.payment_date ? (
                  <span className="text-sm text-gray-600">
                    Ngày trả: <strong>{activeCodBatch.payment_date}</strong>
                  </span>
                ) : null}
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-50 text-gray-600">
                    <tr>
                      <th className="px-3 py-2 text-left font-medium">#</th>
                      <th className="px-3 py-2 text-left font-medium">Mã EMS</th>
                      <th className="px-3 py-2 text-left font-medium">Mã vận đơn</th>
                      <th className="px-3 py-2 text-right font-medium">Đã trả (file)</th>
                      <th className="px-3 py-2 text-right font-medium">Thu hộ (DB)</th>
                      <th className="px-3 py-2 text-right font-medium">Chênh</th>
                      <th className="px-3 py-2 text-left font-medium">Kết quả</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {filteredCodRows.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="px-4 py-8 text-center text-gray-500">
                          Không có dòng trong bộ lọc này.
                        </td>
                      </tr>
                    ) : (
                      filteredCodRows.map((row) => (
                        <tr key={row.id ?? `${row.row_number}:${row.ems_tracking_code}`} className="align-top">
                          <td className="px-3 py-3 text-gray-500">{row.row_number}</td>
                          <td className="px-3 py-3 font-medium text-gray-900">{row.ems_tracking_code || '—'}</td>
                          <td className="px-3 py-3 text-gray-700">{row.ems_reference_code || '—'}</td>
                          <td className="px-3 py-3 text-right tabular-nums">{formatVnd(row.paid_amount)}</td>
                          <td className="px-3 py-3 text-right tabular-nums">{formatCodAmount(row.db_cod_amount)}</td>
                          <td className="px-3 py-3 text-right tabular-nums">
                            {row.amount_difference != null && row.amount_difference !== 0 ? (
                              <span className="text-amber-800 font-medium">
                                {row.amount_difference > 0 ? '+' : ''}
                                {formatVnd(row.amount_difference)}
                              </span>
                            ) : (
                              '—'
                            )}
                          </td>
                          <td className="px-3 py-3">
                            <span
                              className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${
                                COD_RECONCILE_BADGE[row.reconcile_status] || COD_RECONCILE_BADGE.parse_error
                              }`}
                            >
                              {COD_RECONCILE_LABELS[row.reconcile_status] || row.reconcile_status}
                            </span>
                            {row.reconcile_message ? (
                              <p className="text-xs text-gray-600 mt-2 max-w-sm">{row.reconcile_message}</p>
                            ) : null}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </CollapsibleListPanel>
        ) : (
          <div className="bg-gray-50 border border-gray-200 rounded-xl px-4 py-8 text-center text-sm text-gray-500">
            Chưa có lần đối soát COD nào. Upload file <strong>Doi soat cod</strong> để bắt đầu.
          </div>
        )}
      </section>

      <section className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm space-y-4">
        <h2 className="text-lg font-semibold text-gray-900">3. Xác nhận đơn hoàn đã trả shop</h2>
        <p className="text-sm text-gray-600">
          Shop xác nhận đã nhận hàng hoàn — ghi <strong>Đơn hoàn đã trả shop</strong> và hủy hoa hồng affiliate.
          Nhập <strong>mã vận chuyển EMS</strong>, <strong>mã tham chiếu</strong> (cột A file gửi EMS) hoặc <strong>mã đơn DHxxx</strong> —
          hệ thống tự map sang đơn shop. Chỉ xác nhận khi EMS đã có trạng thái <strong>đơn hoàn</strong> (phát hoàn / chuyển hoàn…).
        </p>
        <div className="space-y-3">
          <label className="block text-sm font-medium text-gray-700">Danh sách mã (EMS / tham chiếu / DHxxx)</label>
          <textarea
            value={shopReturnText}
            onChange={(e) => {
              setShopReturnText(e.target.value);
              setShopReturnError(null);
            }}
            rows={4}
            placeholder={'EE123456789VN\nMA_THAM_CHIEU_A\nDH131'}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono placeholder:text-gray-400 focus:border-orange-500 focus:ring-1 focus:ring-orange-500"
          />
        </div>
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <input
            ref={shopReturnFileRef}
            type="file"
            accept=".xls,.xlsx,.xlsm"
            className="block w-full text-sm text-gray-700 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-orange-50 file:text-orange-700 hover:file:bg-orange-100"
            onChange={(e) => {
              setShopReturnFile(e.target.files?.[0] ?? null);
              setShopReturnError(null);
            }}
          />
          <button
            type="button"
            onClick={() => void runShopReturnConfirm()}
            disabled={shopReturnLoading || (!shopReturnText.trim() && !shopReturnFile)}
            className="inline-flex items-center justify-center rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white hover:bg-orange-700 disabled:opacity-50"
          >
            {shopReturnLoading ? 'Đang xử lý…' : 'Xác nhận đơn hoàn'}
          </button>
        </div>
        {shopReturnFile ? <p className="text-xs text-gray-500">File Excel: {shopReturnFile.name}</p> : null}

        {shopReturnError ? (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
            {shopReturnError}
          </div>
        ) : null}

        {shopReturnResult && !shopReturnLoading ? (
          <div className="space-y-3">
            <div
              className={`rounded-lg border px-4 py-3 text-sm ${
                shopReturnResult.error_count > 0
                  ? 'bg-amber-50 border-amber-200 text-amber-950'
                  : 'bg-emerald-50 border-emerald-200 text-emerald-950'
              }`}
            >
              <strong>{shopReturnResult.confirmed_count.toLocaleString('vi-VN')}</strong> đơn đã xác nhận ·{' '}
              <strong>{shopReturnResult.error_count.toLocaleString('vi-VN')}</strong> lỗi
              {shopReturnResult.not_found_count > 0 ? (
                <>
                  {' '}
                  (không tìm thấy: <strong>{shopReturnResult.not_found_count}</strong>)
                </>
              ) : null}
              {(shopReturnResult.ems_not_return_count ?? 0) > 0 ? (
                <>
                  {' '}
                  · EMS chưa hoàn: <strong>{shopReturnResult.ems_not_return_count}</strong>
                </>
              ) : null}
            </div>
            {shopReturnResult.warnings?.length ? (
              <div className="bg-amber-50 border border-amber-200 text-amber-900 rounded-lg px-4 py-3 text-sm space-y-1">
                {shopReturnResult.warnings.map((w) => (
                  <p key={w}>{w}</p>
                ))}
              </div>
            ) : null}
            {shopReturnResult.rows.length > 0 ? (
              <CollapsibleListPanel
                title="Chi tiết từng mã"
                summary={`${shopReturnResult.rows.length} dòng`}
                expanded={shopReturnListExpanded}
                onToggle={() => setShopReturnListExpanded((v) => !v)}
              >
                <div className="overflow-x-auto rounded-xl border border-gray-200">
                  <table className="min-w-full text-sm">
                    <thead className="bg-gray-50 text-gray-600">
                      <tr>
                        <th className="px-3 py-2 text-left font-medium">#</th>
                        <th className="px-3 py-2 text-left font-medium">Mã nhập</th>
                        <th className="px-3 py-2 text-left font-medium">Mã đơn</th>
                        <th className="px-3 py-2 text-left font-medium">Kết quả</th>
                        <th className="px-3 py-2 text-left font-medium">Ghi chú</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {shopReturnResult.rows.map((row: ShopReturnConfirmRow) => {
                        const st = SHOP_RETURN_ROW_STATUS[row.status] || SHOP_RETURN_ROW_STATUS.invalid_code;
                        return (
                          <tr key={`${row.row_number}:${row.order_code}:${row.status}`} className="hover:bg-gray-50/80">
                            <td className="px-3 py-2 text-gray-500 tabular-nums">{row.row_number || '—'}</td>
                            <td className="px-3 py-2 text-gray-700 max-w-[140px] truncate" title={row.raw}>
                              {row.raw || '—'}
                            </td>
                            <td className="px-3 py-2 font-mono font-medium">
                              {row.order_code ? (
                                row.order_id ? (
                                  <Link
                                    href={`/admin/orders?q=${encodeURIComponent(row.order_code)}`}
                                    className="text-orange-700 hover:underline"
                                  >
                                    {row.order_code}
                                  </Link>
                                ) : (
                                  <span className="text-red-700">{row.order_code}</span>
                                )
                              ) : (
                                <span className="text-gray-400">—</span>
                              )}
                            </td>
                            <td className="px-3 py-2">
                              <span
                                className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${st.badge}`}
                              >
                                {st.label}
                              </span>
                            </td>
                            <td className="px-3 py-2 text-gray-600 max-w-xs">{row.message || '—'}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </CollapsibleListPanel>
            ) : null}
          </div>
        ) : null}
      </section>

      <section className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm space-y-4">
        <h2 className="text-lg font-semibold text-gray-900">4. Import đối soát cước</h2>
        <p className="text-sm text-gray-600">
          File <strong>Doi soat cuoc.xls</strong>: cột <strong>A</strong> mã vận chuyển EMS, cột <strong>L</strong> cước phí.
          Mã phải đã có trong bảng vận chuyển và <strong>chưa từng đối soát cước</strong>.
          Cước phí &gt; <strong>70.000 đ</strong> sẽ được cảnh báo để xem lại.
        </p>
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <input
            ref={freightFileRef}
            type="file"
            accept=".xls,.xlsx,.xlsm"
            className="block w-full text-sm text-gray-700 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-violet-50 file:text-violet-700 hover:file:bg-violet-100"
            onChange={(e) => {
              setFreightFile(e.target.files?.[0] ?? null);
              setFreightError(null);
            }}
          />
          <button
            type="button"
            onClick={() => void runFreightImport()}
            disabled={freightLoading || !freightFile || freightListLoading}
            className="inline-flex items-center justify-center rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-50"
          >
            {freightLoading ? 'Đang đối soát cước…' : 'Import đối soát cước'}
          </button>
        </div>
        {freightFile ? <p className="text-xs text-gray-500">Đã chọn: {freightFile.name}</p> : null}

        {freightError ? (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
            {freightError}{' '}
            <button type="button" onClick={() => void loadFreightSettlements()} className="underline font-medium">
              Thử lại
            </button>
          </div>
        ) : null}

        {freightResult?.import_batch && !freightLoading ? (
          <div className="bg-violet-50 border border-violet-200 text-violet-900 rounded-lg px-4 py-3 text-sm">
            Đối soát cước: <strong>{freightResult.import_batch.settled_count}</strong> thành công ·{' '}
            <strong>{freightResult.import_batch.already_settled_count}</strong> đã đối soát trước ·{' '}
            <strong>{freightResult.import_batch.record_not_found_count}</strong> không có trong DB · tổng cước{' '}
            <strong>{formatVnd(freightResult.import_batch.total_freight_amount)}</strong>
            {freightResult.import_batch.high_fee_warning_count > 0 ? (
              <>
                {' '}
                · <strong className="text-amber-800">{freightResult.import_batch.high_fee_warning_count}</strong> mã cước
                &gt; 70.000 đ
              </>
            ) : null}
          </div>
        ) : null}

        {freightResult?.warnings?.length ? (
          <div className="bg-amber-50 border border-amber-200 text-amber-900 rounded-lg px-4 py-3 text-sm space-y-1">
            {freightResult.warnings.map((w) => (
              <p key={w}>{w}</p>
            ))}
          </div>
        ) : null}

        {freightListLoading ? (
          <div className="bg-gray-50 border border-gray-200 rounded-xl px-4 py-8 text-center text-sm text-gray-500">
            Đang tải lịch sử đối soát cước…
          </div>
        ) : freightResult?.batches.length ? (
          <CollapsibleListPanel
            title="Danh sách đối soát cước"
            summary={freightListCollapseSummary}
            expanded={freightListExpanded}
            onToggle={() => setFreightListExpanded((v) => !v)}
          >
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3">
              {[
                ['Tổng mã', freightSummary?.total_rows ?? 0, 'all'],
                ['Đã đối soát', freightSummary?.settled ?? 0, 'settled'],
                ['Đã DS trước', freightSummary?.already_settled ?? 0, 'already_settled'],
                ['Không có DB', freightSummary?.record_not_found ?? 0, 'record_not_found'],
                ['Lỗi parse', freightSummary?.parse_error ?? 0, 'parse_error'],
              ].map(([label, count, key]) => (
                <button
                  key={String(key)}
                  type="button"
                  onClick={() => setFreightFilter(key as FreightFilterKey)}
                  className={`rounded-xl border px-3 py-3 text-left transition ${
                    freightFilter === key ? 'border-violet-500 ring-2 ring-violet-100' : 'border-gray-200 bg-white'
                  }`}
                >
                  <div className="text-xs text-gray-500">{label}</div>
                  <div className="text-xl font-semibold text-gray-900">{count}</div>
                </button>
              ))}
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-3">
                <div className="text-xs text-amber-800">Cảnh báo &gt; 70k</div>
                <div className="text-xl font-semibold text-amber-900">
                  {freightSummary?.high_fee_warning_count ?? 0}
                </div>
              </div>
              <div className="rounded-xl border border-gray-200 bg-white px-3 py-3">
                <div className="text-xs text-gray-500">Tổng cước (OK)</div>
                <div className="text-lg font-semibold text-violet-800">
                  {formatVnd(freightSummary?.total_freight_amount ?? 0)}
                </div>
              </div>
            </div>

            <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
              <div className="px-4 py-3 border-b border-gray-100 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="text-base font-semibold text-gray-900">Bảng đối soát cước</h3>
                  <span className="text-sm text-gray-500">{filteredFreightRows.length} dòng</span>
                </div>
                {freightResult.batches.length > 1 ? (
                  <label className="text-sm text-gray-600 flex items-center gap-2">
                    Lần import
                    <select
                      value={selectedFreightBatchId ?? ''}
                      onChange={(e) => setSelectedFreightBatchId(Number(e.target.value))}
                      className="rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
                    >
                      {freightResult.batches.map((batch) => (
                        <option key={batch.id} value={batch.id}>
                          {batch.created_at?.slice(0, 16).replace('T', ' ') || `#${batch.id}`}
                          {batch.source_filename ? ` · ${batch.source_filename}` : ''}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-50 text-gray-600">
                    <tr>
                      <th className="px-3 py-2 text-left font-medium">#</th>
                      <th className="px-3 py-2 text-left font-medium">Mã EMS</th>
                      <th className="px-3 py-2 text-right font-medium">Cước phí</th>
                      <th className="px-3 py-2 text-left font-medium">Cảnh báo</th>
                      <th className="px-3 py-2 text-left font-medium">Kết quả</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {filteredFreightRows.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="px-4 py-8 text-center text-gray-500">
                          Không có dòng trong bộ lọc này.
                        </td>
                      </tr>
                    ) : (
                      filteredFreightRows.map((row) => (
                        <tr
                          key={row.id ?? `${row.row_number}:${row.ems_tracking_code}`}
                          className={`align-top ${row.high_fee_warning === 'yes' ? 'bg-amber-50/60' : ''}`}
                        >
                          <td className="px-3 py-3 text-gray-500">{row.row_number}</td>
                          <td className="px-3 py-3 font-medium text-gray-900">{row.ems_tracking_code || '—'}</td>
                          <td className="px-3 py-3 text-right tabular-nums">{formatVnd(row.freight_amount)}</td>
                          <td className="px-3 py-3">
                            {row.high_fee_warning === 'yes' ? (
                              <span className="inline-flex rounded-full border border-amber-300 bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900">
                                Cước &gt; 70.000 đ — xem lại
                              </span>
                            ) : (
                              '—'
                            )}
                          </td>
                          <td className="px-3 py-3">
                            <span
                              className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${
                                FREIGHT_RECONCILE_BADGE[row.reconcile_status] || FREIGHT_RECONCILE_BADGE.parse_error
                              }`}
                            >
                              {FREIGHT_RECONCILE_LABELS[row.reconcile_status] || row.reconcile_status}
                            </span>
                            {row.reconcile_message ? (
                              <p className="text-xs text-gray-600 mt-2 max-w-sm">{row.reconcile_message}</p>
                            ) : null}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </CollapsibleListPanel>
        ) : (
          <div className="bg-gray-50 border border-gray-200 rounded-xl px-4 py-8 text-center text-sm text-gray-500">
            Chưa có lần đối soát cước nào. Upload file <strong>Doi soat cuoc</strong> để bắt đầu.
          </div>
        )}
      </section>

      {error ? (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          {error}{' '}
          <button type="button" onClick={() => void loadRecords()} className="underline font-medium">
            Thử lại
          </button>
        </div>
      ) : null}

      {trackingJob && ['queued', 'running'].includes(trackingJob.status) ? (
        <div
          className={`rounded-lg px-4 py-3 text-sm border ${
            trackingJob.is_stale
              ? 'bg-amber-50 border-amber-300 text-amber-950'
              : 'bg-indigo-50 border-indigo-200 text-indigo-900'
          }`}
        >
          <div className="font-medium">
            {trackingJob.is_stale
              ? 'Job tra EMS có thể đã dừng trên server'
              : 'Đang tra EMS nền trên server…'}
          </div>
          <div className="mt-1">
            {trackingJob.message || 'Đang xử lý…'} ({trackingJob.processed}/{trackingJob.total})
          </div>
          <div className="mt-1 text-xs opacity-80">
            Cập nhật gần nhất: {formatStaleSeconds(trackingJob.seconds_since_update)} trước
            {trackingJob.is_stale
              ? ' — số không đổi >2 phút thường do worker backend bị restart hoặc crash.'
              : ' — nếu số tăng đều ~ mỗi vài giây thì job vẫn đang chạy.'}
          </div>
          {trackingJob.is_stale ? (
            <button
              type="button"
              onClick={() => void resumeTrackingJob()}
              disabled={trackingResumeLoading}
              className="mt-2 inline-flex items-center rounded-md bg-amber-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-60"
            >
              {trackingResumeLoading ? 'Đang khôi phục…' : 'Tiếp tục tra EMS'}
            </button>
          ) : null}
          <div className="mt-2 h-2 rounded-full bg-indigo-100 overflow-hidden">
            <div
              className={`h-full transition-all duration-500 ${
                trackingJob.is_stale ? 'bg-amber-500' : 'bg-indigo-500'
              }`}
              style={{
                width: trackingJob.total
                  ? `${Math.min(100, Math.round((trackingJob.processed / trackingJob.total) * 100))}%`
                  : '0%',
              }}
            />
          </div>
        </div>
      ) : null}

      {trackingJob && trackingJob.status === 'completed' ? (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-900 rounded-lg px-4 py-3 text-sm">
          {trackingJob.message || `Tra EMS xong: ${trackingJob.ok}/${trackingJob.total} thành công.`}
        </div>
      ) : null}

      {trackingJob && trackingJob.status === 'failed' ? (
        <div className="bg-red-50 border border-red-200 text-red-800 rounded-lg px-4 py-3 text-sm">
          {trackingJob.message || 'Job tra EMS thất bại.'}
        </div>
      ) : null}

      {result?.warnings?.length ? (
        <div className="bg-amber-50 border border-amber-200 text-amber-900 rounded-lg px-4 py-3 text-sm space-y-1">
          {result.warnings.map((w) => (
            <p key={w}>{w}</p>
          ))}
        </div>
      ) : null}

      {listLoading && !result ? (
        <section className="bg-gray-50 border border-gray-200 rounded-xl px-4 py-10 text-center text-sm text-gray-500">
          Đang tải bảng vận chuyển…
        </section>
      ) : showTable ? (
        <>
          <section className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
            {[
              ['Tổng dòng', result.summary.total_rows, 'all'],
              ['Khớp', result.summary.matched, 'matched'],
              ['Đang xử lý', result.summary.in_progress, 'in_progress'],
              ['Lệch', result.summary.mismatch, 'mismatch'],
              ['Chưa ghép đơn', result.summary.unlinked ?? result.summary.order_not_found, 'unlinked'],
              ['Không tra EMS', result.summary.ems_not_found, 'ems_not_found'],
              ['Lỗi parse', result.summary.parse_error, 'parse_error'],
            ].map(([label, count, key]) => (
              <button
                key={String(key)}
                type="button"
                onClick={() => applyFilter(key as FilterKey)}
                className={`rounded-xl border px-3 py-3 text-left transition ${
                  filter === key ? 'border-emerald-500 ring-2 ring-emerald-100' : 'border-gray-200 bg-white'
                }`}
              >
                <div className="text-xs text-gray-500">{label}</div>
                <div className="text-xl font-semibold text-gray-900">{count}</div>
              </button>
            ))}
          </section>

          {result.summary.breakdown?.length ? (
            <section className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
              <div className="px-4 py-3 border-b border-gray-100">
                <h2 className="text-lg font-semibold text-gray-900">Thống kê theo trạng thái đối chiếu</h2>
                <p className="text-sm text-gray-500 mt-0.5">
                  Số đơn và tổng tiền thu hộ (cột P) theo từng trạng thái
                </p>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-50 text-gray-600">
                    <tr>
                      <th className="px-4 py-2 text-left font-medium">Trạng thái</th>
                      <th className="px-4 py-2 text-right font-medium">Số đơn</th>
                      <th className="px-4 py-2 text-right font-medium">Tổng thu hộ</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {result.summary.breakdown.map((item) => (
                      <tr
                        key={item.key}
                        className={`cursor-pointer hover:bg-gray-50 ${filter === item.key ? 'bg-emerald-50/50' : ''}`}
                        onClick={() => applyFilter(item.key as FilterKey)}
                      >
                        <td className="px-4 py-2.5">
                          <span
                            className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${
                              SYNC_BADGE[item.key] || SYNC_BADGE.parse_error
                            }`}
                          >
                            {SYNC_LABELS[item.key as EmsShippingImportRow['sync_status']] || item.key}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums font-medium text-gray-900">
                          {item.count}
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-gray-900">
                          {formatVnd(item.cod_total)}
                        </td>
                      </tr>
                    ))}
                    <tr className="bg-gray-50 font-semibold">
                      <td className="px-4 py-3 text-gray-900">Tổng cộng</td>
                      <td className="px-4 py-3 text-right tabular-nums text-gray-900">
                        {result.summary.total_rows}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-emerald-800">
                        {formatVnd(result.summary.total_cod_amount ?? 0)}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}

          <section id="ems-shipping-table" className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
            <div className="px-4 py-3 border-b border-gray-100 flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0 flex-1">
                <button
                  type="button"
                  onClick={() => setEmsTableExpanded((v) => !v)}
                  aria-expanded={emsTableExpanded}
                  className="flex items-start sm:items-center gap-2 text-left hover:opacity-90"
                >
                  <span
                    className={`inline-flex h-5 w-5 shrink-0 items-center justify-center text-gray-500 transition-transform ${
                      emsTableExpanded ? 'rotate-90' : ''
                    }`}
                    aria-hidden
                  >
                    ▶
                  </span>
                  <div>
                    <h2 className="text-lg font-semibold text-gray-900">Bảng vận chuyển EMS</h2>
                    <span className="text-sm text-gray-500">
                      {appliedSearch ? (
                        <>
                          Tra «{appliedSearch}»: {filteredTotal} kết quả
                          {filter !== 'all' ? ' (đã lọc trạng thái)' : ''}
                        </>
                      ) : filter === 'all' ? (
                        `${totalRows} dòng`
                      ) : (
                        `${filteredTotal} / ${totalRows} dòng`
                      )}
                      {filteredTotal > 0 && emsTableExpanded
                        ? ` · hiển thị ${displayFrom}–${displayTo}`
                        : ''}
                      {selectedKeys.size > 0 ? ` · đã chọn ${selectedKeys.size}` : ''}
                    </span>
                  </div>
                </button>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => setEmsTableExpanded((v) => !v)}
                  className="text-sm text-emerald-700 hover:underline font-medium whitespace-nowrap"
                >
                  {emsTableExpanded ? 'Thu gọn' : 'Mở rộng'}
                </button>
                {emsTableExpanded ? (
                  <>
                    <label className="text-sm text-gray-600 flex items-center gap-1.5">
                      <span className="whitespace-nowrap">Dòng/trang</span>
                      <select
                        value={listPageSize}
                        onChange={(e) => {
                          setListPageSize(Number(e.target.value));
                          setListPage(1);
                          setSelectedKeys(new Set());
                        }}
                        className="rounded-lg border border-gray-300 bg-white px-2 py-1 text-sm"
                      >
                        {EMS_LIST_PAGE_SIZES.map((size) => (
                          <option key={size} value={size}>
                            {size}
                          </option>
                        ))}
                      </select>
                    </label>
                    {selectedKeys.size > 0 ? (
                      <button
                        type="button"
                        onClick={() => void runEmsTrackingRefresh({ ids: selectedRecordIds })}
                        disabled={refreshingEms || selectedRecordIds.length === 0}
                        className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-sm font-medium text-indigo-800 hover:bg-indigo-100 disabled:opacity-50"
                      >
                        Tra EMS đã chọn ({selectedRecordIds.length})
                      </button>
                    ) : null}
                    <button
                      type="button"
                      onClick={runManualEmsRefresh}
                      disabled={refreshingEms}
                      className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-sm font-medium text-indigo-800 hover:bg-indigo-100 disabled:opacity-50"
                    >
                      {refreshingEms ? 'Đang tra EMS…' : 'Tra lại EMS'}
                    </button>
                    {selectedKeys.size > 0 ? (
                      <button
                        type="button"
                        onClick={() => requestDelete([...selectedKeys])}
                        disabled={deleting}
                        className="inline-flex items-center rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-100 disabled:opacity-50"
                      >
                        Xóa đã chọn ({selectedKeys.size})
                      </button>
                    ) : null}
                  </>
                ) : null}
              </div>
            </div>
            {emsTableExpanded ? (
              <>
                <div className="overflow-x-auto max-h-[min(70vh,720px)] overflow-y-auto">
                  <table className="min-w-full text-sm">
                <thead className="bg-gray-50 text-gray-600 sticky top-0 z-10 shadow-[0_1px_0_0_rgb(229,231,235)]">
                  <tr>
                    <th className="px-3 py-2 w-10 bg-gray-50">
                      <input
                        type="checkbox"
                        checked={allPageSelected}
                        ref={(el) => {
                          if (el) el.indeterminate = !allPageSelected && somePageSelected;
                        }}
                        onChange={toggleAllFiltered}
                        aria-label="Chọn tất cả dòng trên trang này"
                        className="rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
                      />
                    </th>
                    <th className="px-3 py-2 text-left font-medium">#</th>
                    <th className="px-3 py-2 text-left font-medium">Mã vận đơn</th>
                    <th className="px-3 py-2 text-left font-medium">Đơn shop</th>
                    <th className="px-3 py-2 text-right font-medium">Thu hộ</th>
                    <th className="px-3 py-2 text-right font-medium">Đã trả COD</th>
                    <th className="px-3 py-2 text-right font-medium">Cước EMS</th>
                    <th className="px-3 py-2 text-left font-medium">Mã EMS</th>
                    <th className="px-3 py-2 text-left font-medium">Trạng thái EMS</th>
                    <th className="px-3 py-2 text-left font-medium">Trạng thái đơn shop</th>
                    <th className="px-3 py-2 text-left font-medium">Đối chiếu</th>
                    <th className="px-3 py-2 text-right font-medium min-w-[7rem]">Thao tác</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {pageRows.length === 0 ? (
                    <tr>
                      <td colSpan={13} className="px-4 py-8 text-center text-gray-500">
                        {totalRows === 0
                          ? 'Chưa có dòng nào. Upload file Excel EMS để bắt đầu.'
                          : appliedSearch
                            ? `Không tìm thấy dòng nào khớp «${appliedSearch}».`
                            : 'Không có dòng nào trong bộ lọc này.'}
                      </td>
                    </tr>
                  ) : (
                    pageRows.map((row) => {
                      const key = rowKey(row);
                      const checked = selectedKeys.has(key);
                      return (
                        <tr key={key} className={`align-top ${checked ? 'bg-emerald-50/40' : ''}`}>
                          <td className="px-3 py-3">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={(e) => toggleRow(key, e.target.checked)}
                              aria-label={`Chọn dòng ${row.reference_code || row.row_number}`}
                              className="rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
                            />
                          </td>
                          <td className="px-3 py-3 text-gray-500">{row.row_number}</td>
                          <td className="px-3 py-3">
                            <div className="font-medium text-gray-900">{row.reference_code || '—'}</div>
                            <div className="text-xs text-gray-500 mt-1 line-clamp-2">{row.recipient_label}</div>
                          </td>
                          <td className="px-3 py-3">
                            {row.order_code ? (
                              row.order_id ? (
                                <Link
                                  href={`/admin/orders?q=${encodeURIComponent(row.order_code)}`}
                                  className="text-emerald-700 hover:underline font-medium"
                                >
                                  {row.order_code}
                                </Link>
                              ) : (
                                <span className="font-medium text-gray-900">{row.order_code}</span>
                              )
                            ) : (
                              '—'
                            )}
                            {row.tracking_number_saved ? (
                              <div className="text-xs text-gray-500 mt-1">Mã lưu: {row.tracking_number_saved}</div>
                            ) : null}
                          </td>
                          <td className="px-3 py-3 text-right tabular-nums whitespace-nowrap">
                            {formatCodAmount(row.cod_amount)}
                          </td>
                          <td className="px-3 py-3 text-right tabular-nums whitespace-nowrap">
                            <div>{formatCodPaidDisplay(row)}</div>
                            {formatCodCollectedHint(row)}
                            {row.cod_settlement_status ? (
                              <span
                                className={`inline-flex mt-1 rounded-full border px-2 py-0.5 text-[10px] font-medium ${
                                  COD_RECONCILE_BADGE[row.cod_settlement_status] ||
                                  COD_RECONCILE_BADGE.parse_error
                                }`}
                              >
                                {COD_RECONCILE_LABELS[row.cod_settlement_status] || row.cod_settlement_status}
                              </span>
                            ) : null}
                          </td>
                          <td className="px-3 py-3 text-right tabular-nums whitespace-nowrap">
                            <div>{formatVnd(row.freight_amount)}</div>
                            {row.freight_high_fee_warning === 'yes' ? (
                              <span className="inline-flex mt-1 rounded-full border border-amber-300 bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-900">
                                &gt; 70k
                              </span>
                            ) : null}
                            {row.freight_settlement_status === 'settled' ? (
                              <span className="inline-flex mt-1 rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-[10px] font-medium text-violet-800">
                                Đã DS cước
                              </span>
                            ) : null}
                          </td>
                          <td className="px-3 py-3">{row.ems_tracking_code || '—'}</td>
                          <td className="px-3 py-3">
                            <div className="text-gray-900">{row.ems_status || row.ems_error || '—'}</div>
                            {row.ems_phase ? <div className="text-xs text-gray-500 mt-1">{row.ems_phase}</div> : null}
                          </td>
                          <td className="px-3 py-3">
                            {row.order_status ? (
                              <span
                                className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${
                                  ORDER_STATUS_BADGE[row.order_status] || 'bg-gray-100 text-gray-800 border-gray-200'
                                }`}
                              >
                                {emsShopOrderStatusLabel(row)}
                              </span>
                            ) : row.order_code ? (
                              <span className="text-xs text-amber-700">Không khớp đơn khách</span>
                            ) : (
                              '—'
                            )}
                            {row.current_step_key ? (
                              <div className="text-xs text-gray-500 mt-1.5">
                                {emsTimelineLabel(row.current_step_key)}
                              </div>
                            ) : null}
                          </td>
                          <td className="px-3 py-3">
                            <span
                              className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${
                                SYNC_BADGE[row.sync_status] || SYNC_BADGE.parse_error
                              }`}
                            >
                              {SYNC_LABELS[row.sync_status] || row.sync_status}
                            </span>
                            {row.sync_message ? (
                              <p className="text-xs text-gray-600 mt-2 max-w-xs">{row.sync_message}</p>
                            ) : null}
                          </td>
                          <td className="px-3 py-3 text-right">
                            <div className="flex flex-col items-end gap-1.5">
                              {row.id != null ? (
                                <button
                                  type="button"
                                  onClick={() => refreshEmsRow(row)}
                                  disabled={refreshingEms}
                                  className="text-xs font-medium text-indigo-700 hover:text-indigo-900 hover:underline whitespace-nowrap disabled:opacity-50"
                                >
                                  Tra lại EMS
                                </button>
                              ) : null}
                              <button
                                type="button"
                                onClick={() => void openOrderStatusModal(row)}
                                className="text-xs font-medium text-emerald-700 hover:text-emerald-900 hover:underline whitespace-nowrap"
                              >
                                Xem trạng thái
                              </button>
                              <button
                                type="button"
                                onClick={() => requestDelete([key])}
                                disabled={deleting}
                                className="text-xs font-medium text-red-600 hover:text-red-800 hover:underline disabled:opacity-50"
                              >
                                Xóa
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
                  </table>
                </div>
                {filteredTotal > 0 ? (
                  <div className="px-4 py-3 border-t border-gray-100 flex flex-wrap items-center justify-between gap-3 text-sm text-gray-600">
                    <span>
                      Trang {listPage} / {totalPages} · {filteredTotal} dòng
                      {filter !== 'all' ? ' (đã lọc trạng thái)' : ''}
                      {appliedSearch ? ` · tra «${appliedSearch}»` : ''}
                    </span>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setListPage(1)}
                        disabled={listPage <= 1 || listLoading}
                        className="rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 hover:bg-gray-50 disabled:opacity-40"
                      >
                        Đầu
                      </button>
                      <button
                        type="button"
                        onClick={() => setListPage((p) => Math.max(1, p - 1))}
                        disabled={listPage <= 1 || listLoading}
                        className="rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 hover:bg-gray-50 disabled:opacity-40"
                      >
                        Trước
                      </button>
                      <button
                        type="button"
                        onClick={() => setListPage((p) => Math.min(totalPages, p + 1))}
                        disabled={listPage >= totalPages || listLoading}
                        className="rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 hover:bg-gray-50 disabled:opacity-40"
                      >
                        Sau
                      </button>
                      <button
                        type="button"
                        onClick={() => setListPage(totalPages)}
                        disabled={listPage >= totalPages || listLoading}
                        className="rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 hover:bg-gray-50 disabled:opacity-40"
                      >
                        Cuối
                      </button>
                    </div>
                  </div>
                ) : null}
              </>
            ) : (
              <div className="px-4 py-3 text-sm text-gray-500 border-b border-gray-50">
                Bấm <strong className="text-gray-700">Mở rộng</strong> để xem bảng chi tiết và phân trang.
              </div>
            )}
          </section>
        </>
      ) : null}

      {activeOpsBucket ? (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="ops-bucket-title"
          onClick={() => closeOpsBucketModal()}
          onKeyDown={(e) => {
            if (e.key === 'Escape' && !opsBucketLoading) closeOpsBucketModal();
          }}
        >
          <div
            className="w-full max-w-3xl max-h-[90vh] overflow-hidden rounded-xl bg-white shadow-xl border border-gray-200 flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-5 py-4 border-b border-gray-100 flex items-start justify-between gap-3 shrink-0">
              <div>
                <h3 id="ops-bucket-title" className="text-lg font-semibold text-gray-900">
                  {opsBucketLabel}
                </h3>
                <p className="text-sm text-gray-500 mt-0.5">
                  {opsBucketTotal.toLocaleString('vi-VN')} vận đơn
                  {opsBucketTotal > 0
                    ? ` · trang ${opsBucketPage}/${opsBucketTotalPages}`
                    : ''}
                </p>
              </div>
              <button
                type="button"
                onClick={() => closeOpsBucketModal()}
                disabled={opsBucketLoading}
                className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 disabled:opacity-50"
                aria-label="Đóng"
              >
                ✕
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
              {opsBucketError ? (
                <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
                  {opsBucketError}{' '}
                  <button
                    type="button"
                    onClick={() => activeOpsBucket && void loadOpsBucketRecords(activeOpsBucket, opsBucketPage)}
                    className="underline font-medium"
                  >
                    Thử lại
                  </button>
                </div>
              ) : null}
              {!opsBucketLoading && opsBucketRows.length > 0 ? (
                <div className="rounded-lg border border-emerald-100 bg-emerald-50/70 px-4 py-3 text-sm text-emerald-950">
                  <p className="font-medium mb-2">
                    Danh sách mã ({opsBucketRows.length} / {opsBucketTotal.toLocaleString('vi-VN')})
                  </p>
                  <ul className="space-y-1 font-mono text-xs leading-relaxed max-h-40 overflow-y-auto">
                    {opsBucketRows.map((row) => (
                      <li key={rowKey(row)}>
                        {row.order_code || '—'}
                        {row.ems_tracking_code ? ` · ${row.ems_tracking_code}` : ''}
                        {row.reference_code ? ` · ${row.reference_code}` : ''}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {opsBucketLoading ? (
                <p className="text-sm text-gray-500 py-10 text-center">Đang tải danh sách…</p>
              ) : opsBucketRows.length === 0 ? (
                <p className="text-sm text-gray-500 py-10 text-center">Không có dòng trong nhóm này.</p>
              ) : (
                opsBucketRows.map((row) => (
                  <EmsSearchResultCard
                    key={rowKey(row)}
                    row={row}
                    onViewStatus={(r) => void openOrderStatusModal(r)}
                  />
                ))
              )}
            </div>

            {opsBucketTotal > OPS_LIST_PAGE_SIZE ? (
              <div className="px-5 py-3 border-t border-gray-100 flex flex-wrap items-center justify-between gap-2 text-sm text-gray-600 shrink-0">
                <span>
                  {(opsBucketPage - 1) * OPS_LIST_PAGE_SIZE + 1}–
                  {Math.min(opsBucketPage * OPS_LIST_PAGE_SIZE, opsBucketTotal)} / {opsBucketTotal}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    disabled={opsBucketPage <= 1 || opsBucketLoading}
                    onClick={() => activeOpsBucket && void loadOpsBucketRecords(activeOpsBucket, opsBucketPage - 1)}
                    className="rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 hover:bg-gray-50 disabled:opacity-40"
                  >
                    Trước
                  </button>
                  <button
                    type="button"
                    disabled={opsBucketPage >= opsBucketTotalPages || opsBucketLoading}
                    onClick={() => activeOpsBucket && void loadOpsBucketRecords(activeOpsBucket, opsBucketPage + 1)}
                    className="rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 hover:bg-gray-50 disabled:opacity-40"
                  >
                    Sau
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {orderStatusModal ? (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="order-status-title"
          onKeyDown={(e) => {
            if (e.key === 'Escape' && !orderStatusModal.loading) setOrderStatusModal(null);
          }}
        >
          <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-xl bg-white shadow-xl border border-gray-200 p-5 space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 id="order-status-title" className="text-lg font-semibold text-gray-900">
                  Trạng thái đơn shop
                </h3>
                <p className="text-sm text-gray-500 mt-0.5">
                  {orderStatusModal.row.order_code || '—'} · {orderStatusModal.row.reference_code || '—'}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setOrderStatusModal(null)}
                disabled={orderStatusModal.loading}
                className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 disabled:opacity-50"
                aria-label="Đóng"
              >
                ✕
              </button>
            </div>

            {orderStatusModal.loading ? (
              <p className="text-sm text-gray-500 py-6 text-center">Đang tải trạng thái đơn…</p>
            ) : orderStatusModal.error ? (
              <div className="bg-amber-50 border border-amber-200 text-amber-900 rounded-lg px-4 py-3 text-sm space-y-2">
                <p className="font-medium">Không khớp đơn của khách</p>
                <p>{orderStatusModal.error}</p>
                {orderStatusModal.row.ems_status ? (
                  <p className="text-xs text-amber-800/90 pt-1 border-t border-amber-200">
                    EMS: {orderStatusModal.row.ems_status}
                  </p>
                ) : null}
              </div>
            ) : (
              <>
                <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm text-gray-600">Trạng thái hiện tại:</span>
                    <span
                      className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-medium ${
                        ORDER_STATUS_BADGE[orderStatusModal.timeline?.order_status || ''] ||
                        'bg-gray-100 text-gray-800 border-gray-200'
                      }`}
                    >
                      {orderStatusLabel(orderStatusModal.timeline?.order_status)}
                    </span>
                  </div>
                  {orderStatusModal.timeline?.current_step_key ? (
                    <p className="text-sm text-gray-700">
                      Bước timeline:{' '}
                      <strong>
                        {TIMELINE_STEP_LABELS[orderStatusModal.timeline.current_step_key] ||
                          orderStatusModal.timeline.current_step_key}
                      </strong>
                    </p>
                  ) : null}
                  {orderStatusModal.timeline?.tracking_number ? (
                    <p className="text-xs text-gray-600">
                      Mã vận đơn: {orderStatusModal.timeline.tracking_number}
                      {orderStatusModal.timeline.shipping_provider
                        ? ` · ${orderStatusModal.timeline.shipping_provider}`
                        : ''}
                    </p>
                  ) : null}
                </div>

                {orderStatusModal.timeline?.events?.length ? (
                  <div>
                    <h4 className="text-sm font-semibold text-gray-900 mb-2">Lịch trình giao hàng (188.com.vn)</h4>
                    <ul className="space-y-2">
                      {orderStatusModal.timeline.events.map((ev) => (
                        <li key={ev.step_key} className="flex items-start gap-2 text-sm">
                          <span
                            className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                              ev.status === 'completed'
                                ? 'bg-emerald-500'
                                : ev.status === 'active'
                                  ? 'bg-emerald-600'
                                  : 'bg-gray-300'
                            }`}
                          />
                          <span className={ev.status === 'active' ? 'font-medium text-emerald-800' : 'text-gray-700'}>
                            {ev.title}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {orderStatusModal.timeline?.ems_tracking?.available ? (
                  <div className="rounded-lg border border-indigo-100 bg-indigo-50/40 p-4">
                    <h4 className="text-sm font-semibold text-indigo-900 mb-2">Hành trình EMS</h4>
                    {orderStatusModal.timeline.ems_tracking.current_status_description ? (
                      <p className="text-xs text-indigo-700 mb-2">
                        Mới nhất:{' '}
                        <strong>{orderStatusModal.timeline.ems_tracking.current_status_description}</strong>
                      </p>
                    ) : null}
                    {orderStatusModal.timeline.ems_tracking.error ? (
                      <p className="text-xs text-amber-800">{orderStatusModal.timeline.ems_tracking.error}</p>
                    ) : orderStatusModal.timeline.ems_tracking.events.length ? (
                      <ul className="space-y-2">
                        {orderStatusModal.timeline.ems_tracking.events.map((ev, idx) => (
                          <li key={`${ev.description}-${ev.traced_at || idx}`} className="flex items-start gap-2 text-sm">
                            <span
                              className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                                idx === 0 ? 'bg-indigo-600' : 'bg-indigo-300'
                              }`}
                            />
                            <span className={idx === 0 ? 'font-medium text-indigo-800' : 'text-gray-700'}>
                              {ev.description}
                              {ev.traced_at ? (
                                <span className="block text-xs font-normal text-gray-500 mt-0.5">
                                  {new Date(ev.traced_at).toLocaleString('vi-VN')}
                                </span>
                              ) : null}
                              {ev.address ? (
                                <span className="block text-xs font-normal text-gray-400 mt-0.5">{ev.address}</span>
                              ) : null}
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : orderStatusModal.row.ems_status ? (
                      <p className="text-sm text-indigo-800">{orderStatusModal.row.ems_status}</p>
                    ) : (
                      <p className="text-sm text-gray-500">Chưa có cập nhật từ EMS.</p>
                    )}
                  </div>
                ) : orderStatusModal.row.ems_tracking_code || orderStatusModal.row.ems_status ? (
                  <div className="rounded-lg border border-indigo-100 bg-indigo-50/40 p-4">
                    <h4 className="text-sm font-semibold text-indigo-900 mb-2">Hành trình EMS</h4>
                    {orderStatusModal.row.ems_tracking_code ? (
                      <p className="text-xs text-gray-600 mb-2 font-mono">{orderStatusModal.row.ems_tracking_code}</p>
                    ) : null}
                    {orderStatusModal.row.ems_status ? (
                      <p className="text-sm text-indigo-800">{orderStatusModal.row.ems_status}</p>
                    ) : (
                      <p className="text-sm text-gray-500">Chưa có cập nhật từ EMS.</p>
                    )}
                  </div>
                ) : null}

                {orderStatusModal.order ? (
                  <div className="flex flex-wrap gap-2 pt-1">
                    <Link
                      href={`/admin/orders?q=${encodeURIComponent(orderStatusModal.order.order_code)}`}
                      className="inline-flex rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-sm font-medium text-emerald-800 hover:bg-emerald-100"
                    >
                      Mở trong quản lý đơn
                    </Link>
                  </div>
                ) : null}
              </>
            )}
          </div>
        </div>
      ) : null}

      {deleteConfirmKeys ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-confirm-title"
          onKeyDown={(e) => {
            if (e.key === 'Escape' && !deleting) setDeleteConfirmKeys(null);
          }}
        >
          <div className="w-full max-w-md rounded-xl bg-white shadow-xl border border-gray-200 p-5 space-y-4">
            <h3 id="delete-confirm-title" className="text-lg font-semibold text-gray-900">
              Xóa khỏi bảng vận chuyển?
            </h3>
            <p className="text-sm text-gray-600">
              Bạn sắp xóa <strong>{deleteConfirmKeys.length}</strong> dòng khỏi bảng vận chuyển EMS.
              Thao tác này <strong>không thể hoàn tác</strong> — không xóa đơn hàng trên shop.
            </p>
            {deletePreviewRows.length > 0 ? (
              <ul className="max-h-32 overflow-y-auto rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 text-xs text-gray-700 space-y-1">
                {deletePreviewRows.slice(0, 8).map((row) => (
                  <li key={rowKey(row)}>
                    {row.reference_code || '—'} · {row.order_code || '—'} · {row.ems_tracking_code || '—'}
                  </li>
                ))}
                {deletePreviewRows.length > 8 ? (
                  <li className="text-gray-500">… và {deletePreviewRows.length - 8} dòng khác</li>
                ) : null}
              </ul>
            ) : null}
            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={() => setDeleteConfirmKeys(null)}
                disabled={deleting}
                className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >
                Hủy
              </button>
              <button
                type="button"
                onClick={() => void confirmDelete()}
                disabled={deleting}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              >
                {deleting ? 'Đang xóa…' : 'Xóa vĩnh viễn'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
