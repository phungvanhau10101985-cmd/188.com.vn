'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
  type EmsShippingImportResult,
  type EmsShippingImportRow,
  type EmsShippingOperationsStats,
  type EmsTrackingRefreshJob,
} from '@/lib/admin-api';

const EMS_TRACKING_JOB_STORAGE_KEY = 'admin_ems_tracking_job_id';

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
  returned: 'Đã hoàn hàng',
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
  awaiting_confirm: 'Shop đã gửi shipper — chờ khách nhận',
};

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
  return `${Math.round(amount).toLocaleString('vi-VN')} ₫`;
}

function orderStatusLabel(status: string | null | undefined): string {
  if (!status) return '—';
  return ORDER_STATUS_TEXTS[status] || status;
}

export default function AdminShippingPage() {
  const fileRef = useRef<HTMLInputElement>(null);
  const codFileRef = useRef<HTMLInputElement>(null);
  const freightFileRef = useRef<HTMLInputElement>(null);
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
  const [codFilter, setCodFilter] = useState<CodFilterKey>('all');
  const [freightFilter, setFreightFilter] = useState<FreightFilterKey>('all');
  const [selectedBatchId, setSelectedBatchId] = useState<number | null>(null);
  const [selectedFreightBatchId, setSelectedFreightBatchId] = useState<number | null>(null);
  const [opsStats, setOpsStats] = useState<EmsShippingOperationsStats | null>(null);
  const [opsStatsLoading, setOpsStatsLoading] = useState(true);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [deleteConfirmKeys, setDeleteConfirmKeys] = useState<string[] | null>(null);
  const [orderStatusModal, setOrderStatusModal] = useState<OrderStatusModalState | null>(null);
  const [trackingJob, setTrackingJob] = useState<EmsTrackingRefreshJob | null>(null);
  const trackingPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadRecords = useCallback(async () => {
    setListLoading(true);
    setError(null);
    try {
      const data = await adminShippingAPI.listEmsRecords();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không tải được bảng vận chuyển');
    } finally {
      setListLoading(false);
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

  const loadOpsStats = useCallback(async () => {
    setOpsStatsLoading(true);
    try {
      const data = await adminShippingAPI.getOperationsStats();
      setOpsStats(data);
    } catch {
      setOpsStats(null);
    } finally {
      setOpsStatsLoading(false);
    }
  }, []);

  const stopTrackingPoll = useCallback(() => {
    if (trackingPollRef.current) {
      clearInterval(trackingPollRef.current);
      trackingPollRef.current = null;
    }
  }, []);

  const startTrackingPoll = useCallback(
    (jobId: string) => {
      stopTrackingPoll();
      if (typeof window !== 'undefined') {
        sessionStorage.setItem(EMS_TRACKING_JOB_STORAGE_KEY, jobId);
      }
      const poll = async () => {
        try {
          const job = await adminShippingAPI.getEmsTrackingRefreshJob(jobId);
          setTrackingJob(job);
          if (job.status === 'completed' || job.status === 'failed') {
            stopTrackingPoll();
            if (typeof window !== 'undefined') {
              sessionStorage.removeItem(EMS_TRACKING_JOB_STORAGE_KEY);
            }
            await loadRecords();
            await loadOpsStats();
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
    void loadCodSettlements();
    void loadFreightSettlements();
    void loadOpsStats();
  }, [loadRecords, loadCodSettlements, loadFreightSettlements, loadOpsStats]);

  const filteredRows = useMemo(() => {
    if (!result) return [];
    if (filter === 'all') return result.rows;
    if (filter === 'unlinked') {
      return result.rows.filter((row) => row.sync_status === 'unlinked' || row.sync_status === 'order_not_found');
    }
    return result.rows.filter((row) => row.sync_status === filter);
  }, [result, filter]);

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

  const filteredKeyList = useMemo(() => filteredRows.map(rowKey), [filteredRows]);

  const allFilteredSelected =
    filteredKeyList.length > 0 && filteredKeyList.every((key) => selectedKeys.has(key));

  const someFilteredSelected = filteredKeyList.some((key) => selectedKeys.has(key));

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
      setResult(data);
      setFilter('all');
      setSelectedKeys(new Set());
      if (data.tracking_refresh_job_id) {
        startTrackingPoll(data.tracking_refresh_job_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import thất bại');
    } finally {
      setLoading(false);
    }
  }, [file, startTrackingPoll]);

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
      await loadRecords();
      await loadOpsStats();
    } catch (err) {
      setCodError(err instanceof Error ? err.message : 'Import đối soát COD thất bại');
    } finally {
      setCodLoading(false);
    }
  }, [codFile, loadRecords, loadOpsStats]);

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
      if (allFilteredSelected) {
        filteredKeyList.forEach((key) => next.delete(key));
      } else {
        filteredKeyList.forEach((key) => next.add(key));
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
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7 gap-3">
            {[
              ['Đang giao', opsStats.shipping_orders, 'text-blue-800'],
              ['Giao thành công', opsStats.delivered_success_orders, 'text-emerald-800'],
              ['Đã hoàn hàng', opsStats.returned_orders, 'text-orange-800'],
              ['COD chưa trả (đã giao)', opsStats.cod_success_unpaid_count, 'text-amber-800'],
              ['COD đã trả', opsStats.cod_success_paid_count, 'text-emerald-800'],
              ['COD đang giao', opsStats.shipping_cod_unpaid_count, 'text-indigo-800'],
              ['Chưa đối soát cước', opsStats.freight_unsettled_count, 'text-violet-800'],
            ].map(([label, count, color]) => (
              <div key={String(label)} className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3">
                <div className="text-xs text-gray-500">{label}</div>
                <div className={`text-2xl font-semibold tabular-nums ${color}`}>{count}</div>
              </div>
            ))}
          </div>
        ) : null}
        {opsStats ? (
          <div className="flex flex-wrap gap-4 text-sm text-gray-600 pt-1 border-t border-gray-100">
            <span>
              Tổng thu hộ chưa trả:{' '}
              <strong className="text-amber-800">{formatVnd(opsStats.cod_success_unpaid_total)}</strong>
            </span>
            <span>
              Tổng COD đã trả:{' '}
              <strong className="text-emerald-800">{formatVnd(opsStats.cod_success_paid_total)}</strong>
            </span>
          </div>
        ) : null}
      </section>

      <section className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm space-y-4">
        <h2 className="text-lg font-semibold text-gray-900">1. Upload file Excel gửi EMS</h2>
        <p className="text-sm text-gray-600">
          File <strong>file gui ems.xlsx</strong>: cột <strong>A</strong> mã vận đơn, <strong>I</strong> mã đơn shop
          (DHxxx/DCxxx), <strong>G</strong> COD, <strong>D</strong> tên khách. Import lưu ngay; tra EMS chạy{' '}
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
      </section>

      <section className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm space-y-4">
        <h2 className="text-lg font-semibold text-gray-900">2. Import đối soát COD đã trả</h2>
        <p className="text-sm text-gray-600">
          File <strong>Doi soat cod (Shop 188).xls</strong>: cột <strong>C</strong> mã vận chuyển EMS, cột{' '}
          <strong>D</strong> số tiền đã trả (vd. 5,200,000), ô <strong>E1</strong> ngày trả tiền.
          Hệ thống đối chiếu với tiền thu hộ đã lưu trong bảng vận chuyển EMS.
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
      </section>

      <section className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm space-y-4">
        <h2 className="text-lg font-semibold text-gray-900">3. Import đối soát cước</h2>
        <p className="text-sm text-gray-600">
          File <strong>Doi soat cuoc.xls</strong>: cột <strong>A</strong> mã vận chuyển EMS, cột <strong>L</strong> cước phí.
          Mã phải đã có trong bảng vận chuyển và <strong>chưa từng đối soát cước</strong>.
          Cước phí &gt; <strong>70.000 ₫</strong> sẽ được cảnh báo để xem lại.
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
      </section>

      {freightError ? (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          {freightError}{' '}
          <button type="button" onClick={() => void loadFreightSettlements()} className="underline font-medium">
            Thử lại
          </button>
        </div>
      ) : null}

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
        <section className="bg-gray-50 border border-gray-200 rounded-xl px-4 py-8 text-center text-sm text-gray-500">
          Đang tải lịch sử đối soát COD…
        </section>
      ) : codResult?.batches.length ? (
        <>
          <section className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
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
          </section>

          <section className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
            <div className="px-4 py-3 border-b border-gray-100 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Bảng đối soát COD</h2>
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
                        <td className="px-3 py-3 text-right tabular-nums">{formatVnd(row.db_cod_amount)}</td>
                        <td className="px-3 py-3 text-right tabular-nums">
                          {row.amount_difference != null && row.amount_difference !== 0 ? (
                            <span className="text-amber-800 font-medium">
                              {row.amount_difference > 0 ? '+' : ''}
                              {row.amount_difference.toLocaleString('vi-VN')} ₫
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
          </section>
        </>
      ) : (
        <section className="bg-gray-50 border border-gray-200 rounded-xl px-4 py-8 text-center text-sm text-gray-500">
          Chưa có lần đối soát COD nào. Upload file <strong>Doi soat cod</strong> để bắt đầu.
        </section>
      )}

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
              &gt; 70.000 ₫
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
        <section className="bg-gray-50 border border-gray-200 rounded-xl px-4 py-8 text-center text-sm text-gray-500">
          Đang tải lịch sử đối soát cước…
        </section>
      ) : freightResult?.batches.length ? (
        <>
          <section className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3">
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
          </section>

          <section className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
            <div className="px-4 py-3 border-b border-gray-100 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Bảng đối soát cước</h2>
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
                              Cước &gt; 70.000 ₫ — xem lại
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
          </section>
        </>
      ) : (
        <section className="bg-gray-50 border border-gray-200 rounded-xl px-4 py-8 text-center text-sm text-gray-500">
          Chưa có lần đối soát cước nào. Upload file <strong>Doi soat cuoc</strong> để bắt đầu.
        </section>
      )}

      {error ? (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          {error}{' '}
          <button type="button" onClick={() => void loadRecords()} className="underline font-medium">
            Thử lại
          </button>
        </div>
      ) : null}

      {result?.import_stats ? (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-900 rounded-lg px-4 py-3 text-sm">
          Import xong: <strong>{result.import_stats.created}</strong> thêm mới ·{' '}
          <strong>{result.import_stats.updated}</strong> cập nhật theo mã tham chiếu
          {result.import_stats.orders_synced > 0
            ? ` · ${result.import_stats.orders_synced} đơn shop đã đồng bộ gửi EMS`
            : ''}
          {result.import_stats.skipped_no_reference > 0
            ? ` · ${result.import_stats.skipped_no_reference} dòng bỏ qua (thiếu mã tham chiếu)`
            : ''}
        </div>
      ) : null}

      {trackingJob && ['queued', 'running'].includes(trackingJob.status) ? (
        <div className="bg-indigo-50 border border-indigo-200 text-indigo-900 rounded-lg px-4 py-3 text-sm">
          <div className="font-medium">Đang tra EMS nền trên server…</div>
          <div className="mt-1">
            {trackingJob.message || 'Đang xử lý…'} ({trackingJob.processed}/{trackingJob.total})
          </div>
          <div className="mt-2 h-2 rounded-full bg-indigo-100 overflow-hidden">
            <div
              className="h-full bg-indigo-500 transition-all duration-500"
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

      {listLoading ? (
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
                onClick={() => setFilter(key as FilterKey)}
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
                        onClick={() => setFilter(item.key as FilterKey)}
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

          <section className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
            <div className="px-4 py-3 border-b border-gray-100 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Bảng vận chuyển EMS</h2>
                <span className="text-sm text-gray-500">
                  {filteredRows.length} dòng
                  {selectedKeys.size > 0 ? ` · đã chọn ${selectedKeys.size}` : ''}
                </span>
              </div>
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
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-gray-50 text-gray-600">
                  <tr>
                    <th className="px-3 py-2 w-10">
                      <input
                        type="checkbox"
                        checked={allFilteredSelected}
                        ref={(el) => {
                          if (el) el.indeterminate = !allFilteredSelected && someFilteredSelected;
                        }}
                        onChange={toggleAllFiltered}
                        aria-label="Chọn tất cả dòng đang hiển thị"
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
                  {filteredRows.length === 0 ? (
                    <tr>
                      <td colSpan={13} className="px-4 py-8 text-center text-gray-500">
                        {result.rows.length === 0
                          ? 'Chưa có dòng nào. Upload file Excel EMS để bắt đầu.'
                          : 'Không có dòng nào trong bộ lọc này.'}
                      </td>
                    </tr>
                  ) : (
                    filteredRows.map((row) => {
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
                            {formatVnd(row.cod_amount)}
                          </td>
                          <td className="px-3 py-3 text-right tabular-nums whitespace-nowrap">
                            <div>{formatVnd(row.cod_paid_amount)}</div>
                            {row.cod_paid_date ? (
                              <div className="text-xs text-gray-500 mt-1">{row.cod_paid_date}</div>
                            ) : null}
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
                                {orderStatusLabel(row.order_status)}
                              </span>
                            ) : row.order_code ? (
                              <span className="text-xs text-amber-700">Không khớp đơn khách</span>
                            ) : (
                              '—'
                            )}
                            {row.current_step_key ? (
                              <div className="text-xs text-gray-500 mt-1.5">
                                {TIMELINE_STEP_LABELS[row.current_step_key] || row.current_step_key}
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
          </section>
        </>
      ) : null}

      {orderStatusModal ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
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
                    <h4 className="text-sm font-semibold text-gray-900 mb-2">Lịch trình giao hàng</h4>
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
