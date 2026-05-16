'use client';

import { Fragment, type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import {
  DEFAULT_MNT_PER_CNY_FOR_HIBOX_LISTING,
  DEFAULT_VND_PER_CNY_FOR_LISTING_ESTIMATE,
  applyHiboxMntRateToRow,
  estimateListingVndRounded,
  extractOfferId1688FromHref,
  parseTaobaoListingHtml,
  rowsToCsv,
  type ParsedTaobaoCardRow,
} from '@/lib/taobao-cards-html-parse';
import Link from 'next/link';
import {
  adminProductAPI,
  type AdminImport1688Draft,
  type AdminListingImportQueueItem,
  type AdminListingImportQueueRunsResponse,
  type AdminListingImportQueueStatus,
} from '@/lib/admin-api';
import {
  IMPORT_1688_EXCEL_COLUMNS,
  excelExportRowFromProductData,
} from '@/lib/import-1688-excel-export-preview';
import {
  getListingDraftPublishBlockers,
  isListingDraftPublishReady,
} from '@/lib/listing-draft-publish-validation';

/** Lưu ô «₮ / 1 CN¥» (quy Hibox → tệ). */
const TAOBAO_CARDS_PARSE_MNT_PER_CNY_LS_KEY = 'admin.products.taobao_cards_parse.mnt_per_cny';
/** Lưu ô «Tỷ giá» (chuỗi gõ tay) để lần sau không phải nhập lại. */
const TAOBAO_CARDS_PARSE_VND_PER_CNY_LS_KEY = 'admin.products.taobao_cards_parse.vnd_per_cny';
/** Lưu queue_token hàng đợi import trên server (theo dõi / tạm dừng / CSV). */
const TAOBAO_LISTING_QUEUE_TOKEN_LS_KEY = 'admin.products.taobao_cards_parse.listing_queue_token';
/** Danh sách các đợt đang theo dõi đồng thời (JSON string[]); thứ tự hiển thị sắp cũ → mới theo created_at. */
const TAOBAO_TRACKED_QUEUE_TOKENS_LS_KEY = 'admin.products.taobao_cards_parse.tracked_queue_tokens';
/** Thu gọn panel tiến độ (không xóa token — có thể «Hiện panel» lại). */
const TAOBAO_LISTING_QUEUE_PANEL_COLLAPSED_LS_KEY =
  'admin.products.taobao_cards_parse.listing_queue_panel_collapsed';
/** Lưu dropdown «Trang lấy dữ liệu» (import listing → nháp). */
const TAOBAO_CARDS_PARSE_IMPORT_TARGET_LS_KEY = 'admin.products.taobao_cards_parse.import_fetch_target';

/** Chuẩn hoá như backend (A|T + chỉ chữ số). */
function normalizeListingParserItemId(raw: string): string {
  const t = raw.trim();
  const m = t.match(/^([aAtT])(\d+)$/);
  if (m) return `${m[1].toUpperCase()}${m[2]}`;
  return t;
}

/**
 * Kiểm tra các ký tự của needle (so khớp không phân biệt hoa thường Latin) xuất hiện
 * trong haystack đúng thứ tự — giữa hai ký tự được phép chen ký tự khác.
 */
function isSubsequenceIgnoreCase(needle: string, haystack: string): boolean {
  if (!needle) return true;
  const n = needle.toLowerCase();
  const h = (haystack || '').toLowerCase();
  let i = 0;
  for (let j = 0; j < h.length && i < n.length; j++) {
    if (h[j] === n[i]) i += 1;
  }
  return i === n.length;
}

/** Lọc tiêu đề không cần liên tục; vài cụm cách bằng khoảng trắng → mỗi cụm phải thỏa (AND). */
function titleMatchesFlexibleFilter(titleRaw: string, filterTrimmed: string): boolean {
  const parts = filterTrimmed.toLowerCase().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return true;
  const title = titleRaw || '';
  return parts.every((chunk) => isSubsequenceIgnoreCase(chunk, title));
}

/** Biên VNĐ trong ô lọc (cho phép «1.490.000», khoảng trắng). Trống → không giới hạn phía đó. */
function parseVndFilterBound(raw: string): number | null {
  const t = raw.trim();
  if (!t) return null;
  const digits = t.replace(/\D/g, '');
  if (!digits) return null;
  const n = Number(digits);
  if (!Number.isFinite(n) || n < 0) return null;
  return n;
}

function priceVndBoundsSummary(bounds: { lo: number | null; hi: number | null }): ReactNode {
  const { lo, hi } = bounds;
  const fmt = (n: number) => (
    <span className="font-medium tabular-nums">{new Intl.NumberFormat('vi-VN').format(n)} ₫</span>
  );
  if (lo != null && hi != null) return <>khoảng giá ~VNĐ từ {fmt(lo)} đến {fmt(hi)}</>;
  if (lo != null) return <>giá ~VNĐ từ {fmt(lo)} trở lên</>;
  if (hi != null) return <>giá ~VNĐ đến {fmt(hi)}</>;
  return null;
}

function formatVndApproxCell(n: number | null): string {
  if (n == null || !Number.isFinite(n)) return '—';
  return new Intl.NumberFormat('vi-VN').format(n) + ' ₫';
}

function formatApproxCnyCell(n: number): string {
  return new Intl.NumberFormat('vi-VN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n);
}

/** Đủ dữ liệu các cột chính trong bảng (loại dòng chỉ có giá/ảnh nhưng thiếu ID, link, shop…). Lưới Hibox không có shop/tag trong DOM. */
function isListingRowComplete(r: ParsedTaobaoCardRow, vndPerCny: number): boolean {
  const nonEmpty = (x: string) => (x || '').trim().length > 0;
  const fromHiboxGrid =
    r.parsed_source === 'hibox_grid' || r.parsed_source === '1688_text_table';
  if (!nonEmpty(r.item_id)) return false;
  if (!nonEmpty(r.item_url)) return false;
  if (!fromHiboxGrid) {
    if (!nonEmpty(r.shop_name)) return false;
    if (!nonEmpty(r.tags)) return false;
  }
  if (!nonEmpty(r.title)) return false;
  if (r.parsed_source !== '1688_text_table' && !nonEmpty(r.main_image_url)) return false;
  if (!nonEmpty(r.price_raw)) return false;
  if (estimateListingVndRounded(r, vndPerCny) == null) return false;
  return true;
}

/** Hiển thị đợt cũ trước, đợt mới sau (theo created_at server). */
function sortQueueTokensOldestFirst(
  tokens: string[],
  byToken: Record<string, AdminListingImportQueueStatus | undefined>,
): string[] {
  return [...tokens].sort((a, b) => {
    const ca = byToken[a]?.created_at;
    const cb = byToken[b]?.created_at;
    const na = ca && !Number.isNaN(Date.parse(ca)) ? Date.parse(ca) : Number.MAX_SAFE_INTEGER;
    const nb = cb && !Number.isNaN(Date.parse(cb)) ? Date.parse(cb) : Number.MAX_SAFE_INTEGER;
    if (na !== nb) return na - nb;
    return a.localeCompare(b);
  });
}

function progressPctForQueue(st: AdminListingImportQueueStatus | undefined): number {
  const c = st?.counts;
  if (!c?.total) return 0;
  return Math.min(100, Math.round(((c.done + c.error) / c.total) * 100));
}

function currentItemLabelForQueue(st: AdminListingImportQueueStatus | undefined): string | null {
  if (!st?.current_item_id) return null;
  const it = st.items.find((x) => x.id === st.current_item_id);
  return it?.label || it?.url?.slice(0, 52) || st.current_item_id;
}

function formatDraftPriceLine(pd: Record<string, unknown> | undefined): string | null {
  if (!pd) return null;
  const p = pd.price;
  if (typeof p === 'number' && Number.isFinite(p))
    return `${new Intl.NumberFormat('vi-VN').format(p)} ₫`;
  if (typeof p === 'string' && p.trim()) {
    const n = Number.parseFloat(p.replace(/\s/g, '').replace(/,/g, ''));
    if (Number.isFinite(n)) return `${new Intl.NumberFormat('vi-VN').format(n)} ₫`;
  }
  return null;
}

/** Ô bảng modal «đăng web» — khớp cột Excel Export/Import 1688. */
function renderDoneDraftModalExcelCell(
  colKey: string,
  rawValue: string | number,
  pd: Record<string, unknown> | undefined,
): ReactNode {
  if (colKey === 'price') {
    const line = formatDraftPriceLine(pd);
    if (line) return line;
    if (typeof rawValue === 'number' && Number.isFinite(rawValue) && rawValue !== 0) {
      return `${new Intl.NumberFormat('vi-VN').format(rawValue)} ₫`;
    }
    return '—';
  }
  const str =
    typeof rawValue === 'number' && Number.isFinite(rawValue)
      ? String(rawValue)
      : String(rawValue ?? '').trim();
  if (
    (colKey === 'product_url' || colKey === 'video_url' || colKey === 'main_image') &&
    /^https?:\/\//i.test(str)
  ) {
    return (
      <a href={str} target="_blank" rel="noopener noreferrer" className="text-indigo-700 underline" title={str}>
        {str}
      </a>
    );
  }
  if (!str) return '—';
  const ellipsize =
    colKey === 'gallery_images' ||
    colKey === 'detail_images' ||
    colKey === 'sizes' ||
    colKey === 'Variant' ||
    colKey === 'Features' ||
    colKey === 'product_info' ||
    colKey === 'pro_content';
  if (ellipsize && str.length > 120) {
    return (
      <span className="font-mono text-[10px]" title={str}>
        {`${str.slice(0, 120)}…`}
      </span>
    );
  }
  return str;
}

function strPd(v: unknown): string {
  if (v == null) return '';
  if (typeof v === 'string') return v.trim();
  if (typeof v === 'number' || typeof v === 'boolean') return String(v);
  return '';
}

/**
 * Khóa đối chiếu API `/products/listing-parser-db-presence`: tiền tố A|T + chữ số trước `a188…`
 * trong product_id (vd `A942397061385` từ `A942397061385a188X0793`).
 */
function draftListingPresenceKeyFromProductData(pd: Record<string, unknown> | undefined): string | null {
  if (!pd) return null;
  const raw = strPd(pd.product_id);
  if (!raw) return null;
  const lower = raw.toLowerCase();
  const idx = lower.indexOf('a188');
  const base = idx > 0 ? raw.slice(0, idx).trim() : raw.trim();
  const norm = normalizeListingParserItemId(base);
  if (/^[AT]\d+$/i.test(norm)) return norm;
  return null;
}

function draftRowAlreadyInShop(
  row: { draft: AdminImport1688Draft | null; fetchErr?: string },
  shopPresenceKeys: Set<string>,
): boolean {
  if (row.fetchErr || !row.draft?.product_data) return false;
  const k = draftListingPresenceKeyFromProductData(row.draft.product_data as Record<string, unknown>);
  return k != null && shopPresenceKeys.has(k);
}

type DoneDraftPublishLineStatus = 'queued' | 'running' | 'ok' | 'err';

type DoneDraftPublishLine = {
  draftId: number;
  label: string;
  status: DoneDraftPublishLineStatus;
  detail?: string;
};

function draftModalRowTitle(draft: AdminImport1688Draft | null): string {
  const pd = draft?.product_data as Record<string, unknown> | undefined;
  if (!pd) return '(không có tiêu đề)';
  const name = strPd(pd.name);
  const title = strPd(pd.title);
  const s = name || title;
  if (!s) return `(nháp #${draft?.id ?? '?'})`;
  return s.length > 80 ? `${s.slice(0, 80)}…` : s;
}

/** Khớp khóa dòng trong bảng sau lọc. */
function stableListingRowKey(r: ParsedTaobaoCardRow): string {
  return r.item_id ? `row-${r.row}-id-${r.item_id}` : `${r.row}-${r.main_image_url.slice(0, 64)}`;
}

/**
 * URL Hibox để backend import (Playwright): 1688 → `abb-{offerId}`, Taobao/Tmall → slug số.
 * Khớp mẫu `export_hibox_item_excel.py` / ví dụ nguồn dự án.
 */
function listingRowToHiboxImportUrl(r: ParsedTaobaoCardRow): string | null {
  const id = (r.item_id || '').trim();
  const u = (r.item_url || '').trim().toLowerCase();

  const onlyDigits = (s: string) => s.replace(/\D/g, '');

  if (/^a\d+$/i.test(id)) return `https://hibox.mn/v/abb-${id.slice(1)}`;
  if (/^t\d+$/i.test(id)) return `https://hibox.mn/v/${id.slice(1)}`;

  if (/^\d+$/.test(id)) {
    if (u.includes('1688.com')) return `https://hibox.mn/v/abb-${id}`;
    if (u.includes('taobao') || u.includes('tmall')) return `https://hibox.mn/v/${id}`;
    return null;
  }

  const digs = onlyDigits(id);
  if (!digs) return null;
  if (u.includes('1688.com')) return `https://hibox.mn/v/abb-${digs}`;
  if (u.includes('taobao') || u.includes('tmall')) return `https://hibox.mn/v/${digs}`;
  return null;
}

type ListingImportSource = '1688' | 'hibox';
type ListingImportFetchTarget = 'auto' | 'hibox' | '1688';

/** Offer id: từ href 1688 hoặc ID SP dạng A+digits. */
function pick1688OfferIdFromListingRow(r: ParsedTaobaoCardRow): string | null {
  const fromHref = extractOfferId1688FromHref(r.item_url || '');
  if (fromHref) return fromHref;
  const id = (r.item_id || '').trim();
  const m = /^A(\d{6,})$/i.exec(id);
  return m?.[1] ?? null;
}

function listingRowTo1688DetailPcUrl(r: ParsedTaobaoCardRow): string | null {
  const oid = pick1688OfferIdFromListingRow(r);
  if (!oid) return null;
  return `https://detail.1688.com/offer/${oid}.html`;
}

/** Ghép URL + source API theo dropdown (khớp luồng Excel batch / backend). */
function resolveListingImportTask(
  r: ParsedTaobaoCardRow,
  target: ListingImportFetchTarget,
): { url: string; source: ListingImportSource } | null {
  const hiboxUrl = listingRowToHiboxImportUrl(r);
  const detail1688 = listingRowTo1688DetailPcUrl(r);

  if (target === 'hibox') {
    if (!hiboxUrl) return null;
    return { url: hiboxUrl, source: 'hibox' };
  }
  if (target === '1688') {
    if (!detail1688) return null;
    return { url: detail1688, source: '1688' };
  }
  if (hiboxUrl) return { url: hiboxUrl, source: 'hibox' };
  if (detail1688) return { url: detail1688, source: '1688' };
  return null;
}

function listingQueueRunStatusLabel(
  s: AdminListingImportQueueStatus | null,
): { title: string; hint?: string } {
  if (!s) return { title: '—' };
  const rs = s.run_status || '';
  if (s.stop_requested || rs === 'stopped') return { title: 'Đã dừng hẳn', hint: 'Không tiếp tục được — thêm link mới để tạo đợt mới.' };
  if (rs === 'paused') return { title: 'Tạm dừng', hint: 'Bấm «Tiếp tục» để chạy các link còn chờ.' };
  if (rs === 'completed') return { title: 'Hoàn tất', hint: 'Mọi link trong đợt đã xử lý xong.' };
  if (s.pause_requested && rs === 'running')
    return { title: 'Đang chạy', hint: 'Đã yêu cầu tạm dừng — sẽ dừng sau khi xong link hiện tại.' };
  if (rs === 'running') return { title: 'Đang chạy' };
  if (rs === 'idle') return { title: 'Chờ xử lý' };
  return { title: rs || '—' };
}

/** Danh sách đợt từ DB (thiếu cờ can_pause …) — chỉ để hiển thị nhãn trạng thái. */
function savedRunSnapshotLabel(r: {
  run_status?: string;
  pause_requested?: boolean;
  stop_requested?: boolean;
  worker_alive?: boolean;
}): { title: string; hint?: string } {
  const rs = r.run_status || '';
  if (r.stop_requested || rs === 'stopped')
    return { title: 'Đã dừng hẳn', hint: 'Không tiếp tục được.' };
  if (rs === 'paused') return { title: 'Tạm dừng', hint: 'Mở đợt rồi bấm «Tiếp tục».' };
  if (rs === 'completed') return { title: 'Hoàn tất' };
  if (r.pause_requested && rs === 'running')
    return { title: 'Đang chạy', hint: 'Đã yêu cầu tạm dừng — sẽ dừng sau link hiện tại.' };
  if (rs === 'running')
    return {
      title: 'Đang chạy',
      hint: r.worker_alive ? undefined : 'Worker có thể đang khởi động.',
    };
  if (rs === 'idle') return { title: 'Chờ xử lý' };
  return { title: rs || '—' };
}

export default function TaobaoCardsParsePage() {
  const [raw, setRaw] = useState('');
  const [rows, setRows] = useState<ParsedTaobaoCardRow[]>([]);
  const [shopFilter, setShopFilter] = useState('');
  const [titleFilter, setTitleFilter] = useState('');
  const [priceVndMinInput, setPriceVndMinInput] = useState('');
  const [priceVndMaxInput, setPriceVndMaxInput] = useState('');
  const [rateInput, setRateInput] = useState(() => String(DEFAULT_VND_PER_CNY_FOR_LISTING_ESTIMATE));

  useEffect(() => {
    try {
      const s = localStorage.getItem(TAOBAO_CARDS_PARSE_VND_PER_CNY_LS_KEY);
      if (s !== null) setRateInput(s);
    } catch {
      /* noop */
    }
  }, []);

  const persistRateInput = useCallback((next: string) => {
    setRateInput(next);
    try {
      localStorage.setItem(TAOBAO_CARDS_PARSE_VND_PER_CNY_LS_KEY, next);
    } catch {
      /* noop */
    }
  }, []);

  const [mntPerCnyInput, setMntPerCnyInput] = useState(() =>
    String(DEFAULT_MNT_PER_CNY_FOR_HIBOX_LISTING),
  );

  useEffect(() => {
    try {
      const s = localStorage.getItem(TAOBAO_CARDS_PARSE_MNT_PER_CNY_LS_KEY);
      if (s !== null && s.trim() !== '') setMntPerCnyInput(s);
    } catch {
      /* noop */
    }
  }, []);

  const persistMntPerCnyInput = useCallback((next: string) => {
    setMntPerCnyInput(next);
    try {
      localStorage.setItem(TAOBAO_CARDS_PARSE_MNT_PER_CNY_LS_KEY, next);
    } catch {
      /* noop */
    }
  }, []);

  const [importFetchTarget, setImportFetchTarget] = useState<ListingImportFetchTarget>('auto');

  useEffect(() => {
    try {
      const s = localStorage.getItem(TAOBAO_CARDS_PARSE_IMPORT_TARGET_LS_KEY);
      if (s === 'auto' || s === 'hibox' || s === '1688') setImportFetchTarget(s);
    } catch {
      /* noop */
    }
  }, []);

  const persistImportFetchTarget = useCallback((next: ListingImportFetchTarget) => {
    setImportFetchTarget(next);
    try {
      localStorage.setItem(TAOBAO_CARDS_PARSE_IMPORT_TARGET_LS_KEY, next);
    } catch {
      /* noop */
    }
  }, []);

  const [fallbackShopInput, setFallbackShopInput] = useState('');

  const [onlyCompleteListingRows, setOnlyCompleteListingRows] = useState(true);
  const [onlyMissingInDb, setOnlyMissingInDb] = useState(true);
  const [dbExistingSet, setDbExistingSet] = useState<Set<string>>(() => new Set());
  /** Tăng sau khi có SP mới trong `products` (đăng từ modal / đổi tab) hoặc thêm dòng queue `done` (nháp crawl xong) — gọi lại listing-parser-db-presence. */
  const [listingParseDbPresenceTick, setListingParseDbPresenceTick] = useState(0);
  const prevQueueDoneSumRef = useRef(0);
  const [presenceFetchKey, setPresenceFetchKey] = useState<string | null>(null);
  const [dbLookupPending, setDbLookupPending] = useState(false);
  const [dbLookupError, setDbLookupError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const headerSelectAllRef = useRef<HTMLInputElement>(null);
  const listingDraftPublishInFlightRef = useRef(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Set<string>>(() => new Set());
  const [enqueueSubmitting, setEnqueueSubmitting] = useState(false);
  /** Sau khi bấm «Lấy thông tin» — chờ user chọn đợt đích trước khi gọi API. */
  const [enqueueChoiceOpen, setEnqueueChoiceOpen] = useState(false);
  const [pendingEnqueuePayload, setPendingEnqueuePayload] = useState<{
    items: { url: string; source: ListingImportSource; label?: string }[];
    skipLines: string[];
  } | null>(null);
  const [trackedQueueTokens, setTrackedQueueTokens] = useState<string[]>([]);
  const [queuesPanelCollapsed, setQueuesPanelCollapsed] = useState(false);
  const [queueStatusByToken, setQueueStatusByToken] = useState<
    Record<string, AdminListingImportQueueStatus>
  >({});
  const [queuesPollErrorByToken, setQueuesPollErrorByToken] = useState<Record<string, string>>({});
  const [savedRunsOpen, setSavedRunsOpen] = useState(false);
  const [savedRunsLoading, setSavedRunsLoading] = useState(false);
  const [savedRunsErr, setSavedRunsErr] = useState<string | null>(null);
  const [savedRunsData, setSavedRunsData] = useState<AdminListingImportQueueRunsResponse | null>(null);
  const [savedRunDeleteToken, setSavedRunDeleteToken] = useState<string | null>(null);
  const [savedRunsDeleting, setSavedRunsDeleting] = useState(false);
  /** Token đợt đang xác nhận «xóa khỏi DB» trong panel. */
  const [dbDeleteConfirmToken, setDbDeleteConfirmToken] = useState<string | null>(null);
  const [panelDbDeleting, setPanelDbDeleting] = useState(false);
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);

  /** Modal: chọn nháp đã crawl xong để đăng lên web (publish giống Import 1688). */
  const [doneDraftsModalToken, setDoneDraftsModalToken] = useState<string | null>(null);
  const [doneDraftsModalLoading, setDoneDraftsModalLoading] = useState(false);
  const [doneDraftsModalRows, setDoneDraftsModalRows] = useState<
    {
      queueItemId: string;
      draftId: number;
      queueLabel: string;
      queueUrl: string;
      queueSnap: AdminListingImportQueueItem;
      draft: AdminImport1688Draft | null;
      fetchErr?: string;
    }[]
  >([]);
  const [doneDraftsModalSelected, setDoneDraftsModalSelected] = useState<Set<number>>(() => new Set());
  const [doneDraftsPublishing, setDoneDraftsPublishing] = useState(false);
  const [doneDraftsPublishLines, setDoneDraftsPublishLines] = useState<DoneDraftPublishLine[]>([]);
  /** Mã A946…/T… đã có trong `products` (API listing-parser-db-presence). */
  const [doneDraftsShopPresenceKeys, setDoneDraftsShopPresenceKeys] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    try {
      let loaded: string[] = [];
      const rawMulti = localStorage.getItem(TAOBAO_TRACKED_QUEUE_TOKENS_LS_KEY);
      if (rawMulti) {
        const parsed = JSON.parse(rawMulti) as unknown;
        if (Array.isArray(parsed)) {
          loaded = parsed.filter((x): x is string => typeof x === 'string' && x.trim().length > 0);
        }
      }
      if (loaded.length === 0) {
        const legacy = localStorage.getItem(TAOBAO_LISTING_QUEUE_TOKEN_LS_KEY);
        if (legacy?.trim()) loaded = [legacy.trim()];
      }
      if (loaded.length > 0) setTrackedQueueTokens(loaded);
      const collapsed = localStorage.getItem(TAOBAO_LISTING_QUEUE_PANEL_COLLAPSED_LS_KEY);
      setQueuesPanelCollapsed(collapsed === '1' || collapsed === 'true');
    } catch {
      /* noop */
    }
  }, []);

  useEffect(() => {
    if (!trackedQueueTokens.length) {
      setQueueStatusByToken({});
      setQueuesPollErrorByToken({});
      return;
    }
    let cancelled = false;
    const tick = async () => {
      const slice = [...trackedQueueTokens];
      const outcomes = await Promise.allSettled(
        slice.map((token) => adminProductAPI.getListingImportQueueStatus(token)),
      );
      if (cancelled) return;
      const dead: string[] = [];
      const nextErr: Record<string, string> = {};
      setQueueStatusByToken((prev) => {
        const next = { ...prev };
        outcomes.forEach((r, i) => {
          const tok = slice[i];
          if (r.status === 'fulfilled') next[tok] = r.value;
        });
        return next;
      });
      outcomes.forEach((r, i) => {
        const tok = slice[i];
        if (r.status === 'rejected') {
          const msg = r.reason instanceof Error ? r.reason.message : String(r.reason);
          nextErr[tok] = msg;
          if (/404|không tìm thấy|not found/i.test(msg)) dead.push(tok);
        }
      });
      setQueuesPollErrorByToken(nextErr);
      if (dead.length) {
        setTrackedQueueTokens((p) => p.filter((x) => !dead.includes(x)));
        setQueueStatusByToken((p) => {
          const n = { ...p };
          dead.forEach((d) => void delete n[d]);
          return n;
        });
      }
    };
    void tick();
    const id = setInterval(() => void tick(), 2500);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [trackedQueueTokens]);

  /** Khi crawl xong thêm dòng trong đợt — đối chiếu lại DB + nháp done để ẩn dòng (kể cả chưa đăng web). */
  useEffect(() => {
    let done = 0;
    for (const tok of trackedQueueTokens) {
      const c = queueStatusByToken[tok]?.counts;
      if (typeof c?.done === 'number') done += c.done;
    }
    const prev = prevQueueDoneSumRef.current;
    prevQueueDoneSumRef.current = done;
    if (!onlyMissingInDb || rows.length === 0) return;
    if (done > prev) {
      setListingParseDbPresenceTick((n) => n + 1);
    }
  }, [queueStatusByToken, onlyMissingInDb, rows.length, trackedQueueTokens]);

  useEffect(() => {
    try {
      if (trackedQueueTokens.length) {
        localStorage.setItem(TAOBAO_TRACKED_QUEUE_TOKENS_LS_KEY, JSON.stringify(trackedQueueTokens));
        const sorted = sortQueueTokensOldestFirst(trackedQueueTokens, queueStatusByToken);
        const newest = sorted[sorted.length - 1];
        if (newest) localStorage.setItem(TAOBAO_LISTING_QUEUE_TOKEN_LS_KEY, newest);
      } else {
        localStorage.removeItem(TAOBAO_TRACKED_QUEUE_TOKENS_LS_KEY);
        localStorage.removeItem(TAOBAO_LISTING_QUEUE_TOKEN_LS_KEY);
      }
    } catch {
      /* noop */
    }
  }, [trackedQueueTokens, queueStatusByToken]);

  const showToast = useCallback((type: 'ok' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 4500);
  }, []);

  const parse = useCallback(() => {
    setError(null);
    setCopied(false);
    setSelectedRowKeys(new Set());
    setFallbackShopInput('');
    try {
      localStorage.removeItem('admin.products.taobao_cards_parse.fallback_shop');
    } catch {
      /* noop */
    }
    setDbLookupError(null);
    setPresenceFetchKey(null);
    setDbExistingSet(new Set());
    const t = raw.trim();
    if (!t) {
      setRows([]);
      setError('Hãy dán HTML hoặc đoạn DOM (View Source / Copy outerHTML) vào ô bên dưới.');
      return;
    }
    try {
      const out = parseTaobaoListingHtml(t);
      setRows(out);
      setShopFilter('');
      setTitleFilter('');
      setPriceVndMinInput('');
      setPriceVndMaxInput('');
      if (out.length === 0) {
        setError(
          'Không trích được dòng nào. Taobao listing PC 2025+: `<a class="doubleCardWrapperAdapt…">`, `id="item_id_…"`, `mainPic`/`priceInt`. 1688 selloffer (s.1688.com): `<a class="search-offer-wrapper…">`, `offerId=` / `detail.m.1688.com`, `img.main-img`, `offer-title-row`. Cũng hỗ trợ cardContainer / mainImage / ảnh alicdn kèm giá-tiêu đề. Hoặc dán **bảng text backend 1688** (dòng `商品信息`, `ID: …`, hàng tab giá). Copy outerHTML `#content_items_wrapper` hoặc nhiều card; nếu không có `item.htm`/`offerId`/ảnh hoặc chỉ text SPA (và không khớp bảng text 1688) thì không có dữ liệu.',
        );
      }
    } catch (e) {
      setRows([]);
      setPresenceFetchKey(null);
      setDbExistingSet(new Set());
      setError(e instanceof Error ? e.message : 'Lỗi parse');
    }
  }, [raw]);

  const shopFilterTrimmed = shopFilter.trim();
  const fallbackShopTrimmed = useMemo(() => fallbackShopInput.trim(), [fallbackShopInput]);
  const titleFilterTrimmed = titleFilter.trim();

  /** Dòng gốc không có shop — để tooltip «đã áp shop mặc định». */
  const parsedRowKeyHadEmptyShop = useMemo(() => {
    const m = new Map<string, boolean>();
    for (const r of rows) {
      m.set(stableListingRowKey(r), !(r.shop_name || '').trim());
    }
    return m;
  }, [rows]);

  const priceVndBounds = useMemo(() => {
    let lo = parseVndFilterBound(priceVndMinInput);
    let hi = parseVndFilterBound(priceVndMaxInput);
    if (lo != null && hi != null && lo > hi) [lo, hi] = [hi, lo];
    return { lo, hi, active: lo != null || hi != null };
  }, [priceVndMinInput, priceVndMaxInput]);

  const effectiveRate = useMemo(() => {
    const n = Number(String(rateInput ?? '').trim().replace(/\s+/g, '').replace(',', '.'));
    if (!Number.isFinite(n) || n <= 0) return DEFAULT_VND_PER_CNY_FOR_LISTING_ESTIMATE;
    return n;
  }, [rateInput]);

  /** Số đơn vị ₮ (tugrik Mông Cổ) cho 1 CN¥ — chỉ ảnh hưởng dòng parse từ lưới Hibox. */
  const effectiveMntPerCny = useMemo(() => {
    const n = Number(String(mntPerCnyInput ?? '').trim().replace(/\s+/g, '').replace(',', '.'));
    if (!Number.isFinite(n) || n <= 0) return DEFAULT_MNT_PER_CNY_FOR_HIBOX_LISTING;
    return n;
  }, [mntPerCnyInput]);

  const listingRows = useMemo(() => {
    const fb = fallbackShopTrimmed;
    return rows.map((r) => {
      let x = applyHiboxMntRateToRow(r, effectiveMntPerCny);
      if (fb && !(x.shop_name || '').trim())
        x = { ...x, shop_name: fb, shop_name_chinese: (x.shop_name_chinese || '').trim() || fb };
      return x;
    });
  }, [rows, effectiveMntPerCny, fallbackShopTrimmed]);

  /** Sau lọc đủ cột + shop + tiêu đề + giá (trước lọc DB). */
  const preDbFilteredRows = useMemo(() => {
    let xs = listingRows;
    if (onlyCompleteListingRows) {
      xs = xs.filter((r) => isListingRowComplete(r, effectiveRate));
    }
    if (shopFilterTrimmed) {
      const q = shopFilterTrimmed.toLowerCase();
      xs = xs.filter((r) =>
        `${r.shop_name_chinese || ''} ${r.shop_name || ''}`.toLowerCase().includes(q),
      );
    }
    if (titleFilterTrimmed) {
      xs = xs.filter((r) => titleMatchesFlexibleFilter(`${r.chinese_name || ''} ${r.title || ''}`, titleFilterTrimmed));
    }
    if (priceVndBounds.active) {
      const { lo, hi } = priceVndBounds;
      xs = xs.filter((r) => {
        const v = estimateListingVndRounded(r, effectiveRate);
        if (v == null) return false;
        if (lo != null && v < lo) return false;
        if (hi != null && v > hi) return false;
        return true;
      });
    }
    return xs;
  }, [
    listingRows,
    onlyCompleteListingRows,
    shopFilterTrimmed,
    titleFilterTrimmed,
    priceVndBounds,
    effectiveRate,
  ]);

  const idsForDbLookupKey = useMemo(
    () =>
      [...new Set(rows.map((r) => normalizeListingParserItemId(r.item_id)).filter(Boolean))]
        .sort()
        .join('|'),
    [rows],
  );

  useEffect(() => {
    if (!onlyMissingInDb || rows.length === 0 || !idsForDbLookupKey) {
      return;
    }
    const ids = idsForDbLookupKey.split('|').filter(Boolean);
    let active = true;
    setDbLookupPending(true);
    setDbLookupError(null);
    void adminProductAPI
      .listingParserDbPresence(ids)
      .then((res) => {
        if (!active) return;
        setDbExistingSet(new Set(res.existing_normalized ?? []));
        setPresenceFetchKey(idsForDbLookupKey);
      })
      .catch((err: unknown) => {
        if (!active) return;
        const msg =
          err instanceof Error
            ? err.message
            : 'Không đối chiếu được DB (kiểm tra mạng và quyền module sản phẩm).';
        setDbLookupError(msg);
        setOnlyMissingInDb(false);
        setPresenceFetchKey(null);
        setDbExistingSet(new Set());
      })
      .finally(() => {
        if (active) setDbLookupPending(false);
      });
    return () => {
      active = false;
    };
  }, [onlyMissingInDb, idsForDbLookupKey, rows.length, listingParseDbPresenceTick]);

  /** Quay lại tab: đối chiếu lại khi đang lọc (shop + nháp xong). */
  useEffect(() => {
    if (!onlyMissingInDb || rows.length === 0) return undefined;
    const onVis = () => {
      if (document.visibilityState === 'visible') {
        setListingParseDbPresenceTick((n) => n + 1);
      }
    };
    document.addEventListener('visibilitychange', onVis);
    return () => document.removeEventListener('visibilitychange', onVis);
  }, [onlyMissingInDb, rows.length]);

  const dbPresenceReady =
    onlyMissingInDb && !!idsForDbLookupKey && presenceFetchKey === idsForDbLookupKey;

  const displayRows = useMemo(() => {
    let xs = preDbFilteredRows;
    if (onlyMissingInDb && dbPresenceReady) {
      xs = xs.filter((r) => !dbExistingSet.has(normalizeListingParserItemId(r.item_id)));
    }
    return xs;
  }, [preDbFilteredRows, onlyMissingInDb, dbPresenceReady, dbExistingSet]);

  const emptyFilterBannerChunks = useMemo(() => {
    const chunks: ReactNode[] = [];
    if (shopFilterTrimmed)
      chunks.push(
        <>
          shop <span className="font-medium">{shopFilterTrimmed}</span>
        </>,
      );
    if (titleFilterTrimmed)
      chunks.push(
        <>
          cụm tiêu đề <span className="font-medium">{titleFilterTrimmed}</span> (chữ không cần liền)
        </>,
      );
    if (priceVndBounds.active) {
      const p = priceVndBoundsSummary(priceVndBounds);
      if (p) chunks.push(p);
    }
    if (onlyCompleteListingRows) {
      chunks.push(
        <>
          yêu cầu đủ các cột:{' '}
          <span className="font-medium">
            ID SP, link SP, tiêu đề, giá Tệ và ~VNĐ (ảnh bắt buộc trừ bảng text 1688; shop/tag không bắt buộc với Hibox / bảng text 1688)
          </span>
        </>,
      );
    }
    return chunks;
  }, [shopFilterTrimmed, titleFilterTrimmed, priceVndBounds, onlyCompleteListingRows]);

  useEffect(() => {
    const allowed = new Set(displayRows.map((r) => stableListingRowKey(r)));
    setSelectedRowKeys((prev) => new Set([...prev].filter((k) => allowed.has(k))));
  }, [displayRows]);

  const selectedOnPage = useMemo(
    () => displayRows.filter((r) => selectedRowKeys.has(stableListingRowKey(r))),
    [displayRows, selectedRowKeys],
  );

  const allVisibleSelected =
    displayRows.length > 0 && selectedOnPage.length === displayRows.length;

  useEffect(() => {
    const el = headerSelectAllRef.current;
    if (!el) return;
    el.indeterminate = selectedOnPage.length > 0 && !allVisibleSelected;
  }, [selectedOnPage.length, allVisibleSelected, displayRows.length]);

  const toggleSelectAllVisible = useCallback(() => {
    if (!displayRows.length || enqueueSubmitting) return;
    if (allVisibleSelected) {
      setSelectedRowKeys(new Set());
    } else {
      setSelectedRowKeys(new Set(displayRows.map((r) => stableListingRowKey(r))));
    }
  }, [displayRows, allVisibleSelected, enqueueSubmitting]);

  const toggleRowSelected = useCallback(
    (key: string) => {
      if (enqueueSubmitting) return;
      setSelectedRowKeys((prev) => {
        const n = new Set(prev);
        if (n.has(key)) n.delete(key);
        else n.add(key);
        return n;
      });
    },
    [enqueueSubmitting],
  );

  const displayQueueTokens = useMemo(
    () => sortQueueTokensOldestFirst(trackedQueueTokens, queueStatusByToken),
    [trackedQueueTokens, queueStatusByToken],
  );

  const newestTrackedQueueToken =
    displayQueueTokens.length > 0 ? displayQueueTokens[displayQueueTokens.length - 1] : null;

  const newestTrackedQueueStatus = newestTrackedQueueToken
    ? queueStatusByToken[newestTrackedQueueToken]
    : undefined;

  /** «Thêm vào đợt đang mở» = thêm vào đợt mới nhất (cuối danh sách cũ→mới), nếu đợt đó chưa dừng hẳn. */
  const appendToCurrentQueueOption = useMemo(() => {
    if (!newestTrackedQueueToken) {
      return {
        disabled: true as const,
        hint: 'Chưa có đợt đang theo dõi — chỉ có thể tạo đợt mới (hoặc mở từ «Đợt đã lưu»).',
      };
    }
    const st = newestTrackedQueueStatus;
    if (st && (st.stop_requested || st.run_status === 'stopped')) {
      return {
        disabled: true as const,
        hint: 'Đợt mới nhất (cuối danh sách) đã dừng hẳn — chọn «Tạo đợt mới» hoặc chỉnh đợt khác.',
      };
    }
    return { disabled: false as const, hint: null as string | null };
  }, [newestTrackedQueueToken, newestTrackedQueueStatus]);

  const removeTrackedQueueToken = useCallback((token: string) => {
    setTrackedQueueTokens((p) => p.filter((x) => x !== token));
    setQueueStatusByToken((p) => {
      const n = { ...p };
      delete n[token];
      return n;
    });
    setQueuesPollErrorByToken((p) => {
      const n = { ...p };
      delete n[token];
      return n;
    });
    setDbDeleteConfirmToken((cur) => (cur === token ? null : cur));
  }, []);

  const openListingEnqueueChoice = useCallback(() => {
    const ordered = displayRows.filter((r) => selectedRowKeys.has(stableListingRowKey(r)));
    if (!ordered.length) {
      showToast('err', 'Chọn ít nhất một dòng trong bảng.');
      return;
    }

    const tasks: { row: ParsedTaobaoCardRow; url: string; source: ListingImportSource }[] = [];
    const skipLines: string[] = [];
    for (const r of ordered) {
      const task = resolveListingImportTask(r, importFetchTarget);
      if (!task) {
        skipLines.push(
          importFetchTarget === '1688'
            ? `${r.item_id || '—'}: không ghép được link 1688 (cần offer trong URL hoặc ID SP dạng A+số).`
            : importFetchTarget === 'hibox'
              ? `${r.item_id || '—'}: không ghép được link Hibox (cần link 1688/Taobao/Tmall và mã sản phẩm).`
              : `${r.item_id || '—'}: không ghép được URL import — thử đổi «Trang lấy dữ liệu» (Hibox / 1688).`,
        );
        continue;
      }
      tasks.push({ row: r, url: task.url, source: task.source });
    }

    if (!tasks.length) {
      showToast(
        'err',
        'Không có dòng nào ghép được URL để import (kiểm tra link HTML và menu «Trang lấy dữ liệu»).',
      );
      return;
    }

    setPendingEnqueuePayload({
      items: tasks.map((t) => ({
        url: t.url,
        source: t.source,
        label: t.row.item_id || undefined,
      })),
      skipLines,
    });
    setEnqueueChoiceOpen(true);
  }, [displayRows, selectedRowKeys, showToast, importFetchTarget]);

  const cancelListingEnqueueChoice = useCallback(() => {
    if (enqueueSubmitting) return;
    setEnqueueChoiceOpen(false);
    setPendingEnqueuePayload(null);
  }, [enqueueSubmitting]);

  const submitListingEnqueue = useCallback(
    async (mode: 'append' | 'new') => {
      if (!pendingEnqueuePayload) return;
      if (mode === 'append' && appendToCurrentQueueOption.disabled) {
        showToast('err', appendToCurrentQueueOption.hint || 'Không thể thêm vào đợt hiện tại.');
        return;
      }

      const queue_token =
        mode === 'append' && newestTrackedQueueToken && !appendToCurrentQueueOption.disabled
          ? newestTrackedQueueToken
          : undefined;

      const hadOtherQueuesBeforeNew = mode === 'new' && trackedQueueTokens.length > 0;

      const skipLines = pendingEnqueuePayload.skipLines;
      const items = pendingEnqueuePayload.items;

      setEnqueueSubmitting(true);
      try {
        const res = await adminProductAPI.enqueueListingImportQueue({
          queue_token,
          items,
        });
        setEnqueueChoiceOpen(false);
        setPendingEnqueuePayload(null);
        setTrackedQueueTokens((prev) =>
          prev.includes(res.queue_token) ? prev : [...prev, res.queue_token],
        );
        setQueuesPanelCollapsed(false);
        try {
          localStorage.removeItem(TAOBAO_LISTING_QUEUE_PANEL_COLLAPSED_LS_KEY);
        } catch {
          /* noop */
        }
        const st = await adminProductAPI.getListingImportQueueStatus(res.queue_token);
        setQueueStatusByToken((prev) => ({ ...prev, [res.queue_token]: st }));

        const nAdded = items.length;
        setSelectedRowKeys((prev) => {
          const next = new Set(prev);
          for (const it of items) {
            const lab = (it.label || '').trim();
            const uEnqueue = (it.url || '').trim();
            const hit = displayRows.find((r) => {
              if (lab && (r.item_id || '').trim() === lab) return true;
              const uRow = (r.item_url || '').trim();
              return Boolean(uEnqueue && uRow && uEnqueue === uRow);
            });
            if (hit) next.delete(stableListingRowKey(hit));
          }
          return next;
        });

        const modeLabel =
          importFetchTarget === 'hibox'
            ? 'qua Hibox'
            : importFetchTarget === '1688'
              ? 'qua 1688 trực tiếp'
              : 'tự chọn Hibox hoặc 1688';
        const scopeLabel =
          mode === 'append' && queue_token
            ? 'Đã thêm vào đợt đang mở (đợt mới nhất trong danh sách).'
            : 'Đã tạo job mới — worker và hàng đợi riêng trên server, chạy độc lập với các đợt khác.';
        const parallelNote = mode === 'new' && hadOtherQueuesBeforeNew
          ? ' Các đợt khác vẫn trong danh sách (cũ → mới), không bị dừng.'
          : '';

        if (skipLines.length) {
          showToast(
            'ok',
            `${res.message} · Đã bỏ chọn ${nAdded} dòng đã gửi. (${modeLabel}). ${scopeLabel}${parallelNote} ${skipLines.length} dòng không ghép URL — không thêm vào đợt.`,
          );
        } else {
          showToast(
            'ok',
            `${res.message} · Đã bỏ chọn ${nAdded} dòng đã gửi. (${modeLabel}). ${scopeLabel}${parallelNote} Xử lý lần lượt trong đợt này — theo dõi trong danh sách bên dưới.`,
          );
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        showToast('err', msg);
      } finally {
        setEnqueueSubmitting(false);
      }
    },
    [
      pendingEnqueuePayload,
      trackedQueueTokens.length,
      newestTrackedQueueToken,
      appendToCurrentQueueOption.disabled,
      appendToCurrentQueueOption.hint,
      showToast,
      importFetchTarget,
      displayRows,
    ],
  );

  useEffect(() => {
    if (!enqueueChoiceOpen) return;
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape' && !enqueueSubmitting) cancelListingEnqueueChoice();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [enqueueChoiceOpen, enqueueSubmitting, cancelListingEnqueueChoice]);

  const pauseListingQueue = useCallback(async (token: string) => {
    try {
      await adminProductAPI.pauseListingImportQueue(token);
      const st = await adminProductAPI.getListingImportQueueStatus(token);
      setQueueStatusByToken((prev) => ({ ...prev, [token]: st }));
      showToast('ok', 'Đã yêu cầu tạm dừng sau khi xong link hiện tại.');
    } catch (e) {
      showToast('err', e instanceof Error ? e.message : String(e));
    }
  }, [showToast]);

  const resumeListingQueue = useCallback(async (token: string) => {
    try {
      await adminProductAPI.resumeListingImportQueue(token);
      const st = await adminProductAPI.getListingImportQueueStatus(token);
      setQueueStatusByToken((prev) => ({ ...prev, [token]: st }));
      showToast('ok', 'Đã tiếp tục hàng đợi trên server.');
    } catch (e) {
      showToast('err', e instanceof Error ? e.message : String(e));
    }
  }, [showToast]);

  const stopListingQueue = useCallback(async (token: string) => {
    try {
      await adminProductAPI.stopListingImportQueue(token);
      const st = await adminProductAPI.getListingImportQueueStatus(token);
      setQueueStatusByToken((prev) => ({ ...prev, [token]: st }));
      showToast('ok', 'Đã dừng hẳn đợt này — không thể «Tiếp tục»; có thể thêm link để tạo đợt mới.');
    } catch (e) {
      showToast('err', e instanceof Error ? e.message : String(e));
    }
  }, [showToast]);

  const downloadListingQueueCsv = useCallback(
    async (token: string) => {
      const st = queueStatusByToken[token];
      const done = st?.counts?.done ?? 0;
      const err = st?.counts?.error ?? 0;
      if (done + err === 0) {
        showToast('err', 'Chưa có dòng nào xử lý xong (ok hoặc lỗi) — không có gì để xuất CSV kết quả.');
        return;
      }
      try {
        await adminProductAPI.downloadListingImportQueueCsv(token, { finishedOnly: true });
        showToast('ok', `Đã tải CSV kết quả (${done} ok, ${err} lỗi).`);
      } catch (e) {
        showToast('err', e instanceof Error ? e.message : String(e));
      }
    },
    [queueStatusByToken, showToast],
  );

  const downloadListingQueueProductsExcel = useCallback(
    async (token: string) => {
      const st = queueStatusByToken[token];
      const done = st?.counts?.done ?? 0;
      const err = st?.counts?.error ?? 0;
      if (done + err === 0) {
        showToast('err', 'Chưa có dòng nào kết thúc — chưa có draft để xuất Excel.');
        return;
      }
      try {
        await adminProductAPI.downloadListingImportQueueProductsExcel(token);
        showToast('ok', 'Đã tải Excel nhập web (tiêu đề, giá, ảnh, biến thể… — giống export bulk draft).');
      } catch (e) {
        showToast('err', e instanceof Error ? e.message : String(e));
      }
    },
    [queueStatusByToken, showToast],
  );

  const forgetAllTrackedQueues = useCallback(() => {
    try {
      localStorage.removeItem(TAOBAO_TRACKED_QUEUE_TOKENS_LS_KEY);
      localStorage.removeItem(TAOBAO_LISTING_QUEUE_TOKEN_LS_KEY);
      localStorage.removeItem(TAOBAO_LISTING_QUEUE_PANEL_COLLAPSED_LS_KEY);
    } catch {
      /* noop */
    }
    setTrackedQueueTokens([]);
    setQueueStatusByToken({});
    setQueuesPollErrorByToken({});
    setQueuesPanelCollapsed(false);
    setDbDeleteConfirmToken(null);
  }, []);

  const collapseQueuesPanel = useCallback(() => {
    setQueuesPanelCollapsed(true);
    try {
      localStorage.setItem(TAOBAO_LISTING_QUEUE_PANEL_COLLAPSED_LS_KEY, '1');
    } catch {
      /* noop */
    }
    showToast(
      'ok',
      'Đã thu gọn panel — bấm «Hiện panel» để xem lại các đợt đang theo dõi (cũ → mới).',
    );
  }, [showToast]);

  const expandQueuesPanel = useCallback(() => {
    setQueuesPanelCollapsed(false);
    try {
      localStorage.removeItem(TAOBAO_LISTING_QUEUE_PANEL_COLLAPSED_LS_KEY);
    } catch {
      /* noop */
    }
  }, []);

  const loadSavedRuns = useCallback(async () => {
    setSavedRunsLoading(true);
    setSavedRunsErr(null);
    try {
      const data = await adminProductAPI.listListingImportQueueRuns({ limit: 80, offset: 0 });
      setSavedRunsData(data);
    } catch (e) {
      setSavedRunsErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSavedRunsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!savedRunsOpen) return;
    void loadSavedRuns();
  }, [savedRunsOpen, loadSavedRuns]);

  useEffect(() => {
    if (!savedRunsOpen) return;
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') setSavedRunsOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [savedRunsOpen]);

  const openSavedRun = useCallback(
    (token: string) => {
      setTrackedQueueTokens((prev) => (prev.includes(token) ? prev : [...prev, token]));
      setQueuesPanelCollapsed(false);
      try {
        localStorage.removeItem(TAOBAO_LISTING_QUEUE_PANEL_COLLAPSED_LS_KEY);
      } catch {
        /* noop */
      }
      setSavedRunsOpen(false);
      showToast('ok', 'Đã thêm đợt vào danh sách theo dõi (xếp cũ → mới).');
    },
    [showToast],
  );

  const deleteSavedRunRow = useCallback(
    async (token: string) => {
      setSavedRunsDeleting(true);
      setSavedRunsErr(null);
      try {
        await adminProductAPI.deleteListingImportQueueSaved(token);
        removeTrackedQueueToken(token);
        setSavedRunDeleteToken(null);
        await loadSavedRuns();
        showToast('ok', 'Đã xóa đợt khỏi DB (nháp sản phẩm đã tạo không bị xóa).');
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setSavedRunsErr(msg);
        showToast('err', msg);
      } finally {
        setSavedRunsDeleting(false);
      }
    },
    [removeTrackedQueueToken, loadSavedRuns, showToast],
  );

  const deleteQueueFromDbByToken = useCallback(
    async (token: string) => {
      setPanelDbDeleting(true);
      try {
        await adminProductAPI.deleteListingImportQueueSaved(token);
        removeTrackedQueueToken(token);
        setDbDeleteConfirmToken(null);
        showToast('ok', 'Đã xóa đợt khỏi DB — nháp đã tạo vẫn giữ.');
      } catch (e) {
        showToast('err', e instanceof Error ? e.message : String(e));
      } finally {
        setPanelDbDeleting(false);
      }
    },
    [removeTrackedQueueToken, showToast],
  );

  const closeDoneDraftsModal = useCallback(() => {
    if (doneDraftsPublishing) return;
    setDoneDraftsModalToken(null);
    setDoneDraftsModalRows([]);
    setDoneDraftsModalSelected(new Set());
    setDoneDraftsModalLoading(false);
    setDoneDraftsShopPresenceKeys(new Set());
    setDoneDraftsPublishLines([]);
  }, [doneDraftsPublishing]);

  const doneDraftsModalStats = useMemo(() => {
    let formatReady = 0;
    let formatNeedsFix = 0;
    let fetchErr = 0;
    let noData = 0;
    let published = 0;
    let alreadyInShop = 0;
    for (const r of doneDraftsModalRows) {
      if (r.fetchErr) {
        fetchErr += 1;
        continue;
      }
      if (!r.draft?.product_data) {
        noData += 1;
        continue;
      }
      const pd = r.draft.product_data as Record<string, unknown>;
      if (isListingDraftPublishReady(pd)) formatReady += 1;
      else formatNeedsFix += 1;
      if (r.draft.published_product_id?.trim()) published += 1;
      else if (draftRowAlreadyInShop(r, doneDraftsShopPresenceKeys)) alreadyInShop += 1;
    }
    const selectedPublishable = [...doneDraftsModalSelected].filter((id) =>
      doneDraftsModalRows.some((row) => {
        if (!row.draft?.product_data || row.fetchErr) return false;
        if (draftRowAlreadyInShop(row, doneDraftsShopPresenceKeys)) return false;
        if (!isListingDraftPublishReady(row.draft.product_data as Record<string, unknown>)) return false;
        return row.draftId === id;
      }),
    ).length;
    return {
      total: doneDraftsModalRows.length,
      formatReady,
      formatNeedsFix,
      fetchErr,
      noData,
      published,
      alreadyInShop,
      selectedPublishable,
    };
  }, [doneDraftsModalRows, doneDraftsModalSelected, doneDraftsShopPresenceKeys]);

  const openDoneDraftsModalForToken = useCallback(
    async (token: string) => {
      const st = queueStatusByToken[token];
      const candidates = (st?.items ?? []).filter(
        (it) => it.state === 'done' && typeof it.draft_id === 'number' && it.draft_id > 0,
      );
      if (!candidates.length) {
        showToast('err', 'Chưa có dòng «done» kèm bản nháp trong đợt này.');
        return;
      }
      setDoneDraftsModalToken(token);
      setDoneDraftsModalLoading(true);
      setDoneDraftsModalRows([]);
      setDoneDraftsModalSelected(new Set());
      setDoneDraftsPublishLines([]);
      try {
        const rows = await Promise.all(
          candidates.map(async (it) => {
            const draftId = it.draft_id!;
            try {
              const draft = await adminProductAPI.getImport1688Draft(draftId);
              return {
                queueItemId: it.id,
                draftId,
                queueLabel: (it.label || '').trim(),
                queueUrl: it.url || '',
                queueSnap: it,
                draft,
              };
            } catch (e) {
              return {
                queueItemId: it.id,
                draftId,
                queueLabel: (it.label || '').trim(),
                queueUrl: it.url || '',
                queueSnap: it,
                draft: null,
                fetchErr: e instanceof Error ? e.message : String(e),
              };
            }
          }),
        );
        setDoneDraftsModalRows(rows);

        const presenceCandidates = new Set<string>();
        for (const r of rows) {
          const k = draftListingPresenceKeyFromProductData(r.draft?.product_data as Record<string, unknown>);
          if (k) presenceCandidates.add(k);
        }
        const ids = [...presenceCandidates];
        let shopPresence = new Set<string>();
        if (ids.length > 0) {
          try {
            const pres = await adminProductAPI.listingParserDbPresence(ids, {
              includeDoneDrafts: false,
              productsActiveOnly: true,
            });
            shopPresence = new Set(pres.existing_normalized ?? []);
          } catch {
            showToast(
              'err',
              'Không đối chiếu được sản phẩm đã bán trên shop — các ô chọn vẫn bật; kiểm tra mạng và thử lại.',
            );
          }
        }
        setDoneDraftsShopPresenceKeys(shopPresence);

        const ready = rows
          .filter((r) => {
            if (!r.draft?.product_data || r.fetchErr) return false;
            if (!isListingDraftPublishReady(r.draft.product_data as Record<string, unknown>)) return false;
            return !draftRowAlreadyInShop(r, shopPresence);
          })
          .map((r) => r.draftId);
        setDoneDraftsModalSelected(new Set(ready));
      } finally {
        setDoneDraftsModalLoading(false);
      }
    },
    [queueStatusByToken, showToast],
  );

  const publishSelectedListingDrafts = useCallback(async () => {
    const token = doneDraftsModalToken;
    if (!token || listingDraftPublishInFlightRef.current) return;
    const publishable = [...doneDraftsModalSelected].filter((id) =>
      doneDraftsModalRows.some(
        (r) =>
          r.draftId === id &&
          r.draft?.product_data &&
          !r.fetchErr &&
          !draftRowAlreadyInShop(r, doneDraftsShopPresenceKeys) &&
          isListingDraftPublishReady(r.draft.product_data as Record<string, unknown>),
      ),
    );
    if (!publishable.length) {
      showToast(
        'err',
        'Chọn ít nhất một nháp đạt định dạng (màu + ảnh từng màu, ảnh chi tiết > thư viện, tên/shop Trung Quốc; giày dép/quần áo: ≥3 size hoặc free size).',
      );
      return;
    }
    const rowByDraftId = new Map(doneDraftsModalRows.map((r) => [r.draftId, r]));
    const initialLines: DoneDraftPublishLine[] = publishable.map((id) => ({
      draftId: id,
      label: draftModalRowTitle(rowByDraftId.get(id)?.draft ?? null),
      status: 'queued',
    }));
    listingDraftPublishInFlightRef.current = true;
    flushSync(() => {
      setDoneDraftsPublishing(true);
      setDoneDraftsPublishLines(initialLines);
    });
    let ok = 0;
    let fail = 0;
    const errMsgs: string[] = [];
    try {
      for (const id of publishable) {
        flushSync(() => {
          setDoneDraftsPublishLines((prev) =>
            prev.map((line) => (line.draftId === id ? { ...line, status: 'running' } : line)),
          );
        });
        try {
          const res = await adminProductAPI.publishImport1688Draft(id);
          ok += 1;
          const pid = res?.product_id?.trim() ?? '';
          const extra = res?.slug?.trim() ? ` · /${res.slug}` : '';
          flushSync(() => {
            setDoneDraftsPublishLines((prev) =>
              prev.map((line) =>
                line.draftId === id
                  ? {
                      ...line,
                      status: 'ok',
                      detail: pid ? `SP đăng: ${pid}${extra}` : res?.action === 'updated' ? 'Đã cập nhật SP' : 'Đã đăng',
                    }
                  : line,
              ),
            );
          });
        } catch (e) {
          fail += 1;
          const msg = e instanceof Error ? e.message : String(e);
          errMsgs.push(`#${id}: ${msg}`);
          flushSync(() => {
            setDoneDraftsPublishLines((prev) =>
              prev.map((line) =>
                line.draftId === id ? { ...line, status: 'err', detail: msg } : line,
              ),
            );
          });
        }
      }
    } finally {
      listingDraftPublishInFlightRef.current = false;
      flushSync(() => setDoneDraftsPublishing(false));
    }
    try {
      const fresh = await adminProductAPI.getListingImportQueueStatus(token);
      setQueueStatusByToken((prev) => ({ ...prev, [token]: fresh }));
    } catch {
      /* noop */
    }
    if (ok > 0) {
      setListingParseDbPresenceTick((n) => n + 1);
    }
    if (fail === 0) {
      showToast('ok', `Đã đăng ${ok} sản phẩm lên danh mục (cùng API với Import 1688).`);
      closeDoneDraftsModal();
    } else {
      showToast(
        'err',
        `Đăng được ${ok}, lỗi ${fail}. ${errMsgs.slice(0, 3).join(' ')}${errMsgs.length > 3 ? '…' : ''}`,
      );
    }
  }, [
    doneDraftsModalToken,
    doneDraftsModalSelected,
    doneDraftsModalRows,
    doneDraftsShopPresenceKeys,
    showToast,
    closeDoneDraftsModal,
  ]);

  const doneDraftsPublishSummary = useMemo(() => {
    const lines = doneDraftsPublishLines;
    const total = lines.length;
    const finished = lines.filter((l) => l.status === 'ok' || l.status === 'err').length;
    const running = lines.find((l) => l.status === 'running');
    const pct = total ? Math.round((finished / total) * 100) : 0;
    return { total, finished, running, pct };
  }, [doneDraftsPublishLines]);

  useEffect(() => {
    if (!doneDraftsModalToken) return undefined;
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape' && !doneDraftsPublishing && !doneDraftsModalLoading) closeDoneDraftsModal();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [doneDraftsModalToken, doneDraftsPublishing, doneDraftsModalLoading, closeDoneDraftsModal]);

  const csv = useMemo(
    () => (displayRows.length ? rowsToCsv(displayRows, effectiveRate) : ''),
    [displayRows, effectiveRate],
  );

  const downloadCsv = useCallback(() => {
    if (!csv) return;
    const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `taobao_listing_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [csv]);

  const copyCsv = useCallback(async () => {
    if (!csv) return;
    try {
      await navigator.clipboard.writeText(csv);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      setError('Không copy được vào clipboard (trình duyệt chặn). Dùng «Tải CSV».');
    }
  }, [csv]);

  const downloadSelectedCsv = useCallback(() => {
    if (!selectedOnPage.length) return;
    const text = rowsToCsv(selectedOnPage, effectiveRate);
    const blob = new Blob([`\uFEFF${text}`], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `taobao_listing_selected_${selectedOnPage.length}_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('ok', `Đã tải CSV ${selectedOnPage.length} dòng đã chọn.`);
  }, [selectedOnPage, effectiveRate, showToast]);

  return (
    <>
      {savedRunsOpen ? (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/45 p-3 sm:p-6"
          role="presentation"
          onClick={() => {
            if (!savedRunsDeleting) setSavedRunsOpen(false);
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="listing-saved-runs-title"
            className="bg-white rounded-xl shadow-xl max-w-4xl w-full max-h-[min(90vh,720px)] flex flex-col border border-slate-200"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex flex-wrap items-start justify-between gap-2 px-4 py-3 border-b border-slate-200">
              <div className="min-w-0">
                <h2 id="listing-saved-runs-title" className="text-lg font-semibold text-slate-900">
                  Đợt import listing đã lưu
                </h2>
                <p className="text-sm text-slate-600 mt-0.5">
                  Mở lại bất cứ lúc nào để tiếp tục hoặc tạm dừng. «Xóa» gỡ snapshot khỏi DB — nháp sản phẩm đã tạo không bị xóa.
                </p>
              </div>
              <div className="flex gap-2 shrink-0">
                <button
                  type="button"
                  disabled={savedRunsLoading}
                  onClick={() => void loadSavedRuns()}
                  className="px-3 py-1.5 rounded-md border border-slate-300 text-sm font-medium disabled:opacity-50"
                >
                  Làm mới
                </button>
                <button
                  type="button"
                  disabled={savedRunsDeleting}
                  onClick={() => setSavedRunsOpen(false)}
                  className="px-3 py-1.5 rounded-md border border-slate-300 text-sm"
                >
                  Đóng
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-auto px-4 py-3 min-h-[120px]">
              {savedRunsLoading && !savedRunsData?.items?.length ? (
                <p className="text-sm text-slate-600">Đang tải danh sách…</p>
              ) : null}
              {savedRunsErr ? (
                <div
                  className="mb-3 rounded-lg border border-red-200 bg-red-50 text-red-800 text-sm px-3 py-2"
                  role="alert"
                >
                  {savedRunsErr}{' '}
                  <button
                    type="button"
                    className="underline font-medium"
                    onClick={() => void loadSavedRuns()}
                  >
                    Thử lại
                  </button>
                </div>
              ) : null}
              {savedRunsData && savedRunsData.items.length === 0 ? (
                <p className="text-sm text-slate-600">
                  Chưa có đợt nào trong DB — chạy «Lấy thông tin» để tạo và lưu tự động.
                </p>
              ) : null}
              {savedRunsData && savedRunsData.items.length > 0 ? (
                <div className="overflow-x-auto rounded-lg border border-slate-200">
                  <table className="min-w-full text-sm">
                    <thead className="bg-slate-50 text-slate-700">
                      <tr>
                        <th className="text-left p-2 font-medium">Token</th>
                        <th className="text-left p-2 font-medium">Cập nhật</th>
                        <th className="text-left p-2 font-medium">Trạng thái</th>
                        <th className="text-left p-2 font-medium">Tiến độ</th>
                        <th className="text-right p-2 font-medium">Thao tác</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {savedRunsData.items.map((r) => {
                        const lab = savedRunSnapshotLabel(r);
                        const upd = r.updated_at ? String(r.updated_at).slice(0, 19).replace('T', ' ') : '—';
                        return (
                          <tr key={r.queue_token}>
                            <td className="p-2 font-mono text-xs text-slate-800" title={r.queue_token}>
                              {r.queue_token.slice(0, 10)}…
                            </td>
                            <td className="p-2 text-xs text-slate-700 whitespace-nowrap">{upd}</td>
                            <td className="p-2 text-slate-800">
                              <span className="font-medium">{lab.title}</span>
                              {lab.hint ? (
                                <span className="block text-xs text-slate-500 mt-0.5">{lab.hint}</span>
                              ) : null}
                            </td>
                            <td className="p-2 text-xs tabular-nums text-slate-700 whitespace-nowrap">
                              {r.counts.done} ok · {r.counts.error} lỗi · {r.counts.pending} chờ / {r.counts.total}
                            </td>
                            <td className="p-2 text-right whitespace-nowrap space-x-2">
                              <button
                                type="button"
                                onClick={() => openSavedRun(r.queue_token)}
                                className="px-2 py-1 rounded-md bg-indigo-600 text-white text-xs font-medium hover:bg-indigo-700"
                              >
                                Mở đợt
                              </button>
                              {savedRunDeleteToken === r.queue_token ? (
                                <>
                                  <button
                                    type="button"
                                    disabled={savedRunsDeleting}
                                    onClick={() => setSavedRunDeleteToken(null)}
                                    className="px-2 py-1 rounded-md border border-slate-300 text-xs disabled:opacity-40"
                                  >
                                    Huỷ
                                  </button>
                                  <button
                                    type="button"
                                    disabled={savedRunsDeleting}
                                    onClick={() => void deleteSavedRunRow(r.queue_token)}
                                    className="px-2 py-1 rounded-md border border-red-300 text-red-800 text-xs font-medium disabled:opacity-40"
                                  >
                                    {savedRunsDeleting ? 'Đang xóa…' : 'Xác nhận xóa'}
                                  </button>
                                </>
                              ) : (
                                <button
                                  type="button"
                                  disabled={savedRunsDeleting}
                                  onClick={() => setSavedRunDeleteToken(r.queue_token)}
                                  className="px-2 py-1 rounded-md border border-red-200 text-red-800 text-xs font-medium disabled:opacity-40"
                                >
                                  Xóa
                                </button>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : null}
              {savedRunsData ? (
                <p className="text-xs text-slate-500 mt-3">
                  Tổng {savedRunsData.total} đợt trong DB — đang hiển thị {savedRunsData.items.length}.
                </p>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
      {doneDraftsModalToken ? (
        <div
          className="fixed inset-0 z-[102] flex items-center justify-center bg-black/45 p-3 sm:p-6"
          role="presentation"
          onClick={() => {
            if (!doneDraftsPublishing && !doneDraftsModalLoading) closeDoneDraftsModal();
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="listing-done-drafts-title"
            aria-busy={doneDraftsPublishing}
            className="bg-white rounded-xl shadow-xl max-w-[min(96vw,1420px)] w-full max-h-[min(92vh,840px)] flex flex-col border border-slate-200"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex flex-wrap items-start justify-between gap-2 px-4 py-3 border-b border-slate-200 shrink-0">
              <div className="min-w-0">
                <h2 id="listing-done-drafts-title" className="text-lg font-semibold text-slate-900">
                  Sản phẩm đã crawl xong trong đợt
                </h2>
                <p className="text-sm text-slate-600 mt-0.5">
                  <strong className="font-medium text-slate-800">Bảng giống Excel đăng web</strong> — sau vài cột thao tác là{' '}
                  <strong className="font-medium text-slate-800">đúng 39 cột</strong> như file Export/Import 1688 trên server; vuốt ngang để xem
                  Tên, Giá, Size/Biến thể, ảnh, mô tả, danh mục… Cuối bảng là thông tin crawl/đợt (job, link).
                  Chỉ tick được nháp <strong className="font-medium text-slate-800">đạt kiểm tra định dạng</strong>: mỗi màu có tên +
                  URL ảnh; ảnh chi tiết (<code className="text-[10px] bg-slate-100 px-1 rounded">gallery</code>) nhiều hơn ảnh thư viện (
                  <code className="text-[10px] bg-slate-100 px-1 rounded">images</code>);{' '}
                  <code className="text-[10px] bg-slate-100 px-1 rounded">chinese_name</code> và{' '}
                  <code className="text-[10px] bg-slate-100 px-1 rounded">shop_name_chinese</code> có chữ Hán; nếu là giày dép/quần áo thì ≥
                  3 size hoặc chỉ free size. Sau đó đăng qua API Import 1688.
                </p>
                <p className="text-xs font-mono text-slate-500 mt-1.5 break-all" title={doneDraftsModalToken}>
                  Đợt: {doneDraftsModalToken.slice(0, 14)}…{doneDraftsModalToken.slice(-10)}
                </p>
              </div>
              <button
                type="button"
                disabled={doneDraftsPublishing || doneDraftsModalLoading}
                onClick={closeDoneDraftsModal}
                className="px-3 py-1.5 rounded-md border border-slate-300 text-sm shrink-0 disabled:opacity-50"
              >
                Đóng
              </button>
            </div>

            <div className="flex-1 overflow-auto px-4 py-3 min-h-[160px]">
              {doneDraftsModalLoading ? (
                <p className="text-sm text-slate-600" role="status">
                  Đang tải nháp và đối chiếu sản phẩm đã đăng bán trên web…
                </p>
              ) : doneDraftsModalRows.length === 0 ? (
                <p className="text-sm text-slate-600">Không có nháp để hiển thị.</p>
              ) : (
                <>
                  <div className="mb-3 rounded-lg border border-indigo-200 bg-indigo-50/90 px-3 py-3 text-sm text-slate-800 space-y-2">
                    <p className="font-semibold text-indigo-950">Tổng quan kết quả</p>
                    <p className="text-xs text-slate-600">
                      Cột «đăng web» khớp Export Excel nháp — trượt ngang để đối chiếu file import/export. Hàng có mã{' '}
                      <code className="text-[10px] bg-white/80 px-1 rounded">A…</code>/
                      <code className="text-[10px] bg-white/80 px-1 rounded">T…</code> trùng{' '}
                      <strong className="font-medium text-slate-800">sản phẩm đang bán trên web</strong> (theo{' '}
                      <code className="text-[10px] bg-white/80 px-1 rounded">…a188…</code> trong{' '}
                      <code className="text-[10px] bg-white/80 px-1 rounded">products</code>, chỉ{' '}
                      <code className="text-[10px] bg-white/80 px-1 rounded">is_active</code>) sẽ không chọn để đăng —{' '}
                      <strong className="font-medium text-slate-800">không</strong> chặn chỉ vì có nháp crawl.
                    </p>
                    <div className="flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-slate-700">
                      <span>
                        <strong className="tabular-nums text-slate-900">{doneDraftsModalStats.total}</strong> nháp hoàn tất
                      </span>
                      <span>
                        <strong className="tabular-nums text-emerald-800">{doneDraftsModalStats.formatReady}</strong> đạt định dạng để đăng
                      </span>
                      <span>
                        <strong className="tabular-nums text-amber-900">{doneDraftsModalStats.formatNeedsFix}</strong> có nháp nhưng chưa đạt định dạng
                      </span>
                      <span>
                        <strong className="tabular-nums text-emerald-800">{doneDraftsModalStats.published}</strong> đã có mã SP đăng trước
                      </span>
                      <span>
                        <strong className="tabular-nums text-slate-700">{doneDraftsModalStats.alreadyInShop}</strong>{' '}
                        đã có trên shop đang bán (không cho chọn đăng)
                      </span>
                      <span>
                        <strong className="tabular-nums text-amber-800">{doneDraftsModalStats.noData}</strong> thiếu product_data
                      </span>
                      <span>
                        <strong className="tabular-nums text-red-800">{doneDraftsModalStats.fetchErr}</strong> lỗi tải nháp
                      </span>
                      <span>
                        Đang chọn:{' '}
                        <strong className="tabular-nums text-slate-900">{doneDraftsModalStats.selectedPublishable}</strong>
                      </span>
                    </div>
                  </div>

                  <div className="rounded-lg border border-slate-300 bg-white shadow-sm overflow-hidden">
                    <div className="overflow-auto max-h-[min(54vh,560px)]">
                      <table className="min-w-[5400px] w-full text-xs border-collapse">
                        <thead className="sticky top-0 z-10 bg-slate-200 text-slate-900 shadow-[inset_0_-1px_0_0_rgb(203_213_225)]">
                          <tr>
                            <th
                              scope="col"
                              className="w-10 border-b border-r border-slate-300 px-2 py-2 text-center font-semibold"
                            >
                              <span className="sr-only">Chọn</span>
                            </th>
                            <th
                              scope="col"
                              className="border-b border-slate-300 px-2 py-2 text-left font-semibold whitespace-nowrap"
                            >
                              Nháp
                            </th>
                            <th
                              scope="col"
                              className="border-b border-slate-300 px-2 py-2 text-left font-semibold whitespace-nowrap"
                            >
                              Trạng thái
                            </th>
                            <th
                              scope="col"
                              className="border-b border-slate-300 px-2 py-2 text-left font-semibold whitespace-nowrap min-w-[5rem]"
                            >
                              SP đăng
                            </th>
                            {IMPORT_1688_EXCEL_COLUMNS.map(([colKey, viHeader]) => (
                              <th
                                key={colKey}
                                scope="col"
                                title={viHeader}
                                className={`border-b border-slate-300 px-2 py-2 font-semibold whitespace-nowrap leading-tight text-[10px] min-w-[5.5rem] max-w-[11rem] ${
                                  colKey === 'price' ? 'text-right' : 'text-left'
                                }`}
                              >
                                {viHeader}
                              </th>
                            ))}
                            <th
                              scope="col"
                              className="border-b border-slate-300 px-2 py-2 text-left font-semibold whitespace-nowrap min-w-[10rem] border-l border-slate-300"
                            >
                              Ghi chú / tin nhắn
                            </th>
                            <th
                              scope="col"
                              className="border-b border-slate-300 px-2 py-2 text-left font-semibold whitespace-nowrap min-w-[10rem]"
                            >
                              Lỗi nháp
                            </th>
                            <th
                              scope="col"
                              className="border-b border-slate-300 px-2 py-2 text-left font-semibold whitespace-nowrap min-w-[10rem]"
                            >
                              Cảnh báo
                            </th>
                            <th
                              scope="col"
                              className="border-b border-slate-300 px-2 py-2 text-left font-semibold whitespace-nowrap min-w-[6rem]"
                            >
                              Offer ID (nguồn)
                            </th>
                            <th
                              scope="col"
                              className="border-b border-slate-300 px-2 py-2 text-left font-semibold whitespace-nowrap min-w-[8rem]"
                            >
                              Job ID
                            </th>
                            <th
                              scope="col"
                              className="border-b border-slate-300 px-2 py-2 text-left font-semibold whitespace-nowrap"
                            >
                              Nguồn crawl
                            </th>
                            <th
                              scope="col"
                              className="border-b border-slate-300 px-2 py-2 text-left font-semibold whitespace-nowrap"
                            >
                              Phase nháp
                            </th>
                            <th
                              scope="col"
                              className="border-b border-slate-300 px-2 py-2 text-left font-semibold whitespace-nowrap"
                            >
                              Cập nhật nháp
                            </th>
                            <th
                              scope="col"
                              className="border-b border-slate-300 px-2 py-2 text-left font-semibold whitespace-nowrap min-w-[6rem]"
                            >
                              Nhãn lô
                            </th>
                            <th
                              scope="col"
                              className="border-b border-slate-300 px-2 py-2 text-left font-semibold whitespace-nowrap min-w-[12rem]"
                            >
                              Link đợt (queue)
                            </th>
                            <th
                              scope="col"
                              className="border-b border-slate-300 px-2 py-2 text-left font-semibold whitespace-nowrap min-w-[12rem]"
                            >
                              Link nhập nháp
                            </th>
                          </tr>
                        </thead>
                        <tbody className="bg-white">
                          {doneDraftsModalRows.map((row, rowIdx) => {
                            const alreadyInShop = draftRowAlreadyInShop(row, doneDraftsShopPresenceKeys);
                            const pd = row.draft?.product_data as Record<string, unknown> | undefined;
                            const formatBlockers =
                              pd && !row.fetchErr ? getListingDraftPublishBlockers(pd) : [];
                            const formatOk = Boolean(pd && !row.fetchErr && formatBlockers.length === 0);
                            const canPublish = Boolean(
                              row.draft?.product_data && !row.fetchErr && !alreadyInShop && formatOk,
                            );
                            const pubId = row.draft?.published_product_id?.trim();
                            let note = '';
                            if (row.fetchErr) note = row.fetchErr;
                            else if (!row.draft?.product_data)
                              note = 'Chưa có product_data — chỉnh trên Import 1688.';
                            else if (alreadyInShop) {
                              const pk = draftListingPresenceKeyFromProductData(pd);
                              note =
                                pk != null
                                  ? `Đã có sản phẩm đang bán trên shop (mã ${pk} — trùng product_id hoặc …${pk}a188…).`
                                  : 'Đã có sản phẩm đang bán trên shop.';
                            } else if (!formatOk)
                              note = formatBlockers.length ? formatBlockers.join(' · ') : 'Chưa đạt định dạng đăng.';
                            else note = row.draft?.message || row.draft?.status || 'Sẵn sàng đăng';

                            let badgeCls = 'bg-slate-100 text-slate-800';
                            let badgeText = '—';
                            if (row.fetchErr) {
                              badgeCls = 'bg-red-100 text-red-900';
                              badgeText = 'Lỗi tải nháp';
                            } else if (!row.draft?.product_data) {
                              badgeCls = 'bg-amber-100 text-amber-950';
                              badgeText = 'Thiếu dữ liệu';
                            } else if (pubId) {
                              badgeCls = 'bg-emerald-100 text-emerald-950';
                              badgeText = 'Đã đăng';
                            } else if (alreadyInShop) {
                              badgeCls = 'bg-slate-300 text-slate-900';
                              badgeText = 'Đã bán trên shop';
                            } else if (!formatOk) {
                              badgeCls = 'bg-orange-100 text-orange-950';
                              badgeText = 'Chưa đạt định dạng';
                            } else {
                              badgeCls = 'bg-sky-100 text-sky-950';
                              badgeText = 'Sẵn sàng đăng';
                            }

                            const excelRow = excelExportRowFromProductData(pd);
                            const qUrl = row.queueUrl.trim();
                            const srcUrl = row.draft?.source_url?.trim() ?? '';
                            const draftUpdated =
                              row.draft?.updated_at != null
                                ? String(row.draft.updated_at).slice(0, 19).replace('T', ' ')
                                : '—';
                            const offerIdCell =
                              row.draft?.source_offer_id != null && String(row.draft.source_offer_id).trim()
                                ? String(row.draft.source_offer_id).trim()
                                : pd
                                  ? strPd(pd.offer_id)
                                  : '';
                            const errJoined = row.draft?.errors?.length ? row.draft.errors.join('\n') : '';
                            const warnJoined = row.draft?.warnings?.length ? row.draft.warnings.join('\n') : '';

                            return (
                              <tr
                                key={row.queueItemId}
                                className={`border-b border-slate-200 hover:bg-indigo-50/50 align-top ${
                                  rowIdx % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'
                                }`}
                              >
                                <td className="border-r border-slate-100 p-2 text-center align-middle">
                                  <input
                                    type="checkbox"
                                    className="rounded border-slate-300"
                                    checked={doneDraftsModalSelected.has(row.draftId)}
                                    disabled={!canPublish || doneDraftsPublishing}
                                    onChange={(e) => {
                                      setDoneDraftsModalSelected((prev) => {
                                        const n = new Set(prev);
                                        if (e.target.checked) n.add(row.draftId);
                                        else n.delete(row.draftId);
                                        return n;
                                      });
                                    }}
                                    aria-label={
                                      alreadyInShop
                                        ? `Nháp ${row.draftId} đã có SP đang bán trên shop — không chọn để đăng`
                                        : !formatOk
                                          ? `Nháp ${row.draftId} chưa đạt định dạng — không chọn để đăng`
                                          : `Chọn nháp ${row.draftId}`
                                    }
                                  />
                                </td>
                                <td className="p-2 font-mono tabular-nums text-slate-800 whitespace-nowrap align-top border-r border-slate-100/80">
                                  #{row.draftId}
                                </td>
                                <td className="p-2 align-top whitespace-nowrap border-r border-slate-100/80">
                                  <span
                                    className={`inline-block rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${badgeCls}`}
                                  >
                                    {badgeText}
                                  </span>
                                </td>
                                <td className="p-2 font-mono text-[11px] text-slate-700 align-top whitespace-nowrap border-r border-slate-300">
                                  {pubId || '—'}
                                </td>
                                {IMPORT_1688_EXCEL_COLUMNS.map(([colKey]) => (
                                  <td
                                    key={colKey}
                                    className={`p-2 align-top border-r border-slate-100/80 max-w-[14rem] text-slate-800 ${
                                      colKey === 'price' ? 'text-right tabular-nums whitespace-nowrap' : 'text-[11px]'
                                    }`}
                                  >
                                    {renderDoneDraftModalExcelCell(colKey, excelRow[colKey] ?? '', pd)}
                                  </td>
                                ))}
                                <td
                                  className="p-2 text-slate-600 align-top text-[11px] whitespace-nowrap min-w-[10rem] max-w-[18rem] overflow-hidden text-ellipsis border-l border-slate-300"
                                  title={note}
                                >
                                  {note}
                                </td>
                                <td
                                  className="p-2 align-top text-[11px] text-red-900 whitespace-pre-wrap max-h-24 overflow-y-auto min-w-[10rem] max-w-[16rem]"
                                  title={errJoined}
                                >
                                  {errJoined || '—'}
                                </td>
                                <td
                                  className="p-2 align-top text-[11px] text-amber-950 whitespace-pre-wrap max-h-24 overflow-y-auto min-w-[10rem] max-w-[16rem]"
                                  title={warnJoined}
                                >
                                  {warnJoined || '—'}
                                </td>
                                <td className="p-2 font-mono text-[11px] text-slate-800 whitespace-nowrap align-top">
                                  {offerIdCell || '—'}
                                </td>
                                <td
                                  className="p-2 font-mono text-[11px] text-slate-800 whitespace-nowrap align-top max-w-[14rem] overflow-hidden text-ellipsis"
                                  title={row.draft?.job_id ?? ''}
                                >
                                  {row.draft?.job_id ?? '—'}
                                </td>
                                <td className="p-2 align-top whitespace-nowrap">{row.draft?.source ?? '—'}</td>
                                <td className="p-2 align-top whitespace-nowrap font-mono text-[11px]">
                                  {row.draft?.phase ?? '—'}
                                </td>
                                <td className="p-2 align-top whitespace-nowrap font-mono text-[11px]">{draftUpdated}</td>
                                <td className="p-2 font-mono text-[11px] text-slate-700 whitespace-nowrap align-top">
                                  {row.queueLabel || '—'}
                                </td>
                                <td className="p-2 align-top font-mono text-[11px] whitespace-nowrap min-w-[12rem]">
                                  {qUrl ? (
                                    <a
                                      href={qUrl}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="text-indigo-700 underline"
                                      title={qUrl}
                                    >
                                      {qUrl}
                                    </a>
                                  ) : (
                                    '—'
                                  )}
                                </td>
                                <td className="p-2 align-top font-mono text-[11px] whitespace-nowrap min-w-[12rem]">
                                  {srcUrl ? (
                                    <a
                                      href={srcUrl}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="text-indigo-700 underline"
                                      title={srcUrl}
                                    >
                                      {srcUrl}
                                    </a>
                                  ) : (
                                    '—'
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </>
              )}
              {!doneDraftsModalLoading && doneDraftsModalRows.length > 0 ? (
                <p className="text-xs text-slate-500 mt-3">
                  Cần sửa chi tiết từng nháp trước khi đăng?{' '}
                  <Link href="/admin/products" className="text-indigo-700 underline font-medium">
                    Trang Sản phẩm → nhập link Import 1688 → Mở nháp
                  </Link>
                  .
                </p>
              ) : null}
            </div>

            {doneDraftsPublishLines.length > 0 ? (
              <div
                className="border-t border-emerald-200 bg-emerald-50/95 px-4 py-3 shrink-0 space-y-3"
                role="status"
                aria-live="polite"
                aria-relevant="additions text"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-emerald-950">
                    Tiến trình đăng lên shop
                    {doneDraftsPublishing ? (
                      <span className="font-normal text-emerald-800">
                        {' '}
                        — đã phản hồi{' '}
                        <span className="tabular-nums font-medium">
                          {doneDraftsPublishSummary.finished}/{doneDraftsPublishSummary.total}
                        </span>
                        {doneDraftsPublishSummary.running ? (
                          <span className="whitespace-nowrap">
                            {' '}
                            · đang gửi nháp{' '}
                            <span className="font-mono">#{doneDraftsPublishSummary.running.draftId}</span>
                          </span>
                        ) : doneDraftsPublishSummary.finished < doneDraftsPublishSummary.total ? (
                          <span> · chuẩn bị nháp tiếp…</span>
                        ) : null}
                      </span>
                    ) : (
                      <span className="font-normal text-emerald-800">
                        {' '}
                        — hoàn tất{' '}
                        <span className="tabular-nums font-medium">
                          {doneDraftsPublishSummary.finished}/{doneDraftsPublishSummary.total}
                        </span>
                      </span>
                    )}
                  </p>
                  <span className="text-xs tabular-nums text-emerald-900 font-medium">
                    {doneDraftsPublishSummary.pct}%
                  </span>
                </div>
                <div
                  className="h-2 rounded-full bg-emerald-200/80 overflow-hidden"
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={doneDraftsPublishSummary.pct}
                  aria-label="Phần trăm nháp đã xử lý xong"
                >
                  <div
                    className="h-full bg-emerald-600 transition-[width] duration-150 ease-out"
                    style={{ width: `${doneDraftsPublishSummary.pct}%` }}
                  />
                </div>
                <ul className="max-h-[min(28vh,220px)] overflow-auto space-y-1.5 text-xs">
                  {doneDraftsPublishLines.map((line) => {
                    const badge =
                      line.status === 'queued'
                        ? { text: 'Chờ', cls: 'bg-slate-200 text-slate-800' }
                        : line.status === 'running'
                          ? { text: 'Đang gửi', cls: 'bg-amber-200 text-amber-950' }
                          : line.status === 'ok'
                            ? { text: 'Xong', cls: 'bg-emerald-600 text-white' }
                            : { text: 'Lỗi', cls: 'bg-red-600 text-white' };
                    const detail = line.detail?.trim();
                    const detailShort =
                      detail && detail.length > 180 ? `${detail.slice(0, 180)}…` : detail;
                    return (
                      <li
                        key={line.draftId}
                        className="flex flex-wrap items-start gap-2 rounded-md border border-emerald-100 bg-white/90 px-2 py-1.5"
                      >
                        <span className={`shrink-0 rounded px-1.5 py-0.5 font-medium ${badge.cls}`}>
                          {badge.text}
                        </span>
                        <span className="font-mono text-[11px] text-slate-600 shrink-0">#{line.draftId}</span>
                        <span className="text-slate-800 min-w-[8rem] flex-1">{line.label}</span>
                        {detailShort ? (
                          <span className="text-slate-600 w-full sm:w-auto sm:max-w-[min(52vw,420px)] break-words" title={detail}>
                            {detailShort}
                          </span>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              </div>
            ) : null}

            <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 border-t border-slate-200 bg-slate-50/80 shrink-0">
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={doneDraftsModalLoading || doneDraftsPublishing || doneDraftsModalRows.length === 0}
                  onClick={() => {
                    const ids = doneDraftsModalRows
                      .filter((r) => {
                        if (!r.draft?.product_data || r.fetchErr) return false;
                        if (!isListingDraftPublishReady(r.draft.product_data as Record<string, unknown>)) return false;
                        return !draftRowAlreadyInShop(r, doneDraftsShopPresenceKeys);
                      })
                      .map((r) => r.draftId);
                    setDoneDraftsModalSelected(new Set(ids));
                  }}
                  className="px-3 py-1.5 rounded-md border border-slate-300 bg-white text-sm disabled:opacity-40"
                >
                  Chọn tất cả đạt định dạng
                </button>
                <button
                  type="button"
                  disabled={doneDraftsModalLoading || doneDraftsPublishing}
                  onClick={() => setDoneDraftsModalSelected(new Set())}
                  className="px-3 py-1.5 rounded-md border border-slate-300 bg-white text-sm disabled:opacity-40"
                >
                  Bỏ chọn
                </button>
              </div>
              <button
                type="button"
                disabled={
                  doneDraftsModalLoading ||
                  doneDraftsPublishing ||
                  doneDraftsModalStats.selectedPublishable === 0
                }
                onClick={() => void publishSelectedListingDrafts()}
                className="px-4 py-2 rounded-lg bg-emerald-700 text-white text-sm font-medium hover:bg-emerald-800 disabled:opacity-40"
              >
                {doneDraftsPublishing && doneDraftsPublishSummary.total > 0
                  ? `Đang đăng (${doneDraftsPublishSummary.finished}/${doneDraftsPublishSummary.total})…`
                  : `Đăng ${doneDraftsModalStats.selectedPublishable} sản phẩm`}
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {enqueueChoiceOpen && pendingEnqueuePayload ? (
        <div
          className="fixed inset-0 z-[101] flex items-center justify-center bg-black/45 p-3 sm:p-6"
          role="presentation"
          onClick={() => {
            if (!enqueueSubmitting) cancelListingEnqueueChoice();
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="listing-enqueue-choice-title"
            className="bg-white rounded-xl shadow-xl max-w-md w-full border border-slate-200 p-4 space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div>
              <h2 id="listing-enqueue-choice-title" className="text-lg font-semibold text-slate-900">
                Gửi link lên server
              </h2>
              <p className="text-sm text-slate-600 mt-1">
                Bạn sắp gửi{' '}
                <strong className="tabular-nums">{pendingEnqueuePayload.items.length}</strong> link (
                {importFetchTarget === 'hibox'
                  ? 'Hibox'
                  : importFetchTarget === '1688'
                    ? '1688'
                    : 'tự động Hibox/1688'}
                ). Chọn đợt đích:
              </p>
              {newestTrackedQueueToken ? (
                <p className="text-xs text-slate-600 mt-2 font-mono">
                  Đợt nhận «Thêm vào…»: {newestTrackedQueueToken.slice(0, 12)}… —{' '}
                  <span className="font-sans">
                    {listingQueueRunStatusLabel(newestTrackedQueueStatus ?? null).title}
                  </span>
                  <span className="block font-sans text-slate-500 mt-1 normal-case">
                    Đây là đợt <strong>mới nhất</strong> trong danh sách theo dõi (thứ tự <strong>cũ → mới</strong>).
                  </span>
                </p>
              ) : (
                <p className="text-xs text-amber-800 mt-2 rounded-md bg-amber-50 border border-amber-200 px-2 py-1.5">
                  Chưa có đợt đang theo dõi — chỉ có thể tạo đợt mới (hoặc «Đợt đã lưu (DB)» để thêm đợt cũ vào danh sách).
                </p>
              )}
              {appendToCurrentQueueOption.disabled && newestTrackedQueueToken && appendToCurrentQueueOption.hint ? (
                <p className="text-xs text-slate-600 mt-2">{appendToCurrentQueueOption.hint}</p>
              ) : null}
            </div>
            <div className="flex flex-col gap-2">
              <button
                type="button"
                disabled={enqueueSubmitting || appendToCurrentQueueOption.disabled}
                onClick={() => void submitListingEnqueue('append')}
                className="w-full px-4 py-2.5 rounded-lg border border-indigo-300 bg-indigo-50 text-indigo-950 text-sm font-medium text-left hover:bg-indigo-100 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <span className="block font-semibold">Thêm vào đợt đang mở</span>
                <span className="block text-xs font-normal text-indigo-900/90 mt-0.5">
                  Xếp link vào đợt <strong>mới nhất</strong> trong danh sách theo dõi (cùng token — thứ tự cũ → mới).
                </span>
              </button>
              <button
                type="button"
                disabled={enqueueSubmitting}
                onClick={() => void submitListingEnqueue('new')}
                className="w-full px-4 py-2.5 rounded-lg border border-slate-300 bg-white text-slate-900 text-sm font-medium text-left hover:bg-slate-50 disabled:opacity-40"
              >
                <span className="block font-semibold">Tạo đợt mới</span>
                <span className="block text-xs font-normal text-slate-600 mt-0.5">
                  Job worker riêng trên server — không chung hàng đợi với đợt đang mở; các đợt khác vẫn có thể chạy song
                  song.
                </span>
              </button>
            </div>
            <div className="flex justify-between items-center pt-2 border-t border-slate-100">
              <button
                type="button"
                disabled={enqueueSubmitting}
                onClick={cancelListingEnqueueChoice}
                className="px-3 py-1.5 rounded-md border border-slate-300 text-sm text-slate-700 disabled:opacity-40"
              >
                Huỷ
              </button>
              {enqueueSubmitting ? <span className="text-xs text-slate-600">Đang gửi…</span> : null}
            </div>
          </div>
        </div>
      ) : null}
      <div className="max-w-6xl mx-auto px-4 py-6 space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">HTML listing → một dòng một sản phẩm</h1>
        <p className="text-sm text-slate-600 mt-1 max-w-3xl">
          Dán HTML (hoặc outerHTML của vùng danh sách) từ trang Taobao/Tmall / 1688 /{' '}
          <strong>lưới sản phẩm Hibox</strong> (link{' '}
          <code className="text-xs bg-slate-100 px-1 rounded">/v/abb-…</code>{' '}
          hoặc <code className="text-xs bg-slate-100 px-1 rounded">/v/631214062812</code>), hoặc{' '}
          <strong>bảng text xuất từ seller 1688</strong> (cột{' '}
          <span lang="zh-Hans">商品信息</span>, dòng <code className="text-xs bg-slate-100 px-1 rounded">ID: …</code>, hàng tab giá){' '}
          — công cụ khớp{' '}
          <code className="text-xs bg-slate-100 px-1 rounded">cardContainer–…</code>,{' '}
          <code className="text-xs bg-slate-100 px-1 rounded">doubleCardWrapperAdapt</code>,{' '}
          <code className="text-xs bg-slate-100 px-1 rounded">mainImg</code> hoặc ảnh alicdn trong cùng
          một khối có giá/tiêu đề.{' '}
          Mỗi card → một hàng: ID sản phẩm, link SP, ảnh chính, tiêu đề, tên shop, tag, giá nhân dân tệ, cột quy đổi{' '}
          ~VNĐ ≈ làm tròn(CN¥ × hệ số lưới × tỷ giá ô «Tỷ giá»; VNĐ / 1 CN¥). Ô <strong>Shop mặc định</strong> chỉ cho lô hiện tại — làm trống mỗi lần «Parse → bảng» (mỗi lô shop có thể khác).
          Ký hiệu <strong>₮</strong> là <strong>tugrik Mông Cổ (MNT)</strong>. Giá lưới Hibox là MNT (vd.{' '}
          <code className="text-xs bg-slate-100 px-1 rounded">89.000 ₮</code> → nối chữ số thành 89000); quy sang CN¥ bằng ô{' '}
          <strong>₮ / 1 CN¥</strong> trên toolbar, rồi mới nhân hệ số lưới và tỷ giá VNĐ.
          CSV thêm các cột price_cny_approx, cny_exchange_multiplier, vnd_per_cny_used, approx_vnd.
          {' '}
          <span className="text-slate-700">
            Mặc định chỉ hiện các dòng đủ cột trong bảng (với Hibox / bảng text 1688 không bắt buộc shop/tag/ảnh); bỏ chọn để xem cả dòng thiếu dữ liệu.
            Sau đó có thể chỉ giữ các ID chưa có trên shop và chưa có nháp crawl xong (bỏ chọn để xem cả lô).
          </span>{' '}
          <span className="text-slate-700">
            Chọn một hoặc nhiều dòng rồi chọn <strong>Trang lấy dữ liệu</strong> (Hibox / 1688 / tự động) và bấm «Lấy thông tin»
            — cửa sổ sẽ hỏi <strong>thêm vào đợt đang mở</strong> hay <strong>tạo đợt / job mới</strong>. Server xử lý link{' '}
            <strong>lần lượt</strong> (Playwright). Có tạm dừng / tiếp tục / dừng hẳn, tải CSV tiến trình và thanh % bên dưới.
            Hoặc «Export đã chọn» để tải CSV bảng parse.
          </span>
        </p>
      </div>

      <textarea
        className="w-full min-h-[200px] rounded-lg border border-slate-300 px-3 py-2 text-sm font-mono"
        placeholder="Dán HTML hoặc bảng text 1688 (商品信息 / ID: … / hàng tab giá) — Taobao / 1688 / lưới Hibox…"
        value={raw}
        onChange={(e) => setRaw(e.target.value)}
        aria-label="HTML listing Taobao để parse"
      />

      <div className="flex flex-wrap gap-2 items-center">
        <button
          type="button"
          onClick={parse}
          className="px-4 py-2 rounded-lg bg-slate-800 text-white text-sm font-medium hover:bg-slate-900"
        >
          Parse → bảng
        </button>
        <button
          type="button"
          disabled={!displayRows.length}
          onClick={downloadCsv}
          className="px-4 py-2 rounded-lg border border-slate-300 text-sm font-medium disabled:opacity-50"
        >
          Tải CSV (UTF‑8 BOM)
        </button>
        <button
          type="button"
          disabled={!displayRows.length}
          onClick={() => void copyCsv()}
          className="px-4 py-2 rounded-lg border border-slate-300 text-sm font-medium disabled:opacity-50"
        >
          {copied ? 'Đã copy' : 'Copy CSV'}
        </button>
        <button
          type="button"
          disabled={selectedOnPage.length === 0}
          onClick={downloadSelectedCsv}
          title="Chỉ xuất các dòng đang tick trong bảng (cùng cột và tỷ giá như «Tải CSV»)."
          className="px-4 py-2 rounded-lg border border-slate-300 text-sm font-medium disabled:opacity-50"
        >
          Export đã chọn
          {selectedOnPage.length > 0 ? ` (${selectedOnPage.length})` : ''}
        </button>
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor="listing-import-fetch-target" className="sr-only">
            Trang lấy dữ liệu (tên miền import)
          </label>
          <span className="text-xs text-slate-600 whitespace-nowrap hidden sm:inline">Trang lấy dữ liệu</span>
          <select
            id="listing-import-fetch-target"
            value={importFetchTarget}
            onChange={(e) => persistImportFetchTarget(e.target.value as ListingImportFetchTarget)}
            disabled={enqueueSubmitting}
            className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-900 shadow-sm disabled:opacity-60 max-w-[min(100%,15rem)]"
            aria-label="Chọn trang để lấy thông tin: Hibox không cần cookie 1688, hoặc 1688 trực tiếp"
            title="Tự động: ưu tiên link Hibox nếu ghép được, không thì link chi tiết 1688 (khi có offer id)."
          >
            <option value="auto">Tự động (Hibox hoặc 1688)</option>
            <option value="hibox">Hibox (hibox.mn)</option>
            <option value="1688">1688 (detail.1688.com)</option>
          </select>
        </div>
        <button
          type="button"
          disabled={!displayRows.length || enqueueSubmitting || selectedOnPage.length === 0}
          onClick={() => void openListingEnqueueChoice()}
          title="Gửi các dòng đang tick lên hàng đợi server. Sau khi gửi thành công, các dòng đó được bỏ chọn — tránh bấm trùng; chọn lại nếu cần gửi thêm."
          aria-busy={enqueueSubmitting}
          className="px-4 py-2 rounded-lg bg-indigo-700 text-white text-sm font-medium hover:bg-indigo-800 disabled:opacity-50 disabled:pointer-events-none"
        >
          {enqueueSubmitting ? 'Đang gửi lên server…' : `Lấy thông tin${selectedOnPage.length ? ` (${selectedOnPage.length})` : ''}`}
        </button>
        <button
          type="button"
          onClick={() => {
            setSavedRunDeleteToken(null);
            setSavedRunsOpen(true);
          }}
          className="px-4 py-2 rounded-lg border border-indigo-400 bg-white text-indigo-900 text-sm font-medium hover:bg-indigo-50"
          title="Xem các đợt đã lưu trên server — mở lại để Tiếp tục / Tạm dừng; xóa snapshot khỏi DB (không xóa nháp)."
        >
          Đợt đã lưu (DB)
        </button>
        <span className="text-sm text-slate-500">
          {rows.length > 0 ? (
            <>
              Hiển thị{' '}
              <span className="font-medium tabular-nums text-slate-700">{displayRows.length}</span>
              {rows.length !== displayRows.length ? (
                <>
                  {' '}
                  / <span className="tabular-nums">{rows.length}</span> đã parse
                </>
              ) : null}
            </>
          ) : null}
        </span>
        <label className="flex items-center gap-2 text-sm shrink-0 cursor-pointer">
          <input
            type="checkbox"
            checked={onlyMissingInDb}
            onChange={(e) => {
              const on = e.target.checked;
              setOnlyMissingInDb(on);
              if (!on) setDbLookupError(null);
            }}
            disabled={rows.length === 0}
            className="rounded border-slate-300"
            title="Bật: chỉ hiện ID chưa có trên shop và chưa có nháp crawl xong; sau đăng SP hoặc khi queue xong thêm dòng, bảng tự đối chiếu lại; quay lại tab cũng làm mới. Tắt: hiện toàn bộ lô sau parse."
            aria-label="Chỉ hiện sản phẩm chưa có trên shop và chưa có nháp import crawl xong; bỏ chọn để xem cả lô"
          />
          <span className="text-sm text-slate-700 whitespace-nowrap">Chưa có trên shop — chưa nháp xong</span>
          {onlyMissingInDb && dbLookupPending ? (
            <span className="text-xs text-slate-500">Đang đối chiếu…</span>
          ) : null}
        </label>
        <label className="flex items-center gap-2 text-sm shrink-0 cursor-pointer">
          <input
            type="checkbox"
            checked={onlyCompleteListingRows}
            onChange={(e) => setOnlyCompleteListingRows(e.target.checked)}
            disabled={rows.length === 0}
            className="rounded border-slate-300"
            title="Ẩn các dòng thiếu ID, link, tiêu đề, giá Tệ hoặc không tính được ~VNĐ. Với Hibox không yêu cầu shop/tag; với bảng text 1688 không yêu cầu shop/tag/ảnh."
            aria-label="Chỉ hiện dòng có đủ dữ liệu các cột trong bảng"
          />
          <span className="text-sm text-slate-700 whitespace-nowrap">Chỉ dòng đủ dữ liệu</span>
        </label>
        <label className="flex items-center gap-2 text-sm shrink-0">
          <span className="text-slate-600 whitespace-nowrap hidden sm:inline">Tỷ giá</span>
          <input
            type="text"
            inputMode="decimal"
            value={rateInput}
            onChange={(e) => persistRateInput(e.target.value)}
            placeholder="VNĐ / 1 CN¥"
            autoComplete="off"
            aria-label="Tỷ giá VNĐ trên một nhân dân tệ CN¥ để ước lượng cột VNĐ và CSV"
            className="w-[6.75rem] tabular-nums rounded-md border border-slate-300 px-2 py-1.5 text-sm disabled:bg-slate-100 disabled:text-slate-400"
          />
        </label>
        <label className="flex items-center gap-2 text-sm shrink-0" title="Chỉ dùng cho dòng parse từ lưới Hibox (giá hiển thị là ₮ MNT). CN¥ ≈ số MNT (nối chữ số) ÷ ô này.">
          <span className="text-slate-600 whitespace-nowrap hidden sm:inline">₮ / 1 CN¥</span>
          <input
            type="text"
            inputMode="decimal"
            value={mntPerCnyInput}
            onChange={(e) => persistMntPerCnyInput(e.target.value)}
            placeholder="MNT / 1¥"
            autoComplete="off"
            aria-label="Tỷ giá tugrik Mông Cổ trên một nhân dân tệ — quy đổi giá Hibox sang CN¥ trước khi tính ~VNĐ"
            className="w-[5.5rem] tabular-nums rounded-md border border-slate-300 px-2 py-1.5 text-sm"
          />
        </label>
        <label
          className="flex items-center gap-2 text-sm shrink-0 min-w-[12rem] sm:min-w-[18rem] max-w-[22rem]"
          title="Khi parse không có tên shop (vd. Hibox, bảng text 1688), điền tên shop Trung Quốc để hiển thị và CSV dùng giá trị này; dòng đã có shop trong HTML giữ nguyên. Mỗi lần «Parse → bảng» ô được làm trống (shop khác mỗi lô)."
        >
          <span className="text-slate-600 whitespace-nowrap hidden sm:inline">Shop mặc định</span>
          <input
            type="text"
            value={fallbackShopInput}
            onChange={(e) => setFallbackShopInput(e.target.value)}
            placeholder="Tên shop khi thiếu…"
            autoComplete="organization"
            aria-label="Tên shop Trung Quốc dự phòng khi dữ liệu parse không có shop"
            className="flex-1 min-w-0 rounded-md border border-slate-300 px-2 py-1.5 text-sm"
          />
        </label>
        <label className="flex items-center gap-2 text-sm shrink-0 min-w-[12rem] sm:min-w-[16rem] max-w-[20rem]">
          <span className="sr-only">Lọc theo tên shop</span>
          <span className="text-slate-600 whitespace-nowrap hidden sm:inline">Lọc shop</span>
          <input
            type="search"
            value={shopFilter}
            onChange={(e) => setShopFilter(e.target.value)}
            placeholder="Tên shop…"
            autoComplete="off"
            aria-label="Lọc danh sách theo tên shop"
            disabled={rows.length === 0}
            className="flex-1 min-w-0 rounded-md border border-slate-300 px-2 py-1.5 text-sm disabled:bg-slate-100 disabled:text-slate-400"
          />
        </label>
        <label className="flex items-center gap-2 text-sm shrink-0 min-w-[12rem] sm:min-w-[16rem] max-w-[20rem]">
          <span className="sr-only">Lọc theo tiêu đề sản phẩm</span>
          <span className="text-slate-600 whitespace-nowrap hidden sm:inline">Lọc tiêu đề</span>
          <input
            type="search"
            value={titleFilter}
            onChange={(e) => setTitleFilter(e.target.value)}
            placeholder="Chữ trong tiêu đề… (không cần liền)"
            autoComplete="off"
            aria-label="Lọc tiêu đề: ký tự đúng thứ tự, không cần liên tục; nhiều cụm cách nhau bằng khoảng trắng"
            disabled={rows.length === 0}
            className="flex-1 min-w-0 rounded-md border border-slate-300 px-2 py-1.5 text-sm disabled:bg-slate-100 disabled:text-slate-400"
          />
        </label>
        <div
          className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm shrink-0"
          title="Lọc theo cột ~VNĐ (CN¥ × hệ số × tỷ giá ô «Tỷ giá»). Dòng không đọc được giá Tệ bị loại khi bật khoảng."
        >
          <span className="text-slate-600 whitespace-nowrap hidden sm:inline">Giá ~VNĐ</span>
          <label className="flex items-center gap-1.5">
            <span className="sr-only">Giá VNĐ ước lượng tối thiểu</span>
            <span className="text-slate-500 text-xs whitespace-nowrap sm:hidden">Từ</span>
            <input
              type="text"
              inputMode="numeric"
              value={priceVndMinInput}
              onChange={(e) => setPriceVndMinInput(e.target.value)}
              placeholder="Tối thiểu"
              autoComplete="off"
              disabled={rows.length === 0}
              aria-label="Lọc giá VNĐ ước lượng từ (để trống = không giới hạn dưới)"
              className="w-[6.5rem] tabular-nums rounded-md border border-slate-300 px-2 py-1.5 text-sm disabled:bg-slate-100 disabled:text-slate-400"
            />
          </label>
          <span className="text-slate-400 text-xs" aria-hidden>
            —
          </span>
          <label className="flex items-center gap-1.5">
            <span className="sr-only">Giá VNĐ ước lượng tối đa</span>
            <span className="text-slate-500 text-xs whitespace-nowrap sm:hidden">Đến</span>
            <input
              type="text"
              inputMode="numeric"
              value={priceVndMaxInput}
              onChange={(e) => setPriceVndMaxInput(e.target.value)}
              placeholder="Tối đa"
              autoComplete="off"
              disabled={rows.length === 0}
              aria-label="Lọc giá VNĐ ước lượng đến (để trống = không giới hạn trên)"
              className="w-[6.5rem] tabular-nums rounded-md border border-slate-300 px-2 py-1.5 text-sm disabled:bg-slate-100 disabled:text-slate-400"
            />
          </label>
        </div>
      </div>

      {toast && (
        <div
          role="status"
          className={`rounded-lg border px-4 py-3 text-sm ${
            toast.type === 'ok'
              ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
              : 'border-red-200 bg-red-50 text-red-800'
          }`}
        >
          {toast.msg}
        </div>
      )}

      {trackedQueueTokens.length === 0 ? (
        <div
          className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700 flex flex-wrap items-center justify-between gap-2"
          role="status"
        >
          <span className="min-w-0">
            Chưa theo dõi đợt import nào trên trình duyệt — «Bỏ theo dõi» / «Ngắt theo dõi tất cả» chỉ ẩn ở đây,{' '}
            <strong className="font-medium text-slate-900">không</strong> dừng worker trên server. Để xem lại tiến độ:{' '}
            <strong className="font-medium text-slate-900">Đợt đã lưu (DB)</strong> → <strong className="font-medium text-slate-900">Mở đợt</strong>.
          </span>
          <button
            type="button"
            onClick={() => {
              setSavedRunDeleteToken(null);
              setSavedRunsOpen(true);
            }}
            className="shrink-0 px-3 py-1.5 rounded-md bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700"
          >
            Mở danh sách đợt
          </button>
        </div>
      ) : null}

      {trackedQueueTokens.length > 0 && queuesPanelCollapsed ? (
        <div
          className="rounded-lg border border-indigo-200 bg-indigo-50/90 px-3 py-2 flex flex-wrap items-center justify-between gap-2 text-sm text-indigo-950"
          role="region"
          aria-label="Hàng đợi import đang thu gọn"
        >
          <div className="min-w-0">
            <span className="font-medium text-slate-900">
              Đang theo dõi{' '}
              <span className="tabular-nums">{trackedQueueTokens.length}</span> đợt import
            </span>
            <span className="mx-1.5 text-slate-500">·</span>
            <span className="text-slate-700">Thứ tự cũ → mới trong panel</span>
          </div>
          <div className="flex flex-wrap gap-2 shrink-0">
            <button
              type="button"
              onClick={expandQueuesPanel}
              className="px-3 py-1.5 rounded-md bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700"
            >
              Hiện panel
            </button>
            <button
              type="button"
              onClick={forgetAllTrackedQueues}
              className="px-3 py-1.5 rounded-md border border-slate-300 bg-white text-slate-700 text-sm"
              title="Gỡ mọi token khỏi trình duyệt — không dừng server. Xem lại: nút «Đợt đã lưu (DB)» → «Mở đợt», hoặc gửi link mới."
            >
              Ngắt theo dõi tất cả
            </button>
          </div>
        </div>
      ) : null}

      {trackedQueueTokens.length > 0 && !queuesPanelCollapsed ? (
        <section
          className="rounded-lg border border-indigo-200 bg-indigo-50/80 text-indigo-950 px-4 py-3 space-y-3"
          aria-label="Danh sách hàng đợi import trên server"
        >
          <div className="flex flex-wrap gap-2 items-start justify-between">
            <div>
              <div className="font-medium text-slate-900">
                Đợt đang theo dõi ({displayQueueTokens.length})
              </div>
              <p className="text-sm text-slate-700 mt-1 max-w-2xl">
                Xếp <strong>cũ → mới</strong> (theo thời điểm tạo trên server). Mỗi đợt có worker riêng — có thể chạy
                song song. «Bỏ theo dõi» / «Ngắt theo dõi tất cả» chỉ ẩn trên trình duyệt — để xem lại, mở{' '}
                <strong className="font-semibold text-slate-800">Đợt đã lưu (DB)</strong> rồi bấm{' '}
                <strong className="font-semibold text-slate-800">Mở đợt</strong>.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={collapseQueuesPanel}
                className="px-3 py-1.5 rounded-md border border-slate-300 bg-white text-slate-700 text-sm"
                title="Thu gọn thanh — không dừng server."
              >
                Ẩn panel
              </button>
              <button
                type="button"
                onClick={forgetAllTrackedQueues}
                className="px-3 py-1.5 rounded-md border border-slate-300 bg-white text-slate-700 text-sm"
                title="Gỡ mọi token khỏi trình duyệt — không dừng server. Xem lại: «Đợt đã lưu (DB)» → «Mở đợt», hoặc «Lấy thông tin»."
              >
                Ngắt theo dõi tất cả
              </button>
            </div>
          </div>

          <div className="space-y-3">
            {displayQueueTokens.map((token, idx) => {
              const st = queueStatusByToken[token];
              const pollErr = queuesPollErrorByToken[token];
              const pct = progressPctForQueue(st);
              const curLab = currentItemLabelForQueue(st);
              const runLbl = listingQueueRunStatusLabel(st ?? null);
              const donePlusErr = (st?.counts?.done ?? 0) + (st?.counts?.error ?? 0);
              const doneWithDraftCount = (st?.items ?? []).filter(
                (it) => it.state === 'done' && typeof it.draft_id === 'number' && it.draft_id > 0,
              ).length;
              return (
                <article
                  key={token}
                  className="rounded-lg border border-indigo-200/80 bg-white/90 px-3 py-3 space-y-2 shadow-sm"
                  aria-label={`Đợt import ${idx + 1}`}
                >
                  <div className="flex flex-wrap gap-2 items-start justify-between">
                    <div className="min-w-0">
                      <div className="text-xs text-slate-500 mb-0.5">
                        #{idx + 1} trong danh sách (cũ → mới)
                      </div>
                      <div className="font-mono text-xs text-slate-800 break-all" title={token}>
                        {token.slice(0, 14)}…{token.slice(-6)}
                      </div>
                      <div className="font-medium text-slate-900 mt-1">
                        {runLbl.title}
                        {st?.worker_alive ? (
                          <span className="ml-2 text-xs font-normal text-indigo-700">(worker chạy)</span>
                        ) : null}
                      </div>
                      {runLbl.hint ? (
                        <p className="text-sm text-slate-700 mt-1 max-w-2xl">{runLbl.hint}</p>
                      ) : null}
                      {curLab ? (
                        <p className="text-sm text-slate-800 mt-1">
                          Đang xử lý: <span className="font-mono text-xs">{curLab}</span>
                        </p>
                      ) : null}
                    </div>
                    <div className="flex flex-wrap gap-2 shrink-0 justify-end">
                      <button
                        type="button"
                        onClick={() => removeTrackedQueueToken(token)}
                        className="px-2.5 py-1.5 rounded-md border border-slate-300 bg-white text-slate-700 text-xs"
                        title="Chỉ gỡ khỏi danh sách trình duyệt — không dừng worker. Xem lại: «Đợt đã lưu (DB)» → «Mở đợt»."
                      >
                        Bỏ theo dõi
                      </button>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => void pauseListingQueue(token)}
                      disabled={!st?.can_pause}
                      className="px-3 py-1.5 rounded-md border border-indigo-300 bg-white text-sm font-medium disabled:opacity-40"
                    >
                      Tạm dừng
                    </button>
                    <button
                      type="button"
                      onClick={() => void resumeListingQueue(token)}
                      disabled={!st?.can_resume}
                      className="px-3 py-1.5 rounded-md border border-indigo-300 bg-white text-sm font-medium disabled:opacity-40"
                    >
                      Tiếp tục
                    </button>
                    <button
                      type="button"
                      onClick={() => void stopListingQueue(token)}
                      disabled={!st?.can_stop}
                      className="px-3 py-1.5 rounded-md border border-red-300 bg-white text-red-800 text-sm font-medium disabled:opacity-40"
                    >
                      Dừng hẳn
                    </button>
                    <button
                      type="button"
                      onClick={() => void downloadListingQueueProductsExcel(token)}
                      disabled={donePlusErr === 0}
                      className="px-3 py-1.5 rounded-md border border-indigo-600 bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-40"
                      title="File .xlsx cùng mẫu «export bulk draft»: chỉ các draft có product_data (thường là dòng crawl ok)."
                    >
                      Tải Excel nhập web
                    </button>
                    <button
                      type="button"
                      onClick={() => void downloadListingQueueCsv(token)}
                      disabled={donePlusErr === 0}
                      className="px-3 py-1.5 rounded-md border border-indigo-300 bg-white text-sm font-medium disabled:opacity-40"
                      title="CSV theo dõi kỹ thuật: label, URL, draft_id, job_id… — không phải file nhập sản phẩm."
                    >
                      CSV meta (draft/job)
                    </button>
                    <button
                      type="button"
                      onClick={() => void openDoneDraftsModalForToken(token)}
                      disabled={doneWithDraftCount === 0 || doneDraftsModalLoading}
                      className="px-3 py-1.5 rounded-md border border-emerald-600 bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700 disabled:opacity-40"
                      title="Mở danh sách nháp đã crawl xong — chọn và đăng lên cửa hàng (cùng luồng Import 1688)."
                    >
                      {doneDraftsModalLoading && doneDraftsModalToken === token
                        ? 'Đang tải nháp…'
                        : 'Chọn để đăng web…'}
                    </button>
                  </div>

                  {dbDeleteConfirmToken === token ? (
                    <div
                      className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900 flex flex-wrap items-center gap-2 justify-between"
                      role="region"
                      aria-label="Xác nhận xóa đợt khỏi cơ sở dữ liệu"
                    >
                      <span className="min-w-[12rem] max-w-xl">
                        Xóa snapshot đợt khỏi DB? Tiến trình lưu trên server sẽ mất; nháp sản phẩm đã tạo{' '}
                        <strong>không</strong> bị xóa.
                      </span>
                      <span className="flex flex-wrap gap-2 shrink-0">
                        <button
                          type="button"
                          onClick={() => setDbDeleteConfirmToken(null)}
                          disabled={panelDbDeleting}
                          className="px-3 py-1.5 rounded-md border border-slate-300 bg-white text-slate-800 text-sm disabled:opacity-40"
                        >
                          Huỷ
                        </button>
                        <button
                          type="button"
                          onClick={() => void deleteQueueFromDbByToken(token)}
                          disabled={panelDbDeleting}
                          className="px-3 py-1.5 rounded-md border border-red-400 bg-white text-red-900 text-sm font-medium disabled:opacity-40"
                        >
                          {panelDbDeleting ? 'Đang xóa…' : 'Xác nhận xóa khỏi DB'}
                        </button>
                      </span>
                    </div>
                  ) : (
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={() => setDbDeleteConfirmToken(token)}
                        className="text-sm text-red-900 hover:underline font-medium"
                        title="Gỡ snapshot đợt khỏi database — không xóa draft."
                      >
                        Xóa đợt khỏi DB…
                      </button>
                    </div>
                  )}

                  {st?.counts ? (
                    <div>
                      <div className="flex justify-between text-xs text-slate-600 mb-1">
                        <span>
                          Tiến độ: {st.counts.done} ok · {st.counts.error} lỗi · {st.counts.pending} chờ ·{' '}
                          {st.counts.running} đang chạy / {st.counts.total} tổng
                        </span>
                        <span className="tabular-nums">{pct}%</span>
                      </div>
                      <div className="h-2 rounded-full bg-indigo-200 overflow-hidden">
                        <div
                          className="h-full bg-indigo-600 transition-[width] duration-300"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  ) : null}

                  {pollErr ? (
                    <div
                      className="text-sm text-red-800 border border-red-200 bg-red-50 rounded-md px-3 py-2"
                      role="alert"
                    >
                      {pollErr}
                    </div>
                  ) : null}

                  {st?.items && st.items.length > 0 ? (
                    <ul className="max-h-36 overflow-y-auto text-xs font-mono space-y-1 border-t border-indigo-200/60 pt-2 text-slate-800">
                      {st.items.map((it) => (
                        <li key={it.id}>
                          <span
                            className={
                              it.state === 'done'
                                ? 'text-emerald-800'
                                : it.state === 'error'
                                  ? 'text-red-800'
                                  : it.state === 'running'
                                    ? 'text-indigo-800 font-semibold'
                                    : 'text-slate-600'
                            }
                          >
                            [{it.state}]
                          </span>{' '}
                          {it.label || '—'} —{' '}
                          {it.message || (it.draft_id ? `draft #${it.draft_id}` : it.url?.slice(0, 56))}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </article>
              );
            })}
          </div>
        </section>
      ) : null}

      {error && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 text-amber-900 text-sm px-4 py-3">
          {error}
        </div>
      )}

      {dbLookupError && (
        <div className="rounded-lg border border-red-200 bg-red-50 text-red-800 text-sm px-4 py-3">
          {dbLookupError}
        </div>
      )}
      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-slate-200">
          {emptyFilterBannerChunks.length > 0 &&
            rows.length > 0 &&
            preDbFilteredRows.length === 0 && (
              <div className="px-4 py-3 text-sm text-slate-600 border-b border-slate-100 bg-slate-50">
                Không có dòng nào khớp{' '}
                {emptyFilterBannerChunks.map((c, i) => (
                  <Fragment key={i}>
                    {i > 0 ? ' và ' : ''}
                    {c}
                  </Fragment>
                ))}
                .
              </div>
            )}
          {preDbFilteredRows.length > 0 && dbPresenceReady && displayRows.length === 0 && (
            <div className="px-4 py-3 text-sm text-slate-600 border-b border-slate-100 bg-slate-50">
              Mọi sản phẩm trong lô đang lọc đều đã có trong DB (theo ID SP).
            </div>
          )}
          {!shopFilterTrimmed &&
            !titleFilterTrimmed &&
            !priceVndBounds.active &&
            !onlyCompleteListingRows &&
            dbPresenceReady &&
            displayRows.length === 0 &&
            rows.length > 0 && (
              <div className="px-4 py-3 text-sm text-slate-600 border-b border-slate-100 bg-slate-50">
                Mọi ID trong lô parse đều đã có trong DB.
              </div>
            )}
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-600">
              <tr>
                <th className="p-2 w-10">
                  <input
                    ref={headerSelectAllRef}
                    type="checkbox"
                    checked={allVisibleSelected}
                    onChange={toggleSelectAllVisible}
                    disabled={!displayRows.length || enqueueSubmitting}
                    className="rounded border-slate-300"
                    aria-label="Chọn tất cả dòng đang hiển thị"
                    title="Chọn / bỏ chọn tất cả dòng trong bảng (sau lọc)"
                  />
                </th>
                <th className="p-2 w-12">#</th>
                <th className="p-2">ID SP</th>
                <th className="p-2 max-w-[220px]">Link SP</th>
                <th className="p-2 min-w-[120px]" title="shop_name_chinese">
                  Shop Trung Quốc
                </th>
                <th className="p-2 min-w-[120px]" title="Taobao/1688 HTML & bảng text 1688: CN¥ từ cột giá. Hibox: CN¥ sau khi quy từ ₮ (MNT) bằng ô ₮/CN¥.">
                  Giá Tệ
                </th>
                <th className="p-2 min-w-[200px]" title="chinese_name">
                  Tên tiếng trung
                </th>
                <th className="p-2 w-20">Ảnh</th>
                <th className="p-2 min-w-[120px]">Tag</th>
                <th className="p-2 min-w-[120px]" title="CN¥ × hệ số lưới × tỷ giá (VNĐ/CN¥), làm tròn lên bội 10.000 ₫">
                  ~VNĐ
                </th>
              </tr>
            </thead>
            <tbody>
              {displayRows.map((r, i) => {
                const rowKey = stableListingRowKey(r);
                const shopFilledByFallback =
                  !!fallbackShopTrimmed && parsedRowKeyHadEmptyShop.get(rowKey) === true;
                return (
                  <tr
                    key={rowKey}
                    className="border-t border-slate-100 align-top"
                  >
                    <td className="p-2">
                      <input
                        type="checkbox"
                        checked={selectedRowKeys.has(rowKey)}
                        onChange={() => toggleRowSelected(rowKey)}
                        disabled={enqueueSubmitting}
                        className="rounded border-slate-300"
                        aria-label={`Chọn sản phẩm ${r.item_id || i + 1}`}
                      />
                    </td>
                    <td className="p-2 text-slate-500">{i + 1}</td>
                    <td className="p-2 font-mono text-xs text-slate-800 whitespace-nowrap">{r.item_id || '—'}</td>
                    <td className="p-2 text-xs break-all max-w-[220px]">
                      {r.item_url ? (
                        <a
                          href={r.item_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:underline line-clamp-2"
                        >
                          {r.item_url}
                        </a>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                    <td
                      className="p-2 text-slate-700 max-w-[180px]"
                      title={
                        shopFilledByFallback
                          ? 'Tên shop (shop_name_chinese) lấy từ ô «Shop mặc định» vì parse không có shop.'
                          : undefined
                      }
                    >
                      {(r.shop_name_chinese || '').trim() || r.shop_name || '—'}
                    </td>
                    <td
                      className="p-2 font-mono text-xs text-slate-700 break-all max-w-[200px]"
                      title={
                        r.parsed_source === 'hibox_grid'
                          ? `₮ MNT ${r.price_hibox_mnt_integer ?? '—'} (${r.price_raw || '—'}) ÷ ${effectiveMntPerCny} → CN¥`
                          : r.parsed_source === '1688_text_table'
                            ? `Giá cột từ bảng text 1688: ${r.price_raw || '—'} → CN¥`
                            : undefined
                      }
                    >
                      {r.parsed_source === 'hibox_grid' && r.price_cny_approx != null ? (
                        <span className="inline-flex flex-col gap-0.5">
                          <span className="tabular-nums text-slate-900">{formatApproxCnyCell(r.price_cny_approx)} ¥</span>
                          <span className="text-[10px] text-slate-500 font-normal whitespace-nowrap">
                            hiển thị {r.price_raw || '—'}
                          </span>
                        </span>
                      ) : r.parsed_source === '1688_text_table' && r.price_cny_approx != null ? (
                        <span className="tabular-nums text-slate-900">{formatApproxCnyCell(r.price_cny_approx)} ¥</span>
                      ) : (
                        r.price_raw || '—'
                      )}
                    </td>
                    <td className="p-2 text-slate-800 max-w-xl">
                      {(r.chinese_name || '').trim() || r.title || '—'}
                    </td>
                    <td className="p-2">
                      {r.main_image_url ? (
                        <img
                          src={r.main_image_url}
                          alt=""
                          className="w-14 h-14 object-cover rounded border border-slate-200"
                        />
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                    <td className="p-2 text-slate-600 text-xs">{r.tags || '—'}</td>
                    <td
                      className="p-2 text-xs text-slate-800 whitespace-nowrap"
                      title={
                        r.price_cny_approx != null && r.cny_exchange_multiplier != null
                          ? r.parsed_source === 'hibox_grid'
                            ? `${r.price_hibox_mnt_integer ?? '—'} ₮ ÷ ${effectiveMntPerCny} → CN¥ ${r.price_cny_approx} × ${r.cny_exchange_multiplier} × ${effectiveRate} VNĐ/CN¥`
                            : r.parsed_source === '1688_text_table'
                              ? `CN¥ ${r.price_cny_approx} (cột giá bảng text) × ${r.cny_exchange_multiplier} × ${effectiveRate} VNĐ/CN¥`
                              : `CN¥ ${r.price_cny_approx} × ${r.cny_exchange_multiplier} × ${effectiveRate} VNĐ/CN¥`
                          : undefined
                      }
                    >
                      {formatVndApproxCell(estimateListingVndRounded(r, effectiveRate))}
                    </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
    </>
  );
}
