'use client';

import {
  useState,
  useEffect,
  useMemo,
  useRef,
  useCallback,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react';
import {
  adminProductAPI,
  type AdminImport1688Draft,
  type AdminImport1688ExcelBatchSummary,
  type AdminImport1688BatchStatus,
  type AdminImport1688Job,
  type AdminImportExcelJob,
  type AdminImageLocalizationJob,
  type AdminImageLocalizationSummary,
  type AdminImageLocalizationProductReport,
  type AdminGeminiAuthStatus,
  type AdminProduct,
  type AdminProductsResponse,
  type AdminProductListSort,
} from '@/lib/admin-api';
import { getCatalogFeedApiBaseUrl, isNonPublicCatalogFeedBase } from '@/lib/api-base';
import { productPathSlugFromApi } from '@/lib/product-path-slug';
import { ImportDraftExcelCompare } from '@/components/admin/ImportDraftExcelCompare';

const PAGE_SIZE = 100;

/** Thời gian chờ (giây) khi Google Sheets trả 429 — hiển thị toast đếm ngược. */
const GOOGLE_SHEET_RATE_LIMIT_COOLDOWN_SEC = 120;

function isGoogleSheetsRateLimitMessage(message: string): boolean {
  const m = message.trim();
  if (!m) return false;
  const low = m.toLowerCase();
  return (
    /\b429\b/.test(m) ||
    low.includes('rate_limit_exceeded') ||
    low.includes('quota exceeded') ||
    low.includes('writerequestsperminute') ||
    low.includes('write requests per minute')
  );
}

/** Tóm tắt toast khi đồng bộ nhiều Google Sheet (primary + _2). */
function formatGoogleSheetSyncTargetsSummary(
  targets: Array<{
    ok: boolean;
    field?: string;
    row_mode?: string;
    sheet_title?: string;
    sheet_gid?: number;
    error?: string;
    updated_rows?: number;
    unchanged_rows?: number;
    added_rows?: number;
    removed_orphan_rows?: number;
    removed_duplicate_rows?: number;
  }>,
): string {
  return targets
    .map((t, i) => {
      const tag = t.sheet_title ? `"${t.sheet_title}"` : `Bảng ${i + 1}`;
      if (!t.ok) return `${tag}: ${t.error ?? 'lỗi'}`;
      const parts: string[] = [];
      if (t.updated_rows != null) parts.push(`${t.updated_rows} cập nhật`);
      if (t.unchanged_rows != null) parts.push(`${t.unchanged_rows} giữ nguyên`);
      if (t.added_rows != null && t.added_rows > 0) parts.push(`+${t.added_rows} mới`);
      if (t.removed_orphan_rows != null && t.removed_orphan_rows > 0)
        parts.push(`−${t.removed_orphan_rows} thừa`);
      if (t.removed_duplicate_rows != null && t.removed_duplicate_rows > 0)
        parts.push(`−${t.removed_duplicate_rows} trùng`);
      const rm = t.row_mode && t.row_mode !== 'full' ? `, ${t.row_mode}` : '';
      return `${tag} (${t.field ?? '?'}${rm}): ${parts.length ? parts.join(' · ') : 'ổn định'}`;
    })
    .join(' — ');
}

/** Lưu job_id đang chạy để khôi phục khi reload trang giữa chừng. */
const IMPORT_JOB_STORAGE_KEY = 'admin:products:import_excel:job';

/** Theo dõi batch Excel import link (server xử lý tuần tự) sau khi đóng / mở lại tab. */
const ADMIN_1688_EXCEL_BATCH_TOKEN_KEY = 'admin:products:import_1688_excel_batch_token';

/** Theo dõi một job import từng link Hibox sau khi reload. */
const ADMIN_1688_LINK_JOB_KEY = 'admin:products:import_1688_link_job';

/** Legacy: một job_id — migrate sang IMAGE_LOCALIZATION_JOBS_KEY. */
const IMAGE_LOCALIZATION_JOB_KEY = 'admin:products:image_localization_job';

/** Theo dõi nhiều job bản địa hóa ảnh song song + khôi phục khi reload tab. */
const IMAGE_LOCALIZATION_JOBS_KEY = 'admin:products:image_localization_jobs';

/** Tránh duplicate poll khi Strict Mode mount đôi (dev). */
const resumedImageLocalizationPollSession = new Set<string>();

function readStoredLocalizationJobIds(): string[] {
  try {
    const raw = localStorage.getItem(IMAGE_LOCALIZATION_JOBS_KEY);
    if (raw) {
      const arr = JSON.parse(raw) as unknown;
      if (Array.isArray(arr)) {
        return [...new Set(arr.filter((x): x is string => typeof x === 'string'))];
      }
    }
    const legacy = localStorage.getItem(IMAGE_LOCALIZATION_JOB_KEY);
    return legacy ? [legacy] : [];
  } catch {
    return [];
  }
}

function writeStoredLocalizationJobIds(ids: string[]) {
  try {
    const uniq = [...new Set(ids)];
    if (uniq.length === 0) {
      localStorage.removeItem(IMAGE_LOCALIZATION_JOBS_KEY);
      localStorage.removeItem(IMAGE_LOCALIZATION_JOB_KEY);
    } else {
      localStorage.setItem(IMAGE_LOCALIZATION_JOBS_KEY, JSON.stringify(uniq));
      localStorage.removeItem(IMAGE_LOCALIZATION_JOB_KEY);
    }
  } catch {
    /* noop */
  }
}

function addStoredLocalizationJobId(jobId: string) {
  const cur = readStoredLocalizationJobIds();
  if (!cur.includes(jobId)) cur.push(jobId);
  writeStoredLocalizationJobIds(cur);
}

function removeStoredLocalizationJobId(jobId: string) {
  writeStoredLocalizationJobIds(readStoredLocalizationJobIds().filter((id) => id !== jobId));
}

/** Ô URL trong báo cáo ảnh: xem trước + link — luôn mở trong tab mới (không dùng download). */
function ImageLocReportUrlCell({ url, textClassName }: { url: string; textClassName: string }) {
  const [thumbFailed, setThumbFailed] = useState(false);
  const short = url.length > 72 ? `${url.slice(0, 72)}…` : url;
  return (
    <div className="max-w-[14rem]">
      {!thumbFailed ? (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="mb-1 inline-block overflow-hidden rounded border border-gray-200 bg-gray-50"
          title="Mở ảnh trong tab mới"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={url}
            alt=""
            className="block h-16 w-16 object-cover"
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={() => setThumbFailed(true)}
          />
        </a>
      ) : null}
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className={`block break-all hover:underline ${textClassName}`}
        title="Mở URL trong tab mới"
      >
        {short}
      </a>
    </div>
  );
}

/** Model Gemini API: ảnh hưởng “hiểu” prompt, dịch chữ và giữ layout. imageSize chỉ là độ nét đầu ra. */
const IMAGE_LOC_GEMINI_MODEL_PRESETS: { id: string; label: string; model: string }[] = [
  { id: 'server', label: 'Theo backend (.env) — để trống ô Model', model: '' },
  {
    id: 'pro',
    label: 'Gemini 3 Pro Image — chữ đúng & bố cục chuẩn (pipeline mặc định)',
    model: 'gemini-3-pro-image-preview',
  },
];

function resolveGeminiApiModelPresetId(modelTrimmed: string): string {
  if (!modelTrimmed) return 'server';
  const hit = IMAGE_LOC_GEMINI_MODEL_PRESETS.find((p) => p.model && p.model === modelTrimmed);
  return hit ? hit.id : 'custom';
}

const IMAGE_LOC_OPENAI_MODEL_PRESETS: { id: string; label: string; model: string }[] = [
  { id: 'server', label: 'Theo backend (.env) — để trống ô Model', model: '' },
  { id: 'gpt2', label: 'gpt-image-2 — mặc định OpenAI', model: 'gpt-image-2' },
];

function resolveOpenaiImageModelPresetId(modelTrimmed: string): string {
  if (!modelTrimmed) return 'server';
  const hit = IMAGE_LOC_OPENAI_MODEL_PRESETS.find((p) => p.model && p.model === modelTrimmed);
  return hit ? hit.id : 'custom';
}

/** Gợi ý combo chất lượng + cỡ ảnh GPT Image (có thể chỉnh lại tay sau đó). */
const IMAGE_LOC_OPENAI_OUTPUT_PRESETS: { id: string; label: string; quality: string; size: string }[] = [
  { id: '', label: 'Không ép preset — chỉnh quality/size bên dưới', quality: '', size: '' },
  {
    id: 'hq_catalog',
    label: 'Ưu tiên dịch nghĩa & chi tiết — high + auto (khuyến nghị)',
    quality: 'high',
    size: 'auto',
  },
  {
    id: 'hq_wide',
    label: 'Banner ngang lớn — high + 1792×1024',
    quality: 'high',
    size: '1792x1024',
  },
  {
    id: 'hq_portrait',
    label: 'Dọc / catalogue — high + 1024×1536',
    quality: 'high',
    size: '1024x1536',
  },
];

function resolveOpenaiOutputPresetId(quality: string, size: string): string {
  const q = quality.trim().toLowerCase();
  const s = size.trim().toLowerCase();
  const hit = IMAGE_LOC_OPENAI_OUTPUT_PRESETS.find(
    (p) => p.id && p.quality === q && p.size === s,
  );
  return hit?.id ?? '__custom';
}

/** Giữ lựa chọn «Sắp xếp» sau khi reload trang. */
const ADMIN_PRODUCTS_LIST_SORT_KEY = 'admin:products:list_sort';
const ADMIN_PRODUCTS_LIST_SORT_VALUES: readonly AdminProductListSort[] = [
  'default',
  'views_desc',
  'newest',
  'oldest',
];

function parseStoredProductListSort(raw: string | null): AdminProductListSort | null {
  if (!raw) return null;
  return ADMIN_PRODUCTS_LIST_SORT_VALUES.includes(raw as AdminProductListSort)
    ? (raw as AdminProductListSort)
    : null;
}

/** Origin storefront: ưu tiên NEXT_PUBLIC_SITE_URL để admin chạy localhost vẫn mở đúng shop. */
function adminPublicShopOrigin(): string {
  const env = process.env.NEXT_PUBLIC_SITE_URL?.trim().replace(/\/$/, '');
  if (env) return env;
  if (typeof window !== 'undefined') return window.location.origin;
  return 'https://188.com.vn';
}

function adminProductPublicUrl(slug: string | null | undefined): string | null {
  const seg = productPathSlugFromApi(slug);
  if (!seg) return null;
  return `${adminPublicShopOrigin()}/products/${encodeURIComponent(seg)}`;
}

type Stored1688LinkJob = {
  job_id: string;
  draft_id?: number;
  started_at: number;
  source: '1688' | 'hibox';
};

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
    body.push('', `Bỏ qua — trùng phần id trước «a188» hoặc trùng SKU (${skippedCount}):`);
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
  const toastMsg =
    rowErrs.length
      ? 'Import hoàn thành nhưng có lỗi ở một số dòng — xem chi tiết phía dưới ô Import.'
      : skippedCount > 0
        ? `Import xong — ${skippedCount} dòng bỏ qua (trùng id/SKU); xem báo cáo.`
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

type ProductListEditing = { productId: string; field: string; value: string };

/** Chuỗi JSON gọn để hiển thị trong ô (đúng cấu trúc DB/API). */
function productFieldToJsonCellText(raw: unknown): string {
  if (raw == null || raw === '') return '';
  if (typeof raw === 'string') {
    const t = raw.trim();
    if (
      (t.startsWith('[') && t.endsWith(']')) ||
      (t.startsWith('{') && t.endsWith('}'))
    ) {
      try {
        return JSON.stringify(JSON.parse(t));
      } catch {
        /* giữ nguyên */
      }
    }
    return JSON.stringify(raw);
  }
  try {
    return JSON.stringify(raw);
  } catch {
    return String(raw);
  }
}

function coerceImageUrlItem(item: unknown): string | null {
  if (typeof item === 'string') {
    const s = item.trim();
    return s || null;
  }
  if (item && typeof item === 'object') {
    const row = item as { url?: unknown; src?: unknown };
    if (typeof row.url === 'string' && row.url.trim()) return row.url.trim();
    if (typeof row.src === 'string' && row.src.trim()) return row.src.trim();
  }
  return null;
}

function parseJsonImageFieldEdit(
  value: string,
  mode: 'string' | 'array',
): string | string[] | null {
  const t = value.trim();
  if (!t) return mode === 'array' ? [] : null;
  try {
    const parsed = JSON.parse(t) as unknown;
    if (mode === 'string') {
      if (typeof parsed === 'string') return parsed;
      if (parsed === null) return null;
      if (Array.isArray(parsed)) {
        for (const item of parsed) {
          const url = coerceImageUrlItem(item);
          if (url) return url;
        }
      }
      const single = coerceImageUrlItem(parsed);
      if (single) return single;
      return t;
    }
    if (Array.isArray(parsed)) {
      return parsed
        .map((item) => coerceImageUrlItem(item))
        .filter((url): url is string => Boolean(url));
    }
    const one = coerceImageUrlItem(parsed);
    return one ? [one] : [];
  } catch {
    if (mode === 'array') {
      return t
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean);
    }
    return t;
  }
}

function productListFieldEditSnapshot(product: AdminProduct, field: string): string {
  if (field === 'main_image') return productFieldToJsonCellText(product.main_image);
  if (field === 'images') return productFieldToJsonCellText(product.images);
  if (field === 'gallery') return productFieldToJsonCellText(product.gallery);
  const v = product[field as keyof AdminProduct];
  if (v == null) return '';
  return String(v);
}

function AdminProductJsonFieldCell({
  productId,
  field,
  raw,
  editing,
  saving,
  onStart,
  onEditChange,
  onSave,
  onCancel,
  editMode = 'string',
}: {
  productId: string;
  field: string;
  raw: unknown;
  editing: ProductListEditing | null;
  saving: boolean;
  onStart: (productId: string, field: string, value: string | number) => void;
  onEditChange: (value: string) => void;
  onSave: () => void;
  onCancel: () => void;
  editMode?: 'string' | 'array';
}) {
  const jsonText = productFieldToJsonCellText(raw);
  const isEditing = editing?.productId === productId && editing?.field === field;
  const isArray = editMode === 'array';

  const handleEditKeyDown = (e: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      onCancel();
      return;
    }
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      onSave();
    }
  };

  const editClass =
    'w-full min-w-[12rem] max-w-[14rem] max-h-32 overflow-auto rounded border border-gray-300 px-2 py-1 text-[10px] font-mono text-gray-800 whitespace-pre-wrap break-all resize-y';

  if (isEditing) {
    return (
      <textarea
        autoFocus
        disabled={saving}
        rows={isArray ? 5 : 3}
        value={editing.value}
        onChange={(e) => onEditChange(e.target.value)}
        onBlur={onSave}
        onKeyDown={handleEditKeyDown}
        className={editClass}
        placeholder={
          isArray
            ? 'JSON mảng URL · vd ["url1","url2"] · Ctrl+Enter lưu'
            : 'JSON chuỗi URL · vd "https://…" · Ctrl+Enter lưu'
        }
        aria-label={`Sửa ${field}`}
        spellCheck={false}
      />
    );
  }

  return (
    <div
      role="button"
      tabIndex={0}
      className="w-[14rem] max-w-[14rem] cursor-pointer rounded border border-gray-100 bg-slate-50/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-orange-500"
      onMouseDown={(e) => {
        e.preventDefault();
        onStart(productId, field, jsonText);
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onStart(productId, field, jsonText);
        }
      }}
      title={`${jsonText || 'Trống'} — Bấm để sửa JSON · Cuộn trong ô để xem đủ`}
    >
      {jsonText === '' ? (
        <span className="block p-2 text-xs text-gray-400">— (bấm nhập JSON)</span>
      ) : (
        <pre className="m-0 max-h-20 overflow-auto p-2 text-[10px] leading-snug font-mono text-gray-800 whitespace-pre-wrap break-all">
          {jsonText}
        </pre>
      )}
    </div>
  );
}

function AdminProductEditableCell({
  productId,
  field,
  value,
  display,
  editing,
  saving,
  onStart,
  onEditChange,
  onSave,
  onKeyDown,
  inputType = 'text',
  cellClassName = '',
  inputClassName = 'w-full min-w-[7rem] rounded border border-gray-300 px-2 py-1',
  title = 'Bấm để sửa · Enter lưu · Esc hủy',
}: {
  productId: string;
  field: string;
  value: string | number;
  display: ReactNode;
  editing: ProductListEditing | null;
  saving: boolean;
  onStart: (productId: string, field: string, value: string | number) => void;
  onEditChange: (value: string) => void;
  onSave: () => void;
  onKeyDown: (e: ReactKeyboardEvent<HTMLInputElement>) => void;
  inputType?: 'text' | 'number';
  cellClassName?: string;
  inputClassName?: string;
  title?: string;
}) {
  const isEditing = editing?.productId === productId && editing?.field === field;
  if (isEditing) {
    return (
      <input
        type={inputType}
        autoFocus
        disabled={saving}
        value={editing.value}
        onChange={(e) => onEditChange(e.target.value)}
        onBlur={onSave}
        onKeyDown={onKeyDown}
        className={inputClassName}
      />
    );
  }
  return (
    <span
      role="button"
      tabIndex={0}
      className={`cursor-pointer rounded px-1 -mx-1 hover:bg-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-orange-500 ${cellClassName}`}
      onMouseDown={(e) => {
        e.preventDefault();
        onStart(productId, field, value);
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onStart(productId, field, value);
        }
      }}
      title={title}
    >
      {display}
    </span>
  );
}

export default function AdminProductsPage() {
  const [data, setData] = useState<AdminProductsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  /** Phân biệt lỗi API với danh sách rỗng thật */
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [searchName, setSearchName] = useState('');
  const [searchId, setSearchId] = useState('');
  const [listSort, setListSort] = useState<AdminProductListSort>('default');
  /** Chỉ fetch sau khi đọc localStorage để không bị sort mặc định một nhịp rồi đổi. */
  const [listSortReady, setListSortReady] = useState(false);
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
  /** File đã chọn; upload chỉ khi bấm «Chạy lấy dữ liệu». */
  const [excelBatchFile, setExcelBatchFile] = useState<File | null>(null);
  /** Trang mở khi batch Excel: auto | hibox — khớp backend `fetch_target` (không còn 1688 trực tiếp). */
  const [excelBatchFetchTarget, setExcelBatchFetchTarget] = useState<'auto' | 'hibox'>('auto');
  const [excelBatchTrackToken, setExcelBatchTrackToken] = useState<string | null>(null);
  const [excelBatchHint, setExcelBatchHint] = useState<string | null>(null);
  const [bulkExport1688Busy, setBulkExport1688Busy] = useState(false);
  const [resumeBatchBusy, setResumeBatchBusy] = useState(false);
  /** Tab trong khối Import Hibox — tách luồng để giao diện không chồng chéo. */
  const [import1688SectionTab, setImport1688SectionTab] = useState<'link' | 'excel' | 'history'>('link');
  const [importDraftsLoading, setImportDraftsLoading] = useState(false);
  const [importDraftsError, setImportDraftsError] = useState<string | null>(null);
  const [importExcelBatches, setImportExcelBatches] = useState<AdminImport1688ExcelBatchSummary[]>([]);
  const [importDraftsFilter, setImportDraftsFilter] = useState<'finished' | 'all'>('all');
  const [expandedImportBatchToken, setExpandedImportBatchToken] = useState<string | null>(null);
  const expandedImportBatchTokenRef = useRef<string | null>(null);
  expandedImportBatchTokenRef.current = expandedImportBatchToken;
  const excelBatchTrackTokenRef = useRef<string | null>(null);
  excelBatchTrackTokenRef.current = excelBatchTrackToken;
  const importExcelBatchesRef = useRef<AdminImport1688ExcelBatchSummary[]>([]);
  importExcelBatchesRef.current = importExcelBatches;
  const [importBatchDetail, setImportBatchDetail] = useState<AdminImport1688BatchStatus | null>(null);
  const [importBatchDetailLoading, setImportBatchDetailLoading] = useState(false);
  const [importDraftDeleteTarget, setImportDraftDeleteTarget] = useState<{ id: number } | null>(null);
  const [importDraftDeleting, setImportDraftDeleting] = useState(false);
  const [importBatchDeleteTarget, setImportBatchDeleteTarget] = useState<string | null>(null);
  const [importBatchDeleting, setImportBatchDeleting] = useState(false);
  const [imageLocalizationLanguage, setImageLocalizationLanguage] = useState('vi');
  const [imageLocalizationGeminiMode, setImageLocalizationGeminiMode] = useState<
    'web' | 'api' | 'openai' | 'local_only'
  >('local_only');
  const [imageLocalizationGeminiApiModel, setImageLocalizationGeminiApiModel] = useState('');
  const [imageLocalizationGeminiImageSize, setImageLocalizationGeminiImageSize] = useState('');
  const [imageLocalizationOpenaiModel, setImageLocalizationOpenaiModel] = useState('');
  const [imageLocalizationOpenaiQuality, setImageLocalizationOpenaiQuality] = useState('high');
  const [imageLocalizationOpenaiSize, setImageLocalizationOpenaiSize] = useState('auto');
  const [imageLocalizationCookie, setImageLocalizationCookie] = useState('');
  const [imageLocalizationForce, setImageLocalizationForce] = useState(false);
  const [imageLocalizationPlaywrightHeadless, setImageLocalizationPlaywrightHeadless] = useState(true);
  const imageLocalizationPlaywrightSyncedRef = useRef(false);
  const [imageLocalizationSelectedOnly, setImageLocalizationSelectedOnly] = useState(false);
  const [imageLocalizationSavingCookie, setImageLocalizationSavingCookie] = useState(false);
  /** Đang có ít nhất một vòng poll GET job trên tab này (có thể nhiều job song song phía server). */
  const [localizationPollActive, setLocalizationPollActive] = useState(false);
  /** Chặn double-submit khi POST start job (ngắn). */
  const [localizationStartBusy, setLocalizationStartBusy] = useState(false);
  const localizationPollCountRef = useRef(0);
  const [imageLocalizationJobsById, setImageLocalizationJobsById] = useState<
    Record<string, AdminImageLocalizationJob>
  >({});
  /** Thứ tự hiển thị trong khung Tiến trình (mỗi job một card). */
  const [localizationJobIdsOrdered, setLocalizationJobIdsOrdered] = useState<string[]>([]);
  const localizationCompletionFlushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [imageLocalizationSummary, setImageLocalizationSummary] = useState<AdminImageLocalizationSummary | null>(null);
  const [geminiAuthStatus, setGeminiAuthStatus] = useState<AdminGeminiAuthStatus | null>(null);
  const [imageLocalizationError, setImageLocalizationError] = useState<string | null>(null);
  const [imageLocReportOpen, setImageLocReportOpen] = useState(false);
  const [imageLocReportLoading, setImageLocReportLoading] = useState(false);
  const [imageLocReportData, setImageLocReportData] = useState<AdminImageLocalizationProductReport | null>(null);
  const [imageLocReportError, setImageLocReportError] = useState<string | null>(null);
  const [imageLocReportProductId, setImageLocReportProductId] = useState<string | null>(null);
  /** Cờ huỷ theo dõi (job vẫn chạy ở server). */
  const cancelTrackRef = useRef(false);
  const [exporting, setExporting] = useState(false);
  const [exportingUnusedSkus, setExportingUnusedSkus] = useState(false);
  const [googleSheetSyncing, setGoogleSheetSyncing] = useState(false);
  /** Còn lại giây trước khi cho phép thử đồng bộ lại (quota 429). null = không giới hạn. */
  const [googleSheetRateLimitSec, setGoogleSheetRateLimitSec] = useState<number | null>(null);
  const [unusedSkuExportCount, setUnusedSkuExportCount] = useState(100);
  const [unusedSkuStats, setUnusedSkuStats] = useState<{
    total_space: number;
    available: number;
    used_on_products: number;
    exported_reserved: number;
    blocked_distinct: number;
  } | null>(null);
  const [unusedSkuStatsLoading, setUnusedSkuStatsLoading] = useState(false);
  const [unusedSkuStatsError, setUnusedSkuStatsError] = useState<string | null>(null);
  const [downloadingTemplate, setDownloadingTemplate] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const excelBatch1688InputRef = useRef<HTMLInputElement>(null);

  const [editing, setEditing] = useState<{ productId: string; field: string; value: string } | null>(null);
  const editingRef = useRef(editing);
  editingRef.current = editing;
  const inlineSaveInFlightRef = useRef(false);
  const [saving, setSaving] = useState(false);
  const [selectedProductIds, setSelectedProductIds] = useState<Set<string>>(new Set());

  const catalogFeedBase = useMemo(() => getCatalogFeedApiBaseUrl(), []);

  const showAdminGoogleSheetSync =
    process.env.NEXT_PUBLIC_ADMIN_GOOGLE_SHEET_SYNC !== '0' &&
    process.env.NEXT_PUBLIC_ADMIN_GOOGLE_SHEET_SYNC !== 'false';
  const googleSheetsEditorUrl = (process.env.NEXT_PUBLIC_GOOGLE_SHEETS_EDITOR_URL || '').trim();
  const googleSheetsEditorUrl2 = (process.env.NEXT_PUBLIC_GOOGLE_SHEETS_EDITOR_URL_2 || '').trim();

  const imageLocalizationHeadlessNeedsSavedCookie =
    imageLocalizationGeminiMode === 'web' &&
    imageLocalizationPlaywrightHeadless &&
    Boolean(geminiAuthStatus?.web?.requires_cookie_or_login_marker_for_headless);

  const imageLocalizationGeminiReady = useMemo(() => {
    if (imageLocalizationGeminiMode === 'local_only') return true;
    if (!geminiAuthStatus) return false;
    if (imageLocalizationGeminiMode === 'api') return Boolean(geminiAuthStatus.api?.ready);
    if (imageLocalizationGeminiMode === 'openai') return Boolean(geminiAuthStatus.openai?.ready);
    if (!geminiAuthStatus.web?.ready) return false;
    if (imageLocalizationHeadlessNeedsSavedCookie) return false;
    return true;
  }, [geminiAuthStatus, imageLocalizationGeminiMode, imageLocalizationHeadlessNeedsSavedCookie]);

  /** Gemini Web/API và GPT Image chỉ khi backend cho phép (IMAGE_LOCALIZATION_AI_IMAGE_JOBS_ALLOWED). Chưa có auth = chưa chọn được các nhánh AI. */
  const imageLocAiImageModesSelectable =
    geminiAuthStatus != null && (geminiAuthStatus.ai_image_jobs_allowed ?? true);

  const geminiApiModelPresetSelectValue = useMemo(() => {
    const id = resolveGeminiApiModelPresetId(imageLocalizationGeminiApiModel.trim());
    return id === 'custom' ? 'custom' : id;
  }, [imageLocalizationGeminiApiModel]);

  const openaiImageModelPresetSelectValue = useMemo(() => {
    const id = resolveOpenaiImageModelPresetId(imageLocalizationOpenaiModel.trim());
    return id === 'custom' ? 'custom' : id;
  }, [imageLocalizationOpenaiModel]);

  const openaiOutputPresetSelectValue = useMemo(
    () =>
      resolveOpenaiOutputPresetId(imageLocalizationOpenaiQuality, imageLocalizationOpenaiSize),
    [imageLocalizationOpenaiQuality, imageLocalizationOpenaiSize],
  );
  const feedMerchantCenterTsv = `${catalogFeedBase}/import-export/export/merchant-center-feed.tsv`;
  const feedMetaCatalogTsv = `${catalogFeedBase}/import-export/export/meta-catalog-feed.tsv`;
  const feedTiktokCatalogTsv = `${catalogFeedBase}/import-export/export/tiktok-catalog-feed.tsv`;
  const feedUrlIsNonPublic = isNonPublicCatalogFeedBase(catalogFeedBase);

  const showToast = (type: 'ok' | 'err', msg: string, persistMs?: number) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), persistMs ?? 3000);
  };

  useEffect(() => {
    if (googleSheetRateLimitSec === null) return;
    if (googleSheetRateLimitSec <= 0) {
      setToast(null);
      setGoogleSheetRateLimitSec(null);
      return;
    }
    setToast({
      type: 'err',
      msg: `Google Sheet: quota ghi vượt mức (429). Đếm ngược ${googleSheetRateLimitSec}s (khuyến nghị chờ ~2 phút rồi thử lại).`,
    });
    const t = window.setTimeout(() => {
      setGoogleSheetRateLimitSec((s) => (s === null || s <= 1 ? 0 : s - 1));
    }, 1000);
    return () => window.clearTimeout(t);
  }, [googleSheetRateLimitSec]);

  const openImageLocReport = useCallback(async (productId: string) => {
    setImageLocReportOpen(true);
    setImageLocReportProductId(productId);
    setImageLocReportData(null);
    setImageLocReportError(null);
    setImageLocReportLoading(true);
    try {
      const r = await adminProductAPI.getImageLocalizationProductReport(productId);
      setImageLocReportData(r);
    } catch (e) {
      setImageLocReportError(e instanceof Error ? e.message : 'Không tải được báo cáo');
    } finally {
      setImageLocReportLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!imageLocReportOpen) return;
    const onKey = (ev: globalThis.KeyboardEvent) => {
      if (ev.key === 'Escape') setImageLocReportOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [imageLocReportOpen]);

  const fetchProducts = useCallback(async () => {
    setLoading(true);
    setFetchError(null);
    try {
      const res = await adminProductAPI.getProducts({
        skip: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
        q: searchName.trim() || undefined,
        product_id: searchId.trim() || undefined,
        sort: listSort,
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
  }, [page, searchName, searchId, listSort]);

  useEffect(() => {
    try {
      const parsed = parseStoredProductListSort(localStorage.getItem(ADMIN_PRODUCTS_LIST_SORT_KEY));
      if (parsed) setListSort(parsed);
    } catch {
      /* bỏ qua private mode / quota */
    } finally {
      setListSortReady(true);
    }
  }, []);

  useEffect(() => {
    if (!listSortReady) return;
    fetchProducts();
  }, [listSortReady, fetchProducts]);

  const loadUnusedInternalSkuStats = useCallback(async () => {
    setUnusedSkuStatsLoading(true);
    setUnusedSkuStatsError(null);
    try {
      const s = await adminProductAPI.getUnusedInternalSkuStats();
      setUnusedSkuStats(s);
    } catch (e) {
      setUnusedSkuStats(null);
      setUnusedSkuStatsError(e instanceof Error ? e.message : 'Không tải được số mã SKU');
    } finally {
      setUnusedSkuStatsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadUnusedInternalSkuStats();
  }, [loadUnusedInternalSkuStats]);

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
          message: job.message || 'Đang xử lý link Hibox…',
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

  const loadImageLocalizationSummary = useCallback(async () => {
    try {
      const [summary, auth] = await Promise.all([
        adminProductAPI.getImageLocalizationSummary(),
        adminProductAPI.getGeminiImageLocalizationAuth(imageLocalizationLanguage),
      ]);
      setImageLocalizationSummary(summary);
      setGeminiAuthStatus(auth);
    } catch (err) {
      setImageLocalizationError(err instanceof Error ? err.message : 'Không tải được trạng thái bản địa hóa ảnh');
    }
  }, [imageLocalizationLanguage]);

  const registerLocalizationJobId = useCallback((jobId: string) => {
    setLocalizationJobIdsOrdered((prev) => (prev.includes(jobId) ? prev : [...prev, jobId]));
  }, []);

  const scheduleLocalizationUiFlush = useCallback(() => {
    if (localizationCompletionFlushTimerRef.current != null) return;
    localizationCompletionFlushTimerRef.current = setTimeout(() => {
      localizationCompletionFlushTimerRef.current = null;
      fetchProducts();
      void loadImageLocalizationSummary();
    }, 450);
  }, [fetchProducts, loadImageLocalizationSummary]);

  useEffect(
    () => () => {
      if (localizationCompletionFlushTimerRef.current != null) {
        clearTimeout(localizationCompletionFlushTimerRef.current);
      }
    },
    [],
  );

  const bumpLocalizationPollCount = useCallback((delta: number) => {
    localizationPollCountRef.current += delta;
    setLocalizationPollActive(localizationPollCountRef.current > 0);
  }, []);

  const pollImageLocalizationJob = useCallback(
    async (jobId: string): Promise<AdminImageLocalizationJob> => {
      bumpLocalizationPollCount(1);
      try {
        for (let pollIdx = 0; ; pollIdx += 1) {
          const job = await adminProductAPI.getImageLocalizationJob(jobId);
          setImageLocalizationJobsById((prev) => ({ ...prev, [jobId]: job }));
          if (job.status === 'done' || job.status === 'error' || job.status === 'cancelled') return job;
          const delayMs = pollIdx <= 5 ? 1200 : Math.min(8000, 2500 + pollIdx * 350);
          await new Promise((resolve) => setTimeout(resolve, delayMs));
        }
      } finally {
        bumpLocalizationPollCount(-1);
      }
    },
    [bumpLocalizationPollCount],
  );

  const finishLocalizationPoll = useCallback(
    (jobId: string, job: AdminImageLocalizationJob) => {
      removeStoredLocalizationJobId(jobId);
      resumedImageLocalizationPollSession.delete(jobId);

      const tail = (job.job_id ?? jobId).slice(0, 10);
      if (job.status === 'done') {
        showToast('ok', `Job ảnh ${tail}…: ${job.message || 'Đã hoàn tất'}`, 8000);
        scheduleLocalizationUiFlush();
      } else if (job.status === 'cancelled') {
        showToast('ok', `Job ảnh ${tail}…: đã hủy`);
      } else {
        showToast('err', job.message || `Job ảnh ${tail}… thất bại`, 9000);
      }
    },
    [scheduleLocalizationUiFlush],
  );

  const handleSaveGeminiCookie = async () => {
    const cookie = imageLocalizationCookie.trim();
    if (!cookie) {
      showToast('err', 'Vui lòng dán cookie Gemini');
      return;
    }
    setImageLocalizationSavingCookie(true);
    setImageLocalizationError(null);
    try {
      const res = await adminProductAPI.saveGeminiImageLocalizationCookie(cookie);
      setImageLocalizationCookie('');
      showToast('ok', `Đã lưu ${res.cookie_count} cookie Gemini`);
      await loadImageLocalizationSummary();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Không lưu được cookie Gemini';
      setImageLocalizationError(msg);
      showToast('err', msg, 9000);
    } finally {
      setImageLocalizationSavingCookie(false);
    }
  };

  const handleStartImageLocalization = async () => {
    setImageLocalizationError(null);
    setLocalizationStartBusy(true);
    let startedJobId: string | null = null;
    try {
      const productIds =
        imageLocalizationSelectedOnly && selectedProductIds.size > 0 ? Array.from(selectedProductIds) : undefined;
      const started = await adminProductAPI.startImageLocalization({
        language: imageLocalizationLanguage,
        force: imageLocalizationForce,
        product_ids: productIds,
        gemini_mode: imageLocalizationGeminiMode === 'local_only' ? 'web' : imageLocalizationGeminiMode,
        allow_ai_image_models: imageLocalizationGeminiMode === 'local_only' ? false : null,
        ...(imageLocalizationGeminiMode === 'api' && {
          gemini_image_model: imageLocalizationGeminiApiModel.trim() || undefined,
          gemini_image_size: imageLocalizationGeminiImageSize.trim() || undefined,
        }),
        ...(imageLocalizationGeminiMode === 'openai' && {
          openai_image_model: imageLocalizationOpenaiModel.trim() || undefined,
          openai_image_quality: imageLocalizationOpenaiQuality.trim() || undefined,
          openai_image_size: imageLocalizationOpenaiSize.trim() || undefined,
        }),
        ...(imageLocalizationGeminiMode === 'web' && {
          playwright_headless: imageLocalizationPlaywrightHeadless,
        }),
      });
      startedJobId = started.job_id;
      registerLocalizationJobId(started.job_id);
      addStoredLocalizationJobId(started.job_id);
      setImageLocalizationJobsById((prev) => ({
        ...prev,
        [started.job_id]: {
          job_id: started.job_id,
          status: 'queued',
          message: 'Đã xếp hàng bản địa hóa ảnh.',
        },
      }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Không chạy được bản địa hóa ảnh';
      setImageLocalizationError(msg);
      showToast('err', msg, 9000);
      return;
    } finally {
      setLocalizationStartBusy(false);
    }

    const jid = startedJobId as string;
    void pollImageLocalizationJob(jid)
      .then((job) => {
        finishLocalizationPoll(jid, job);
      })
      .catch((err) => {
        setImageLocalizationError(err instanceof Error ? err.message : 'Không theo dõi được job ảnh');
        removeStoredLocalizationJobId(jid);
      })
      .finally(() => {
        resumedImageLocalizationPollSession.delete(jid);
      });
  };

  const handleCancelImageLocalization = async (jobId: string) => {
    try {
      const job = await adminProductAPI.cancelImageLocalizationJob(jobId);
      setImageLocalizationJobsById((prev) => ({ ...prev, [jobId]: job }));
      showToast('ok', 'Đang hủy job sau ảnh hiện tại');
    } catch (err) {
      showToast('err', err instanceof Error ? err.message : 'Không hủy được job', 8000);
    }
  };

  const localizationJobsForUi = useMemo(() => {
    const out: AdminImageLocalizationJob[] = [];
    for (const id of localizationJobIdsOrdered) {
      const j = imageLocalizationJobsById[id];
      if (j) out.push(j);
    }
    const rank = (s: AdminImageLocalizationJob['status']) =>
      s === 'running' ? 0 : s === 'queued' ? 1 : s === 'error' ? 2 : s === 'cancelled' ? 3 : 4;
    return [...out].sort((a, b) => rank(a.status) - rank(b.status));
  }, [localizationJobIdsOrdered, imageLocalizationJobsById]);

  const localizationActiveJobCount = useMemo(() => {
    let n = 0;
    for (const j of localizationJobsForUi) {
      if (j.status === 'running' || j.status === 'queued') n += 1;
    }
    return n;
  }, [localizationJobsForUi]);

  useEffect(() => {
    if (
      geminiAuthStatus &&
      typeof geminiAuthStatus.playwright_headless === 'boolean' &&
      !imageLocalizationPlaywrightSyncedRef.current
    ) {
      setImageLocalizationPlaywrightHeadless(Boolean(geminiAuthStatus.playwright_headless));
      imageLocalizationPlaywrightSyncedRef.current = true;
    }
  }, [geminiAuthStatus]);

  useEffect(() => {
    if (geminiAuthStatus?.ai_image_jobs_allowed === false && imageLocalizationGeminiMode !== 'local_only') {
      setImageLocalizationGeminiMode('local_only');
    }
  }, [geminiAuthStatus?.ai_image_jobs_allowed, imageLocalizationGeminiMode]);

  useEffect(() => {
    void loadImageLocalizationSummary();
  }, [loadImageLocalizationSummary]);

  useEffect(() => {
    let cancelled = false;
    const ids = readStoredLocalizationJobIds();
    if (ids.length === 0) return undefined;
    ids.forEach((jobId) => {
      registerLocalizationJobId(jobId);
      if (resumedImageLocalizationPollSession.has(jobId)) return;
      resumedImageLocalizationPollSession.add(jobId);
      void pollImageLocalizationJob(jobId)
        .then((job) => {
          if (cancelled) return;
          finishLocalizationPoll(jobId, job);
        })
        .catch((err) => {
          if (!cancelled) {
            const msg = err instanceof Error ? err.message : 'Không theo dõi được job ảnh';
            const is404 = /404|Không tìm thấy job/i.test(msg);
            setImageLocalizationError(
              is404
                ? 'Job ảnh không còn trên server (có thể đã xong hoặc server đã restart trước khi lưu DB). Đã xóa khỏi danh sách theo dõi.'
                : msg,
            );
            removeStoredLocalizationJobId(jobId);
          }
        })
        .finally(() => {
          resumedImageLocalizationPollSession.delete(jobId);
        });
    });
    return () => {
      cancelled = true;
    };
  }, [finishLocalizationPoll, pollImageLocalizationJob, registerLocalizationJobId]);

  const handleImport1688 = async (e: React.FormEvent) => {
    e.preventDefault();
    const url = resolveImportLinkUrl(import1688Url);
    if (!url) {
      showToast('err', 'Vui lòng dán link sản phẩm Hibox (hoặc taobao1688.kz)');
      return;
    }
    if (!isHiboxProductUrl(url)) {
      showToast(
        'err',
        'Chỉ hỗ trợ link Hibox / taobao1688.kz. Import trực tiếp từ 1688.com đã tắt.',
        8000,
      );
      return;
    }
    try {
      localStorage.removeItem(ADMIN_1688_LINK_JOB_KEY);
    } catch {
      /* noop */
    }
    setImporting1688(true);
    setImport1688Draft(null);
    setImport1688Progress({
      message: 'Đang gửi link Hibox lên server…',
      percent: null,
    });
    try {
      const started = await adminProductAPI.startImport1688(url, false, 'hibox');
      try {
        const payload: Stored1688LinkJob = {
          job_id: started.job_id,
          draft_id: started.draft_id,
          started_at: Date.now(),
          source: 'hibox',
        };
        localStorage.setItem(ADMIN_1688_LINK_JOB_KEY, JSON.stringify(payload));
      } catch {
        /* noop */
      }
      setImport1688Progress({
        message: 'Đã nhận link, đang mở trang Hibox…',
        percent: null,
      });
      const job = await pollImport1688Job(started.job_id);
      if (job.status === 'error') {
        const body = [...(job.errors || []), ...(job.warnings || [])].filter(Boolean).join('\n');
        setImportDetailPanel({
          variant: 'err',
          title: 'Import Hibox thất bại',
          body: body || job.message || 'Không đọc được dữ liệu từ link.',
        });
        showToast('err', job.message || 'Import Hibox thất bại', 8000);
        return;
      }
      const draftId = job.draft_id ?? started.draft_id;
      const draft = await adminProductAPI.getImport1688Draft(draftId);
      setImport1688Draft(draft);
      const warnText = draft.warnings?.length ? ` Có ${draft.warnings.length} cảnh báo cần kiểm tra.` : '';
      showToast('ok', `Đã tạo draft từ Hibox.${warnText}`, 6000);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Import Hibox thất bại';
      setImportDetailPanel({
        variant: 'err',
        title: 'Không thể import Hibox',
        body: msg,
      });
      showToast('err', msg, 9000);
    } finally {
      try {
        localStorage.removeItem(ADMIN_1688_LINK_JOB_KEY);
      } catch {
        /* noop */
      }
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
      showToast('ok', 'Đã tải Excel bản nháp import');
    } catch (err) {
      showToast('err', err instanceof Error ? err.message : 'Export Excel nháp thất bại', 8000);
    } finally {
      setExporting1688Draft(false);
    }
  };

  useEffect(() => {
    if (!importDraftDeleteTarget) return undefined;
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape' && !importDraftDeleting && !importBatchDeleting) {
        setImportDraftDeleteTarget(null);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [importDraftDeleteTarget, importDraftDeleting, importBatchDeleting]);

  useEffect(() => {
    if (!importBatchDeleteTarget) return undefined;
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape' && !importBatchDeleting && !importDraftDeleting) {
        setImportBatchDeleteTarget(null);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [importBatchDeleteTarget, importBatchDeleting, importDraftDeleting]);

  useEffect(() => {
    setImportBatchDetail(null);
    if (!expandedImportBatchToken) {
      setImportBatchDetailLoading(false);
      return undefined;
    }
    let cancelled = false;
    setImportBatchDetailLoading(true);
    void adminProductAPI
      .getImport1688ExcelBatchStatus(expandedImportBatchToken)
      .then((st) => {
        if (!cancelled) setImportBatchDetail(st);
      })
      .catch((err) => {
        if (!cancelled) setImportBatchDetail(null);
        setImportDraftsError(
          err instanceof Error ? err.message : 'Không tải được chi tiết đợt import Excel',
        );
      })
      .finally(() => {
        if (!cancelled) setImportBatchDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [expandedImportBatchToken]);

  const loadImportExcelBatchesList = useCallback(async (opts?: { silent?: boolean }) => {
    const silent = Boolean(opts?.silent);
    if (!silent) {
      setImportDraftsLoading(true);
    }
    setImportDraftsError(null);
    try {
      const res = await adminProductAPI.listImport1688ExcelBatches({ limit: 48 });
      setImportExcelBatches(res.items);
    } catch (e) {
      setImportDraftsError(e instanceof Error ? e.message : 'Không tải được danh sách đợt import Excel');
      setImportExcelBatches([]);
    } finally {
      if (!silent) {
        setImportDraftsLoading(false);
      }
    }
  }, []);

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
          setExcelBatchHint(null);
          try {
            localStorage.removeItem(ADMIN_1688_EXCEL_BATCH_TOKEN_KEY);
          } catch {
            /* noop */
          }
          void loadImportExcelBatchesList({ silent: true });
          const openTok = expandedImportBatchTokenRef.current;
          if (openTok === token) {
            void adminProductAPI
              .getImport1688ExcelBatchStatus(token)
              .then((d) => setImportBatchDetail(d))
              .catch(() => {});
          }
          showToast(
            'ok',
            `Đợt import Excel đã xong: ${st.completed} thành công, ${st.failed} lỗi. Danh sách đợt đã được làm mới.`,
            10_000,
          );
        }
      } catch (err) {
        if (!cancelled) {
          const m = err instanceof Error ? err.message : String(err);
          setExcelBatchHint(m || 'Không poll được trạng thái batch');
          if (/\b404\b|Không tìm thấy batch/i.test(m)) {
            try {
              localStorage.removeItem(ADMIN_1688_EXCEL_BATCH_TOKEN_KEY);
            } catch {
              /* noop */
            }
            setExcelBatchTrackToken(null);
            stopInterval();
          }
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
  }, [excelBatchTrackToken, loadImportExcelBatchesList]);

  useEffect(() => {
    if (import1688SectionTab !== 'history') return undefined;
    const tick = () => {
      const rows = importExcelBatchesRef.current;
      const anyPending = rows.some((b) => b.pending > 0);
      if (!anyPending && !excelBatchTrackTokenRef.current?.trim()) return;
      void loadImportExcelBatchesList({ silent: true });
      const exp = expandedImportBatchTokenRef.current;
      if (exp) {
        void adminProductAPI
          .getImport1688ExcelBatchStatus(exp)
          .then((d) => setImportBatchDetail(d))
          .catch(() => {});
      }
    };
    const iv = setInterval(() => void tick(), 4500);
    void tick();
    return () => clearInterval(iv);
  }, [import1688SectionTab, loadImportExcelBatchesList]);

  const handleOpenStoredImportDraft = async (id: number) => {
    try {
      const d = await adminProductAPI.getImport1688Draft(id);
      setImport1688Draft(d);
      if (!d.product_data) {
        showToast(
          'err',
          `Nháp #${id}: ${(d.message || d.errors?.[0] || 'Chưa có dữ liệu sản phẩm').slice(0, 180)}`,
          10000,
        );
      } else {
        showToast('ok', `Đã mở nháp #${id} — chỉnh sửa bên dưới.`, 5000);
      }
      window.setTimeout(() => {
        const goDraft = Boolean(d.product_data);
        document
          .getElementById(goDraft ? 'import-hibox-draft' : 'import-hibox')
          ?.scrollIntoView({ behavior: 'smooth', block: goDraft ? 'nearest' : 'start' });
      }, 120);
    } catch (err) {
      showToast('err', err instanceof Error ? err.message : 'Không mở được nháp', 9000);
    }
  };

  const handleExportExcelBatchByToken = async (batchToken: string) => {
    setBulkExport1688Busy(true);
    try {
      const st = await adminProductAPI.getImport1688ExcelBatchStatus(batchToken);
      const ids = st.items.map((x) => x.draft_id).filter((id) => typeof id === 'number' && id > 0);
      if (!ids.length) {
        showToast('err', 'Đợt này chưa có bản nháp nào để export (đợi hoặc kiểm tra lỗi).', 7000);
        return;
      }
      await adminProductAPI.exportImport1688DraftsExcelBulk(ids);
      showToast('ok', `Đã tải Excel gộp (${ids.length} nháp, chỉ dòng có dữ liệu).`, 8000);
    } catch (err) {
      showToast('err', err instanceof Error ? err.message : 'Export gộp thất bại', 10000);
    } finally {
      setBulkExport1688Busy(false);
    }
  };

  const handleResumeExcelBatch = async (batchToken: string) => {
    setResumeBatchBusy(true);
    try {
      const r = await adminProductAPI.resumeImport1688ExcelBatch(batchToken);
      showToast('ok', r.message, 6500);
      await loadImportExcelBatchesList();
      if (expandedImportBatchToken === batchToken) {
        try {
          const st = await adminProductAPI.getImport1688ExcelBatchStatus(batchToken);
          setImportBatchDetail(st);
        } catch {
          /* noop */
        }
      }
    } catch (err) {
      showToast('err', err instanceof Error ? err.message : 'Chạy tiếp đợt thất bại', 9000);
    } finally {
      setResumeBatchBusy(false);
    }
  };

  const confirmDeleteImportDraft = async () => {
    if (!importDraftDeleteTarget || importDraftDeleting) return;
    setImportDraftDeleting(true);
    try {
      await adminProductAPI.deleteImport1688Draft(importDraftDeleteTarget.id);
      const removedId = importDraftDeleteTarget.id;
      setImportDraftDeleteTarget(null);
      setImport1688Draft((cur) => (cur?.id === removedId ? null : cur));
      showToast('ok', `Đã xóa nháp #${removedId}.`, 5000);
      await loadImportExcelBatchesList();
      if (expandedImportBatchToken) {
        try {
          const st = await adminProductAPI.getImport1688ExcelBatchStatus(expandedImportBatchToken);
          setImportBatchDetail(st);
        } catch {
          /* meta hoặc batch có thể không còn */
        }
      }
    } catch (err) {
      showToast('err', err instanceof Error ? err.message : 'Xóa nháp thất bại', 9000);
    } finally {
      setImportDraftDeleting(false);
    }
  };

  const confirmDeleteImportExcelBatch = async () => {
    if (!importBatchDeleteTarget || importBatchDeleting) return;
    setImportBatchDeleting(true);
    try {
      const res = await adminProductAPI.deleteImport1688ExcelBatch(importBatchDeleteTarget);
      const removed = new Set(res.draft_ids_deleted);
      const tok = res.batch_token;
      setImportBatchDeleteTarget(null);
      setImportExcelBatches((items) => items.filter((b) => b.batch_token !== tok));
      if (expandedImportBatchToken === tok) {
        setExpandedImportBatchToken(null);
        setImportBatchDetail(null);
      }
      if (excelBatchTrackToken === tok) {
        setExcelBatchTrackToken(null);
      }
      try {
        const rawLs = localStorage.getItem(ADMIN_1688_EXCEL_BATCH_TOKEN_KEY);
        const parsedLs = rawLs ? (JSON.parse(rawLs) as { batch_token?: string }) : null;
        if (parsedLs?.batch_token === tok) {
          localStorage.removeItem(ADMIN_1688_EXCEL_BATCH_TOKEN_KEY);
        }
      } catch {
        /* noop */
      }
      setImport1688Draft((cur) => (cur && removed.has(cur.id) ? null : cur));
      showToast('ok', `Đã xóa đợt import và ${res.draft_ids_deleted.length} bản nháp liên quan.`, 6000);
      if (!res.meta_removed) {
        showToast('err', 'Nháp đã xóa nhưng file meta server chưa gỡ — hãy «Làm mới» hoặc báo ops.', 10000);
        void loadImportExcelBatchesList();
      }
    } catch (err) {
      showToast('err', err instanceof Error ? err.message : 'Xóa đợt import thất bại', 10000);
    } finally {
      setImportBatchDeleting(false);
    }
  };

  const importBatchesFiltered = useMemo(() => {
    if (importDraftsFilter !== 'finished') return importExcelBatches;
    return importExcelBatches.filter((b) => b.pending === 0);
  }, [importExcelBatches, importDraftsFilter]);

  useEffect(() => {
    if (import1688SectionTab !== 'history') {
      setExpandedImportBatchToken(null);
    }
  }, [import1688SectionTab]);

  useEffect(() => {
    if (import1688SectionTab === 'history') {
      void loadImportExcelBatchesList();
    }
  }, [import1688SectionTab, loadImportExcelBatchesList]);

  const handleExcelBatch1688Pick = () => {
    excelBatch1688InputRef.current?.click();
  };

  const handleExcelBatch1688Change = (e: React.ChangeEvent<HTMLInputElement>) => {
    const input = e.target;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    setExcelBatchFile(file);
    setExcelBatchHint(
      `Đã chọn «${file.name}». Chế độ «Tự động» sẽ đổi link Taobao/1688 sang Hibox khi có thể; hoặc chọn «Ép về Hibox». Bấm «Chạy lấy dữ liệu».`,
    );
  };

  const handleExcelBatchRun = async () => {
    if (!excelBatchFile) {
      showToast('err', 'Chưa chọn file Excel (.xlsx).', 6000);
      return;
    }
    setExcelBatchBusy(true);
    setExcelBatchHint('Đang tải file và tạo draft cho từng dòng…');
    try {
      const res = await adminProductAPI.uploadImport1688ExcelBatch(excelBatchFile, excelBatchFetchTarget);
      if (res.skipped?.length) {
        const head = res.skipped.slice(0, 4).join(' — ');
        showToast(
          'err',
          `${head}${res.skipped.length > 4 ? '…' : ''} (${res.skipped.length} dòng bỏ qua)`,
          14000,
        );
      }
      setExcelBatchFile(null);
      setExcelBatchTrackToken(res.batch_token);
      try {
        localStorage.setItem(
          ADMIN_1688_EXCEL_BATCH_TOKEN_KEY,
          JSON.stringify({ batch_token: res.batch_token, started_at: Date.now() }),
        );
      } catch {
        /* noop */
      }
      showToast('ok', `Đã nhận ${res.total} link. Server xử lý tuần tự (có thể vài phút).`, 6000);
      setImport1688SectionTab('history');
    } catch (err) {
      setExcelBatchHint(null);
      showToast('err', err instanceof Error ? err.message : 'Upload batch thất bại', 10000);
    } finally {
      setExcelBatchBusy(false);
    }
    void loadImportExcelBatchesList();
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

  useEffect(() => {
    let cancelled = false;
    (async () => {
      type StoredBatch = { batch_token?: string; started_at?: number };
      let s: StoredBatch | null = null;
      try {
        const raw = localStorage.getItem(ADMIN_1688_EXCEL_BATCH_TOKEN_KEY);
        s = raw ? (JSON.parse(raw) as StoredBatch) : null;
      } catch {
        s = null;
      }
      if (!s?.batch_token?.trim()) return;
      const maxAgeMs = 48 * 60 * 60 * 1000;
      if (s.started_at && Date.now() - s.started_at > maxAgeMs) {
        try {
          localStorage.removeItem(ADMIN_1688_EXCEL_BATCH_TOKEN_KEY);
        } catch {
          /* noop */
        }
        return;
      }
      const tok = s.batch_token.trim();
      try {
        const st = await adminProductAPI.getImport1688ExcelBatchStatus(tok);
        if (cancelled) return;
        if (st.pending <= 0) {
          try {
            localStorage.removeItem(ADMIN_1688_EXCEL_BATCH_TOKEN_KEY);
          } catch {
            /* noop */
          }
          return;
        }
        setExcelBatchTrackToken(tok);
        showToast(
          'ok',
          `Đang có batch link chạy dở — tiếp tục hiển thị tiến độ (${st.completed}/${st.total} xong · ${st.failed} lỗi · ${st.pending} đang chờ).`,
          6000,
        );
      } catch {
        try {
          localStorage.removeItem(ADMIN_1688_EXCEL_BATCH_TOKEN_KEY);
        } catch {
          /* noop */
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let saved: Stored1688LinkJob | null = null;
      try {
        const raw = localStorage.getItem(ADMIN_1688_LINK_JOB_KEY);
        saved = raw ? (JSON.parse(raw) as Stored1688LinkJob) : null;
      } catch {
        saved = null;
      }
      if (!saved?.job_id) return;
      if (saved.source === '1688') {
        try {
          localStorage.removeItem(ADMIN_1688_LINK_JOB_KEY);
        } catch {
          /* noop */
        }
        return;
      }
      const maxAgeMs = 2 * 60 * 60 * 1000;
      if (saved.started_at && Date.now() - saved.started_at > maxAgeMs) {
        try {
          localStorage.removeItem(ADMIN_1688_LINK_JOB_KEY);
        } catch {
          /* noop */
        }
        return;
      }
      setImporting1688(true);
      setImport1688Progress({
        message: 'Khôi phục theo dõi import Hibox (job đã gửi trước đó)…',
        percent: null,
      });
      try {
        const job = await pollImport1688Job(saved.job_id);
        if (cancelled) return;
        try {
          localStorage.removeItem(ADMIN_1688_LINK_JOB_KEY);
        } catch {
          /* noop */
        }
        if (job.status === 'error') {
          const body = [...(job.errors || []), ...(job.warnings || [])].filter(Boolean).join('\n');
          setImportDetailPanel({
            variant: 'err',
            title: 'Import Hibox thất bại',
            body: body || job.message || 'Không đọc được dữ liệu từ link.',
          });
          showToast('err', job.message || 'Import Hibox thất bại', 8000);
          return;
        }
        const draftId = job.draft_id ?? saved.draft_id;
        if (draftId == null || draftId <= 0) {
          showToast('err', 'Job xong nhưng không xác định được nháp (draft_id).', 8000);
          return;
        }
        const draft = await adminProductAPI.getImport1688Draft(draftId);
        if (cancelled) return;
        setImport1688Draft(draft);
        const warnText = draft.warnings?.length ? ` Có ${draft.warnings.length} cảnh báo cần kiểm tra.` : '';
        showToast('ok', `Đã tạo draft từ Hibox.${warnText}`, 6000);
      } catch (err) {
        if (cancelled) return;
        const msg = err instanceof Error ? err.message : 'Import Hibox thất bại';
        setImportDetailPanel({
          variant: 'err',
          title: 'Không khôi phục được import Hibox',
          body: msg,
        });
        showToast('err', msg, 9000);
        try {
          localStorage.removeItem(ADMIN_1688_LINK_JOB_KEY);
        } catch {
          /* noop */
        }
      } finally {
        if (!cancelled) {
          setImporting1688(false);
          setImport1688Progress(null);
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

  const handleSyncGoogleSheet = async () => {
    if (googleSheetRateLimitSec !== null) return;
    setGoogleSheetSyncing(true);
    try {
      const r = await adminProductAPI.syncGoogleSheetSkus();
      if (r.skipped) {
        showToast(
          'err',
          r.reason === 'disabled'
            ? 'Đồng bộ Google Sheet đang tắt trên server (kiểm tra GOOGLE_SHEETS_SKU_SYNC_ENABLED).'
            : 'Không đồng bộ.',
          6000,
        );
        return;
      }
      if (!r.ok) {
        const errRaw = r.error ?? 'Đồng bộ Google Sheet thất bại';
        if (isGoogleSheetsRateLimitMessage(errRaw)) {
          setGoogleSheetRateLimitSec(GOOGLE_SHEET_RATE_LIMIT_COOLDOWN_SEC);
          return;
        }
        if (r.partial && r.targets && r.targets.length > 0) {
          showToast(
            'err',
            `Đồng bộ một phần: ${errRaw}. Chi tiết: ${formatGoogleSheetSyncTargetsSummary(r.targets)}`,
            10000,
          );
          return;
        }
        showToast('err', errRaw.length > 500 ? `${errRaw.slice(0, 500)}…` : errRaw, 8000);
        return;
      }
      if (r.targets && r.targets.length > 1) {
        showToast(
          'ok',
          `Google Sheet: ${formatGoogleSheetSyncTargetsSummary(r.targets)}`,
          9000,
        );
        return;
      }
      const parts: string[] = [];
      if (r.updated_rows != null) parts.push(`${r.updated_rows} hàng cập nhật`);
      if (r.unchanged_rows != null) parts.push(`${r.unchanged_rows} hàng giữ nguyên`);
      if (r.added_rows != null && r.added_rows > 0) parts.push(`+${r.added_rows} hàng mới`);
      if (r.removed_orphan_rows != null && r.removed_orphan_rows > 0)
        parts.push(`−${r.removed_orphan_rows} hàng thừa`);
      if (r.removed_duplicate_rows != null && r.removed_duplicate_rows > 0)
        parts.push(`−${r.removed_duplicate_rows} hàng trùng mã`);
      showToast('ok', parts.length ? `Google Sheet: ${parts.join(' · ')}` : 'Đã đồng bộ Google Sheet', 7000);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Đồng bộ Google Sheet lỗi';
      if (isGoogleSheetsRateLimitMessage(msg)) {
        setGoogleSheetRateLimitSec(GOOGLE_SHEET_RATE_LIMIT_COOLDOWN_SEC);
      } else {
        showToast('err', msg, 8000);
      }
    } finally {
      setGoogleSheetSyncing(false);
    }
  };

  const handleExportUnusedInternalSkus = async () => {
    const maxAllowed =
      unusedSkuStats != null ? Math.min(10_000, Math.max(0, unusedSkuStats.available)) : 10_000;
    if (maxAllowed < 1) {
      showToast('err', 'Không còn mã SKU trống để xuất.');
      return;
    }
    const raw = Math.max(1, Math.floor(Number(unusedSkuExportCount) || 0));
    const n = Math.min(maxAllowed, Math.min(10_000, raw));
    setExportingUnusedSkus(true);
    try {
      await adminProductAPI.exportUnusedInternalSkus(n);
      showToast('ok', `Đã tải ${n} mã SKU trống (một cột). Các mã được reserve 7 ngày để lần xuất sau không trùng; sau đó không cần đối chiếu file cũ.`, 7500);
      await loadUnusedInternalSkuStats();
    } catch (e) {
      showToast('err', e instanceof Error ? e.message : 'Export mã SKU trống thất bại');
    } finally {
      setExportingUnusedSkus(false);
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

  const commitInlineEdit = useCallback(async () => {
    const cur = editingRef.current;
    if (!cur || !data?.products || inlineSaveInFlightRef.current) return;
    const product = data.products.find((p) => p.product_id === cur.productId);
    if (!product) {
      setEditing(null);
      return;
    }

    const imageJsonFields = new Set(['main_image', 'images', 'gallery']);
    const previous =
      imageJsonFields.has(cur.field)
        ? productListFieldEditSnapshot(product, cur.field)
        : String((product as Record<string, unknown>)[cur.field] ?? '');
    if (cur.value === previous) {
      setEditing(null);
      return;
    }

    const payload: Record<string, unknown> = {};
    if (cur.field === 'name') payload.name = cur.value;
    if (cur.field === 'price') payload.price = parseFloat(cur.value) || 0;
    if (cur.field === 'product_id') payload.product_id = cur.value;
    if (cur.field === 'brand_name') payload.brand_name = cur.value;
    if (cur.field === 'category') payload.category = cur.value;
    if (cur.field === 'subcategory') payload.subcategory = cur.value;
    if (cur.field === 'sub_subcategory') payload.sub_subcategory = cur.value;
    if (cur.field === 'code') payload.code = cur.value;
    if (cur.field === 'slug') payload.slug = cur.value;
    if (cur.field === 'available') payload.available = parseInt(cur.value, 10) || 0;
    if (cur.field === 'link_default') payload.link_default = cur.value;
    if (cur.field === 'main_image') {
      payload.main_image = parseJsonImageFieldEdit(cur.value, 'string');
    }
    if (cur.field === 'images') {
      payload.images = parseJsonImageFieldEdit(cur.value, 'array');
    }
    if (cur.field === 'gallery') {
      payload.gallery = parseJsonImageFieldEdit(cur.value, 'array');
    }

    if (Object.keys(payload).length === 0) {
      setEditing(null);
      return;
    }

    inlineSaveInFlightRef.current = true;
    setSaving(true);
    try {
      const updated = await adminProductAPI.updateProduct(
        cur.productId,
        payload as Partial<AdminProduct>,
      );
      setData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          products: prev.products.map((p) =>
            p.product_id === cur.productId ? { ...p, ...updated } : p,
          ),
        };
      });
      showToast('ok', 'Đã lưu');
      setEditing(null);
      await fetchProducts();
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Lưu thất bại';
      showToast('err', msg.length > 280 ? `${msg.slice(0, 280)}…` : msg);
    } finally {
      inlineSaveInFlightRef.current = false;
      setSaving(false);
    }
  }, [data?.products, fetchProducts, showToast]);

  const openInlineEdit = useCallback(
    (productId: string, field: string, value: string | number) => {
      void (async () => {
        await commitInlineEdit();
        startEdit(productId, field, value);
      })();
    },
    [commitInlineEdit],
  );

  const saveEdit = () => {
    void commitInlineEdit();
  };

  const handleKeyDown = (e: ReactKeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') saveEdit();
    if (e.key === 'Escape') cancelEdit();
  };

  const toggleProductActive = async (p: AdminProduct) => {
    if (saving) return;
    const nextActive = p.is_active === false;
    setSaving(true);
    try {
      await adminProductAPI.updateProduct(p.product_id, { is_active: nextActive });
      showToast('ok', nextActive ? 'Đã bật hiển thị' : 'Đã ẩn sản phẩm');
      fetchProducts();
    } catch {
      showToast('err', 'Cập nhật trạng thái thất bại');
    } finally {
      setSaving(false);
    }
  };

  const totalPages = data?.total_pages ?? 1;
  const unusedSkuExportMax = useMemo(
    () =>
      unusedSkuStats != null ? Math.min(10_000, Math.max(0, unusedSkuStats.available)) : 10_000,
    [unusedSkuStats],
  );
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
            <div>
              <label htmlFor="admin-products-sort" className="block text-sm font-medium text-gray-700 mb-1">
                Sắp xếp
              </label>
              <select
                id="admin-products-sort"
                value={listSort}
                onChange={(e) => {
                  const v = e.target.value as AdminProductListSort;
                  setListSort(v);
                  setPage(1);
                  try {
                    localStorage.setItem(ADMIN_PRODUCTS_LIST_SORT_KEY, v);
                  } catch {
                    /* ignore */
                  }
                }}
                className="w-52 rounded-lg border border-gray-300 px-3 py-2 text-sm bg-white"
                aria-label="Sắp xếp danh sách sản phẩm"
              >
                <option value="default">ID sản phẩm (mặc định)</option>
                <option value="views_desc">Nhiều lượt xem nhất</option>
                <option value="newest">Từ mới đến cũ</option>
                <option value="oldest">Từ cũ đến mới</option>
              </select>
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
            {showAdminGoogleSheetSync ? (
              <div className="flex flex-col items-stretch gap-1 sm:items-end">
                <button
                  type="button"
                  onClick={() => void handleSyncGoogleSheet()}
                  disabled={googleSheetSyncing || googleSheetRateLimitSec !== null}
                  className="px-4 py-2 bg-sky-600 text-white rounded-lg hover:bg-sky-700 text-sm font-medium disabled:opacity-70 disabled:cursor-not-allowed"
                  title={
                    googleSheetRateLimitSec !== null
                      ? 'Quota Google Sheet (429): chờ hết đếm ngược rồi thử lại.'
                      : 'Cập nhật Google Sheet theo dữ liệu cửa hàng (cần bật đồng bộ trên server và share sheet cho service account).'
                  }
                  aria-busy={googleSheetSyncing}
                  aria-label="Đồng bộ danh sách sản phẩm lên Google Sheet"
                >
                  {googleSheetSyncing
                    ? 'Đang đồng bộ…'
                    : googleSheetRateLimitSec !== null && googleSheetRateLimitSec > 0
                      ? `Chờ ${googleSheetRateLimitSec}s (429)…`
                      : googleSheetRateLimitSec === 0
                        ? 'Đang mở khóa…'
                        : 'Đồng bộ Google Sheet'}
                </button>
                {googleSheetsEditorUrl ? (
                  <a
                    href={googleSheetsEditorUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-sky-800 hover:underline text-center sm:text-right"
                    title="Bảng primary trên backend (GOOGLE_SHEETS_SKU_SPREADSHEET_ID)"
                  >
                    {googleSheetsEditorUrl2 ? 'Mở Sheet (prefix / trước a188)' : 'Mở Google Sheet'}
                  </a>
                ) : null}
                {googleSheetsEditorUrl2 ? (
                  <a
                    href={googleSheetsEditorUrl2}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-sky-800 hover:underline text-center sm:text-right"
                    title="Bảng phụ _2 (GOOGLE_SHEETS_SKU_*_2, thường cột A = SKU)"
                  >
                    Mở Sheet (SKU)
                  </a>
                ) : null}
              </div>
            ) : null}
            <div className="flex flex-wrap items-end gap-2 border-l border-gray-200 pl-3 ml-1">
              <div>
                <label htmlFor="admin-unused-sku-count" className="block text-sm font-medium text-gray-700 mb-1">
                  Số lượng mã SKU cần export
                </label>
                <div className="flex flex-col gap-1">
                  <input
                    id="admin-unused-sku-count"
                    type="number"
                    min={1}
                    max={Math.max(1, unusedSkuExportMax)}
                    value={unusedSkuExportCount}
                    onChange={(e) =>
                      setUnusedSkuExportCount(Math.max(1, parseInt(e.target.value, 10) || 1))
                    }
                    className="w-28 rounded-lg border border-gray-300 px-3 py-2 text-sm"
                    aria-label="Số lượng mã SKU trống cần export"
                    disabled={unusedSkuStatsLoading || unusedSkuExportMax < 1}
                  />
                  {unusedSkuStatsError ? (
                    <p className="text-xs text-red-600 max-w-[14rem]">
                      {unusedSkuStatsError}{' '}
                      <button
                        type="button"
                        onClick={() => void loadUnusedInternalSkuStats()}
                        className="underline font-medium text-red-700"
                      >
                        Thử lại
                      </button>
                    </p>
                  ) : unusedSkuStats ? (
                    <p className="text-[11px] text-gray-600 max-w-[16rem] leading-snug">
                      Còn{' '}
                      <strong className="text-gray-800">
                        {unusedSkuStats.available.toLocaleString('vi-VN')}
                      </strong>{' '}
                      mã có thể xuất (tối đa {Math.min(10_000, unusedSkuExportMax).toLocaleString('vi-VN')} mã /
                      lần). Sau mỗi lần tải file, các mã được reserve <strong className="text-gray-800">7 ngày</strong>{' '}
                      để lần xuất tiếp theo không trùng.
                      {unusedSkuStatsLoading ? ' · đang cập nhật…' : ''}
                    </p>
                  ) : unusedSkuStatsLoading ? (
                    <p className="text-[11px] text-gray-500">Đang tải số mã…</p>
                  ) : null}
                </div>
              </div>
              <button
                type="button"
                onClick={() => void handleExportUnusedInternalSkus()}
                disabled={exportingUnusedSkus || unusedSkuExportMax < 1}
                className="px-4 py-2 bg-slate-700 text-white rounded-lg hover:bg-slate-800 text-sm font-medium disabled:opacity-70 mb-0"
                title="Mã A0001–Z9999 (không X0000): chỉ các mã chưa gán SP và không đang reserve sau lần tải trong 7 ngày."
              >
                {exportingUnusedSkus ? 'Đang tạo file...' : 'Tải SKU trống'}
              </button>
            </div>
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
          <section
            id="import-hibox"
            aria-labelledby="import-hibox-heading"
            className="mt-6 scroll-mt-24 overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm ring-1 ring-slate-900/5"
          >
            <div className="border-b border-slate-100 bg-slate-50/60 px-4 py-4 sm:px-5">
              <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <h2 id="import-hibox-heading" className="text-lg font-semibold tracking-tight text-slate-900">
                    Import Hibox
                  </h2>
                  <p className="mt-1 max-w-2xl text-sm text-slate-600">
                    Một URL hoặc Excel nhiều dòng → bản nháp (chỉ Hibox / taobao1688.kz). Luôn kiểm tra nháp trước khi đăng
                    hoặc xuất Excel.
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <span className="inline-flex items-center rounded-md border border-sky-200 bg-sky-50 px-2 py-0.5 text-[11px] font-medium text-sky-950">
                      Hibox · không cần cookie 1688
                    </span>
                  </div>
                </div>
              </header>

              <div className="mt-4" role="tablist" aria-label="Chế độ import Hibox">
                <div className="flex flex-wrap gap-1 rounded-xl bg-slate-100/95 p-1">
                  <button
                    type="button"
                    role="tab"
                    id="import-1688-tab-link"
                    aria-selected={import1688SectionTab === 'link'}
                    aria-controls="import-1688-panel-link"
                    onClick={() => setImport1688SectionTab('link')}
                    className={`inline-flex min-h-[40px] flex-1 items-center justify-center rounded-lg px-3 py-2 text-sm font-medium transition focus:outline-none focus-visible:ring-2 focus-visible:ring-orange-500 focus-visible:ring-offset-1 sm:flex-none sm:min-w-[7.5rem] ${
                      import1688SectionTab === 'link'
                        ? 'bg-white text-slate-900 shadow-sm ring-1 ring-slate-200/80'
                        : 'text-slate-600 hover:bg-white/80 hover:text-slate-900'
                    }`}
                  >
                    Một link
                  </button>
                  <button
                    type="button"
                    role="tab"
                    id="import-1688-tab-excel"
                    aria-selected={import1688SectionTab === 'excel'}
                    aria-controls="import-1688-panel-excel"
                    onClick={() => setImport1688SectionTab('excel')}
                    className={`inline-flex min-h-[40px] flex-1 items-center justify-center rounded-lg px-3 py-2 text-sm font-medium transition focus:outline-none focus-visible:ring-2 focus-visible:ring-orange-500 focus-visible:ring-offset-1 sm:flex-none sm:min-w-[7.5rem] ${
                      import1688SectionTab === 'excel'
                        ? 'bg-white text-slate-900 shadow-sm ring-1 ring-slate-200/80'
                        : 'text-slate-600 hover:bg-white/80 hover:text-slate-900'
                    }`}
                  >
                    Excel hàng loạt
                  </button>
                  <button
                    type="button"
                    role="tab"
                    id="import-1688-tab-history"
                    aria-selected={import1688SectionTab === 'history'}
                    aria-controls="import-1688-panel-history"
                    onClick={() => setImport1688SectionTab('history')}
                    className={`inline-flex min-h-[40px] flex-1 items-center justify-center rounded-lg px-3 py-2 text-sm font-medium transition focus:outline-none focus-visible:ring-2 focus-visible:ring-orange-500 focus-visible:ring-offset-1 sm:flex-none sm:min-w-[7.5rem] ${
                      import1688SectionTab === 'history'
                        ? 'bg-white text-slate-900 shadow-sm ring-1 ring-slate-200/80'
                        : 'text-slate-600 hover:bg-white/80 hover:text-slate-900'
                    }`}
                  >
                    Lịch sử đợt
                  </button>
                </div>
              </div>
            </div>

            <div className="space-y-4 px-4 py-4 sm:px-5 sm:py-5">
              <input
                ref={excelBatch1688InputRef}
                type="file"
                accept=".xlsx,.xls"
                className="hidden"
                aria-hidden
                onChange={handleExcelBatch1688Change}
              />

              {import1688SectionTab === 'link' ? (
                <div
                  role="tabpanel"
                  id="import-1688-panel-link"
                  aria-labelledby="import-1688-tab-link"
                  className="rounded-xl border border-slate-200/80 bg-slate-50/50 p-4 shadow-sm sm:p-5"
                >
                <h3 className="text-sm font-semibold text-slate-900">Import một link</h3>
                <p className="mt-0.5 text-xs text-gray-500">
                  Dán địa chỉ sản phẩm trên Hibox hoặc mirror <span className="whitespace-nowrap">taobao1688.kz</span>.
                </p>
                <form onSubmit={handleImport1688} className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-end">
                  <div className="min-w-0 flex-1">
                    <label htmlFor="admin-import-hibox-url" className="sr-only">
                      URL nguồn Hibox
                    </label>
                    <input
                      id="admin-import-hibox-url"
                      type="url"
                      value={import1688Url}
                      onChange={(e) => setImport1688Url(e.target.value)}
                      placeholder="https://hibox.mn/v/… hoặc https://taobao1688.kz/item?id=…"
                      className="w-full rounded-lg border border-gray-200 bg-gray-50/50 px-3 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 focus:border-orange-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-orange-300/80"
                      autoComplete="off"
                      spellCheck={false}
                    />
                    <details className="group mt-2 rounded-lg border border-gray-100 bg-gray-50/60 text-xs text-gray-600 [&_summary::-webkit-details-marker]:hidden">
                      <summary className="cursor-pointer list-none px-2.5 py-2 font-medium text-gray-700 outline-none hover:text-gray-900 focus-visible:ring-2 focus-visible:ring-orange-300 rounded-lg">
                        <span className="inline-flex items-center gap-1.5">
                          <span aria-hidden className="text-orange-600 transition group-open:rotate-90">
                            ›
                          </span>
                          Chi tiết: ảnh, Excel → Shop ID, luồng draft
                        </span>
                      </summary>
                      <div className="border-t border-gray-100 px-3 py-2 leading-relaxed text-gray-600">
                        Luồng import Hibox không dùng cookie 1688; ảnh giữ URL gốc trên nháp. Luôn có bước nháp trước khi đăng
                        hoặc export Excel khớp cột import.
                        <span className="mt-2 block">
                          File Excel link: ô <strong>Kiểu dáng / Style</strong> (hoặc cột AI đủ rộng) đồng bộ vào{' '}
                          <strong>Shop ID</strong> và trường kiểu dáng trong nháp.
                        </span>
                      </div>
                    </details>
                  </div>
                  <button
                    type="submit"
                    disabled={importing1688 || !import1688Url.trim()}
                    className="min-h-[42px] shrink-0 rounded-lg bg-orange-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-orange-700 disabled:pointer-events-none disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-offset-2 sm:w-auto w-full"
                  >
                    {importing1688 ? 'Đang lấy dữ liệu…' : 'Lấy dữ liệu'}
                  </button>
                </form>
                </div>
              ) : null}

              {import1688SectionTab === 'excel' ? (
              <div
                role="tabpanel"
                id="import-1688-panel-excel"
                aria-labelledby="import-1688-tab-excel"
                className="rounded-xl border border-slate-200/80 bg-slate-50/50 p-4 shadow-sm sm:p-5"
              >
                <h3 className="text-sm font-semibold text-slate-900">Import hàng loạt từ Excel</h3>
                <p className="mt-0.5 text-xs text-gray-500">
                  Chỉ nhận file <strong>.xlsx</strong> mẫu <strong>tái nhập listing</strong> (hai hàng đầu là nhãn EN/VI).
                  Tiêu đề phải có <strong>Link</strong> (vd. Link SP / item_url) và <strong>Giá Tệ</strong> / China price.
                  <strong>Giá bán VNĐ</strong> trên nháp luôn do backend tính: CN¥ × hệ số lưới × tỷ giá (
                  <code className="rounded bg-white/80 px-1">LISTING_IMPORT_VND_PER_CNY</code>, mặc định 3580; hoặc cột{' '}
                  <code className="rounded bg-white/80 px-1">vnd_per_cny_used</code>), sau đó làm tròn lên bội 10.000&nbsp;₫.
                  Tuỳ chọn: Shop Trung Quốc / Tên tiếng Trung / «Mã sp»{' '}
                  <span className="whitespace-nowrap">[A-Z]0001–9999</span>. Chọn file → chọn cách lấy dữ liệu → bấm chạy;
                  URL sẽ được chuẩn hoá về Hibox: Taobao/Tmall và offer 1688 → <span className="whitespace-nowrap">hibox.mn/v/…</span>{' '}
                  khi đọc được mã; hoặc dòng bị bỏ qua kèm lý do nếu không quy đổi được.
                </p>
                <div className="mt-3 flex flex-col gap-3">
                  <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
                    <button
                      type="button"
                      onClick={handleExcelBatch1688Pick}
                      disabled={excelBatchBusy}
                      className="inline-flex flex-1 min-w-[12rem] items-center justify-center rounded-lg border border-orange-200 bg-white px-4 py-2.5 text-sm font-semibold text-orange-800 shadow-sm hover:bg-orange-50 disabled:pointer-events-none disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-offset-2 sm:flex-none sm:justify-start"
                    >
                      Chọn file Excel (.xlsx)
                    </button>
                    <div className="flex min-w-0 flex-1 flex-col gap-1 sm:max-w-md">
                      <label htmlFor="admin-excel-batch-fetch-target" className="text-xs font-medium text-slate-700">
                        Lấy dữ liệu từ trang
                      </label>
                      <select
                        id="admin-excel-batch-fetch-target"
                        value={excelBatchFetchTarget}
                        onChange={(e) => setExcelBatchFetchTarget(e.target.value as 'auto' | 'hibox')}
                        disabled={excelBatchBusy}
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-orange-300 focus:outline-none focus:ring-2 focus:ring-orange-300/80 disabled:opacity-60"
                      >
                        <option value="auto">Tự động — Taobao / 1688 → Hibox khi đổi được</option>
                        <option value="hibox">Ép về Hibox (hibox.mn)</option>
                      </select>
                    </div>
                    <button
                      type="button"
                      onClick={handleExcelBatchRun}
                      disabled={excelBatchBusy || !excelBatchFile}
                      className="inline-flex min-h-[42px] flex-1 min-w-[12rem] items-center justify-center rounded-lg bg-orange-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-orange-700 disabled:pointer-events-none disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-offset-2 sm:flex-none sm:justify-center"
                    >
                      {excelBatchBusy ? 'Đang chạy…' : 'Chạy lấy dữ liệu'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setImport1688SectionTab('history')}
                      className="inline-flex items-center justify-center rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-orange-500 focus-visible:ring-offset-2 sm:min-h-[42px]"
                    >
                      Xem lịch sử đợt
                    </button>
                  </div>
                  <p className="text-xs text-slate-600" aria-live="polite">
                    {excelBatchFile ? (
                      <>
                        File đã chọn: <span className="font-medium text-slate-800">{excelBatchFile.name}</span>
                      </>
                    ) : (
                      <>Chưa có file — bấm «Chọn file Excel» trước.</>
                    )}
                  </p>
                </div>
                {excelBatchHint ? (
                  <p className="mt-3 rounded-md border border-amber-100 bg-amber-50/80 px-3 py-2 text-xs text-amber-950">
                    {excelBatchHint}
                  </p>
                ) : null}
                {excelBatchTrackToken ? (
                  <p className="mt-2 text-[11px] leading-snug text-gray-500">
                    Tiến độ batch được lưu trong trình duyệt: đóng tab rồi mở lại vẫn xem được phần đã xử lý và còn chờ (khoảng 48 giờ;
                    xóa đợt hoặc mất file meta trên server thì không còn dữ liệu theo dõi).
                  </p>
                ) : null}
              </div>
              ) : null}

            {import1688SectionTab === 'history' ? (
              <div
                className="rounded-xl border border-slate-200/90 bg-white p-4 shadow-sm sm:p-5"
                role="tabpanel"
                id="import-1688-panel-history"
                aria-labelledby="import-1688-tab-history"
              >
                <div className="flex flex-col gap-3 border-b border-slate-100 pb-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0 max-w-xl">
                    <h3 id="import-1688-batches-heading" className="text-sm font-semibold text-slate-900">
                      Các đợt import Excel
                    </h3>
                    <p className="mt-0.5 text-xs text-slate-600 leading-relaxed">
                      Mỗi dòng dưới đây là một lần bạn upload file. Mở rộng để xem từng link / nháp; dùng «Chạy tiếp» nếu
                      còn link đang chờ.
                    </p>
                    <details className="group mt-2 text-xs text-slate-600 [&_summary::-webkit-details-marker]:hidden">
                      <summary className="inline-flex cursor-pointer list-none items-center gap-1 font-medium text-slate-800 outline-none hover:text-slate-950 focus-visible:ring-2 focus-visible:ring-orange-400 rounded">
                        <span aria-hidden className="text-orange-600 transition group-open:rotate-90">
                          ›
                        </span>
                        Ghi chú nâng cao (resume server, thư mục meta…)
                      </summary>
                      <div className="mt-1.5 rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2 leading-relaxed">
                        Sau khi restart backend có thể bật biến môi trường{' '}
                        <code className="rounded bg-white px-0.5 text-[10px]">IMPORT_1688_BATCH_RESUME_ON_STARTUP</code> để tự
                        xếp hàng lại. Danh sách dựa trên file meta trong{' '}
                        <code className="rounded bg-white px-0.5 text-[10px]">uploads/import_batches</code>; deploy server mới
                        không copy thư mục này thì lịch sử đợt có thể trống dù nháp vẫn trong database.
                      </div>
                    </details>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 shrink-0">
                    <label className="text-xs text-gray-600 whitespace-nowrap">Lọc:</label>
                    <select
                      value={importDraftsFilter}
                      onChange={(e) =>
                        setImportDraftsFilter(e.target.value === 'all' ? 'all' : 'finished')
                      }
                      className="rounded-lg border border-gray-300 px-2 py-1 text-xs"
                    >
                      <option value="finished">Đợt đã xử lý xong (không còn link đang chạy)</option>
                      <option value="all">Mọi đợt</option>
                    </select>
                    <button
                      type="button"
                      onClick={() => void loadImportExcelBatchesList()}
                      disabled={importDraftsLoading}
                      className="rounded-lg border border-gray-300 bg-gray-50 px-2 py-1 text-xs font-medium hover:bg-gray-100 disabled:opacity-60"
                    >
                      {importDraftsLoading ? 'Đang tải…' : 'Làm mới'}
                    </button>
                  </div>
                </div>
                {importDraftsError ? (
                  <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
                    {importDraftsError}{' '}
                    <button
                      type="button"
                      onClick={() => void loadImportExcelBatchesList()}
                      className="ml-2 underline font-medium"
                    >
                      Thử lại
                    </button>
                  </div>
                ) : null}
                {importDraftsLoading && importExcelBatches.length === 0 ? (
                  <p className="text-sm text-gray-600">Đang tải danh sách đợt…</p>
                ) : importBatchesFiltered.length === 0 ? (
                  <p className="text-sm text-gray-600">
                    Chưa có đợt import Excel nào trên máy chủ này (hoặc không khớp lọc). Upload file Excel link để tạo
                    đợt mới.
                  </p>
                ) : (
                  <div className="space-y-2 max-h-[min(32rem,55vh)] overflow-y-auto pr-1">
                    {importBatchesFiltered.map((batch) => {
                      const open = expandedImportBatchToken === batch.batch_token;
                      const when = batch.created_at
                        ? String(batch.created_at).replace('T', ' ').replace('+00:00', ' UTC').slice(0, 19)
                        : '—';
                      const shortTok =
                        batch.batch_token.length > 14
                          ? `${batch.batch_token.slice(0, 12)}…`
                          : batch.batch_token;
                      return (
                        <div
                          key={batch.batch_token}
                          className="rounded-lg border border-gray-200 bg-gray-50/80 overflow-hidden"
                        >
                          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between px-3 py-2.5">
                            <div className="min-w-0">
                              <div className="flex flex-wrap items-center gap-2">
                                <button
                                  type="button"
                                  onClick={() =>
                                    setExpandedImportBatchToken(open ? null : batch.batch_token)
                                  }
                                  className="text-left text-sm font-semibold text-gray-900 hover:text-sky-800"
                                  aria-expanded={open}
                                >
                                  <span className="inline-block w-4 text-gray-500">{open ? '▼' : '▶'}</span>{' '}
                                  Đợt <span className="font-mono text-xs" title={batch.batch_token}>
                                    {shortTok}
                                  </span>
                                </button>
                                {batch.pending > 0 ? (
                                  <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-medium text-amber-900">
                                    Còn {batch.pending} đang chạy
                                  </span>
                                ) : (
                                  <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[11px] font-medium text-emerald-900">
                                    Xong
                                  </span>
                                )}
                              </div>
                              <p className="mt-1 text-[11px] text-gray-600">
                                {when} · {batch.total_links} link · đã OK {batch.completed} · lỗi{' '}
                                {batch.failed}
                                {batch.skipped_lines > 0
                                  ? ` · ${batch.skipped_lines} dòng bỏ qua khi nhận file`
                                  : ''}
                              </p>
                            </div>
                            <div className="flex flex-wrap gap-2 shrink-0">
                              {batch.pending > 0 ? (
                                <button
                                  type="button"
                                  onClick={() => void handleResumeExcelBatch(batch.batch_token)}
                                  disabled={
                                    resumeBatchBusy || bulkExport1688Busy || importBatchDeleting
                                  }
                                  className="rounded-lg border border-emerald-300 bg-white px-2.5 py-1.5 text-xs font-medium text-emerald-900 hover:bg-emerald-50 disabled:opacity-60"
                                >
                                  {resumeBatchBusy ? 'Đang xếp hàng…' : 'Chạy tiếp'}
                                </button>
                              ) : null}
                              <button
                                type="button"
                                onClick={() =>
                                  void handleExportExcelBatchByToken(batch.batch_token)
                                }
                                disabled={bulkExport1688Busy || resumeBatchBusy || importBatchDeleting}
                                className="rounded-lg border border-amber-300 bg-white px-2.5 py-1.5 text-xs font-medium text-amber-900 hover:bg-amber-50 disabled:opacity-60"
                              >
                                {bulkExport1688Busy ? 'Đang tải…' : 'Export Excel đợt này'}
                              </button>
                              <button
                                type="button"
                                onClick={() => {
                                  setImportDraftDeleteTarget(null);
                                  setImportBatchDeleteTarget(batch.batch_token);
                                }}
                                disabled={
                                  bulkExport1688Busy ||
                                  resumeBatchBusy ||
                                  importBatchDeleting ||
                                  importDraftDeleting
                                }
                                className="rounded-lg border border-red-200 bg-white px-2.5 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-60"
                              >
                                Xóa đợt
                              </button>
                            </div>
                          </div>
                          {open ? (
                            <div className="border-t border-gray-200 bg-white px-2 py-2">
                              {importBatchDetailLoading ? (
                                <p className="text-xs text-gray-600 px-2 py-3">
                                  Đang tải chi tiết từng link…
                                </p>
                              ) : importBatchDetail && importBatchDetail.batch_token === batch.batch_token ? (
                                importBatchDetail.items.length === 0 ? (
                                  <p className="text-xs text-gray-600 px-2 py-2">
                                    Không còn bản nháp nào trong đợt (đã xóa hết khỏi DB hoặc dữ liệu lệch).
                                  </p>
                                ) : (
                                  <div className="overflow-x-auto max-h-[min(20rem,40vh)] overflow-y-auto rounded border border-gray-100">
                                    <table className="min-w-full text-xs">
                                      <thead className="bg-gray-50 sticky top-0 z-10 border-b border-gray-200">
                                        <tr>
                                          <th className="px-2 py-2 text-left font-semibold text-gray-700">
                                            Draft #
                                          </th>
                                          <th className="px-2 py-2 text-left font-semibold text-gray-700">
                                            Dòng Excel
                                          </th>
                                          <th className="px-2 py-2 text-left font-semibold text-gray-700">
                                            Trạng thái
                                          </th>
                                          <th className="px-2 py-2 text-left font-semibold text-gray-700">
                                            Ghi chú
                                          </th>
                                          <th className="px-2 py-2 text-right font-semibold text-gray-700">
                                            Thao tác
                                          </th>
                                        </tr>
                                      </thead>
                                      <tbody className="divide-y divide-gray-100">
                                        {importBatchDetail.items.map((row) => {
                                          const st = String(row.status || '').toLowerCase();
                                          const stCls =
                                            st === 'done' || st === 'published'
                                              ? 'bg-emerald-100 text-emerald-900'
                                              : st === 'error'
                                                ? 'bg-red-100 text-red-900'
                                                : st === 'running' || st === 'queued'
                                                  ? 'bg-amber-100 text-amber-900'
                                                  : 'bg-gray-100 text-gray-800';
                                          const msg = row.message || '';
                                          return (
                                            <tr key={row.draft_id}>
                                              <td className="px-2 py-2 font-mono text-gray-800 tabular-nums">
                                                {row.draft_id}
                                              </td>
                                              <td className="px-2 py-2 text-gray-700 tabular-nums">
                                                {row.excel_row != null ? row.excel_row : '—'}
                                              </td>
                                              <td className="px-2 py-2 whitespace-nowrap">
                                                <span
                                                  className={`rounded px-1.5 py-0.5 font-medium ${stCls}`}
                                                >
                                                  {row.status}
                                                </span>
                                              </td>
                                              <td
                                                className="px-2 py-2 text-gray-700 max-w-[18rem] sm:max-w-md break-words"
                                                title={msg}
                                              >
                                                {msg
                                                  ? msg.length > 160
                                                    ? `${msg.slice(0, 158)}…`
                                                    : msg
                                                  : '—'}
                                              </td>
                                              <td className="px-2 py-2 text-right whitespace-nowrap">
                                                <span className="inline-flex gap-3 justify-end">
                                                  <button
                                                    type="button"
                                                    onClick={() =>
                                                      void handleOpenStoredImportDraft(row.draft_id)
                                                    }
                                                    className="text-sky-700 hover:underline font-medium"
                                                  >
                                                    Mở
                                                  </button>
                                                  <button
                                                    type="button"
                                                    onClick={() => {
                                                      setImportBatchDeleteTarget(null);
                                                      setImportDraftDeleteTarget({ id: row.draft_id });
                                                    }}
                                                    className="text-red-700 hover:underline font-medium"
                                                    aria-label={`Xóa nháp import #${row.draft_id}`}
                                                  >
                                                    Xóa
                                                  </button>
                                                </span>
                                              </td>
                                            </tr>
                                          );
                                        })}
                                      </tbody>
                                    </table>
                                  </div>
                                )
                              ) : (
                                <p className="text-xs text-gray-600 px-2 py-2">
                                  Không tải được chi tiết. Thử đóng và mở lại đợt.
                                </p>
                              )}
                            </div>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                )}
                <details className="mt-3 rounded-lg border border-slate-100 bg-slate-50/60 text-[11px] text-slate-600 [&_summary::-webkit-details-marker]:hidden">
                  <summary className="cursor-pointer list-none px-3 py-2 font-medium text-slate-700 hover:text-slate-900">
                    Về nguồn danh sách (48 đợt, file meta trên server)
                  </summary>
                  <p className="border-t border-slate-100 px-3 py-2 leading-relaxed">
                    Danh sách theo file meta trên server (<code className="text-[10px]">uploads/import_batches</code>). Mỗi lần
                    làm mới tải tối đa 48 đợt mới nhất
                    {importExcelBatches.length > 0 ? ` (đang hiển thị ${importExcelBatches.length})` : ''}.
                  </p>
                </details>
              </div>
            ) : null}
            </div>

            <div className="border-t border-slate-100 bg-slate-50/25 px-4 py-4 sm:px-5 sm:py-5 space-y-4">
            {importing1688 && import1688Progress ? (
              <div
                className="rounded-xl border border-orange-200/90 bg-white p-4 shadow-sm ring-1 ring-orange-100/60"
                role="status"
                aria-live="polite"
                aria-busy="true"
              >
                <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-orange-900/90">Đang xử lý</p>
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
                <p className="mt-2 text-[11px] text-gray-500 leading-snug">
                  Job được lưu trên trình duyệt (khoảng 2 giờ): đóng tab rồi mở lại trang này sẽ tự tiếp tục kiểm tra tiến độ cho đến khi xong hoặc lỗi.
                </p>
              </div>
            ) : null}

            {import1688Draft?.product_data ? (
              <div
                id="import-hibox-draft"
                className="scroll-mt-28 rounded-xl border border-slate-200/90 bg-white p-4 shadow-sm ring-1 ring-slate-900/5 sm:p-5"
              >
                <div className="mb-4 flex flex-col gap-1 border-b border-gray-100 pb-3 sm:flex-row sm:flex-wrap sm:items-end sm:justify-between">
                  <div>
                    <h3 className="text-base font-semibold text-gray-900">Chỉnh sửa nháp</h3>
                    <p className="text-xs text-gray-500">Kiểm tra trường trước khi đăng hoặc xuất Excel.</p>
                  </div>
                  {import1688Draft?.id != null ? (
                    <span className="inline-flex rounded-md border border-gray-200 bg-gray-50 px-2 py-1 font-mono text-xs text-gray-700">
                      Draft #{import1688Draft.id}
                    </span>
                  ) : null}
                </div>
                <div className="flex flex-col lg:flex-row gap-4">
                  <div className="w-full lg:w-40 shrink-0">
                    {import1688Draft.product_data.main_image ? (
                      <a
                        href={String(import1688Draft.product_data.main_image)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
                        title="Mở ảnh trong tab mới"
                      >
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={String(import1688Draft.product_data.main_image)}
                          alt={String(import1688Draft.product_data.name || 'Ảnh sản phẩm nháp')}
                          className="h-40 w-full object-cover rounded-lg border border-gray-200 bg-gray-50"
                        />
                      </a>
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
                      <label className="block text-xs font-medium text-gray-700 mb-1">
                        Shop ID <span className="text-gray-500 font-normal">(Excel: ô Kiểu dáng / Style)</span>
                      </label>
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

            {importDraftDeleteTarget ? (
              <div
                className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 p-4"
                role="presentation"
                onClick={(e) => {
                  if (e.target === e.currentTarget && !importDraftDeleting && !importBatchDeleting)
                    setImportDraftDeleteTarget(null);
                }}
              >
                <div
                  role="dialog"
                  aria-modal="true"
                  aria-labelledby="import-draft-delete-title"
                  className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-5 shadow-xl"
                  onClick={(e) => e.stopPropagation()}
                >
                  <h3 id="import-draft-delete-title" className="text-base font-semibold text-gray-900">
                    Xóa nháp import?
                  </h3>
                  <p className="mt-2 text-sm text-gray-600 leading-relaxed">
                    Nháp <span className="font-mono">#{importDraftDeleteTarget.id}</span> sẽ bị xóa{' '}
                    <strong className="font-medium text-gray-800">vĩnh viễn</strong>. Thao tác này không hoàn tác.
                  </p>
                  <div className="mt-5 flex flex-wrap justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => !importDraftDeleting && setImportDraftDeleteTarget(null)}
                      disabled={importDraftDeleting}
                      className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-60"
                    >
                      Hủy
                    </button>
                    <button
                      type="button"
                      onClick={() => void confirmDeleteImportDraft()}
                      disabled={importDraftDeleting}
                      className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
                    >
                      {importDraftDeleting ? 'Đang xóa…' : 'Xóa'}
                    </button>
                  </div>
                </div>
              </div>
            ) : null}

            {importBatchDeleteTarget ? (
              <div
                className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 p-4"
                role="presentation"
                onClick={(e) => {
                  if (e.target === e.currentTarget && !importBatchDeleting && !importDraftDeleting)
                    setImportBatchDeleteTarget(null);
                }}
              >
                <div
                  role="dialog"
                  aria-modal="true"
                  aria-labelledby="import-batch-delete-title"
                  className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-5 shadow-xl"
                  onClick={(e) => e.stopPropagation()}
                >
                  <h3 id="import-batch-delete-title" className="text-base font-semibold text-gray-900">
                    Xóa cả đợt import Excel?
                  </h3>
                  <p className="mt-2 text-sm text-gray-600 leading-relaxed">
                    Đợt{' '}
                    <span className="font-mono text-xs break-all" title={importBatchDeleteTarget}>
                      {importBatchDeleteTarget.length > 20
                        ? `${importBatchDeleteTarget.slice(0, 18)}…`
                        : importBatchDeleteTarget}
                    </span>
                    : file meta trên server và <strong className="font-medium text-gray-800">tất cả bản nháp</strong>{' '}
                    trong đợt sẽ bị xóa vĩnh viễn. Không hoàn tác.
                  </p>
                  <div className="mt-5 flex flex-wrap justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => !importBatchDeleting && setImportBatchDeleteTarget(null)}
                      disabled={importBatchDeleting}
                      className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-60"
                    >
                      Hủy
                    </button>
                    <button
                      type="button"
                      onClick={() => void confirmDeleteImportExcelBatch()}
                      disabled={importBatchDeleting}
                      className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
                    >
                      {importBatchDeleting ? 'Đang xóa…' : 'Xóa đợt'}
                    </button>
                  </div>
                </div>
              </div>
            ) : null}
          </section>
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

        <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-gray-900">Bản địa hóa ảnh</h2>
              <p className="mt-1 text-sm text-gray-600">
                Xử lý ảnh cột O/P/Q/T: biến thể, thư viện ảnh, ảnh chi tiết và ảnh chính cho sản phẩm chưa bản địa hóa.
              </p>
            </div>
            <button
              type="button"
              onClick={() => void loadImageLocalizationSummary()}
              className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Làm mới trạng thái
            </button>
          </div>

          <p
            className={
              geminiAuthStatus?.ai_image_jobs_allowed === false
                ? 'mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-950 leading-relaxed'
                : 'mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-800 leading-relaxed'
            }
          >
            {geminiAuthStatus?.ai_image_jobs_allowed === false ? (
              <>
                <span className="font-semibold">Đang chỉ bật pipeline DeepSeek + vẽ local</span> (OCR → DeepSeek dịch → vẽ chữ).{' '}
                Gemini / GPT ảnh <span className="font-medium">tạm tắt</span> trên server — bật lại bằng{' '}
                <code className="text-[11px]">IMAGE_LOCALIZATION_AI_IMAGE_JOBS_ALLOWED=true</code> trong .env backend.
              </>
            ) : (
              <>
                <span className="font-semibold text-slate-900">Mặc định giao diện:</span>{' '}
                <span className="font-medium">DeepSeek + vẽ local</span> (OCR → dịch → vẽ chữ); Gemini / GPT chỉ khi chọn chủ động — model Pro và ảnh{' '}
                <span className="font-medium">2K hoặc 4K</span>; GPT chỉ <span className="font-medium">high/auto</span> và cỡ ảnh lớn.
              </>
            )}
          </p>

          <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(22rem,28rem)]">
            <div className="space-y-3">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <label className="block text-sm lg:col-span-2">
                  <span className="mb-1 block font-medium text-gray-700">Sinh/sửa ảnh (chữ Trung → bản địa)</span>
                  <div className="flex flex-col gap-2 rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-700">
                    <label className="flex cursor-pointer items-start gap-2">
                      <input
                        type="radio"
                        name="imageLocalizationGeminiMode"
                        className="mt-1"
                        checked={imageLocalizationGeminiMode === 'local_only'}
                        onChange={() => setImageLocalizationGeminiMode('local_only')}
                        disabled={localizationStartBusy}
                      />
                      <span>
                        <span className="font-medium">DeepSeek + vẽ local (không AI ảnh Gemini/GPT)</span>
                        <span className="mt-0.5 block text-xs text-gray-500">
                          OCR (Vision) → <span className="font-medium">DeepSeek</span> dịch → <span className="font-medium">vẽ local</span>{' '}
                          chữ trên ảnh. Không gọi Gemini/GPT sinh/chỉnh cả khung (ổn với ảnh dài / split). Không cần cookie hay key
                          Gemini/OpenAI cho nhánh này.
                        </span>
                      </span>
                    </label>
                    <label
                      className={`flex items-start gap-2 ${imageLocAiImageModesSelectable ? 'cursor-pointer' : 'cursor-not-allowed opacity-55'}`}
                    >
                      <input
                        type="radio"
                        name="imageLocalizationGeminiMode"
                        className="mt-1"
                        checked={imageLocalizationGeminiMode === 'web'}
                        onChange={() => setImageLocalizationGeminiMode('web')}
                        disabled={localizationStartBusy || !imageLocAiImageModesSelectable}
                      />
                      <span>
                        <span className="font-medium">Gemini trên trình duyệt</span>
                        {geminiAuthStatus?.ai_image_jobs_allowed === false ? (
                          <span className="ml-1 text-xs font-normal text-gray-400">(tạm tắt)</span>
                        ) : null}
                        <span className="mt-0.5 block text-xs text-gray-500">
                          Playwright + cookie / profile (Nano Banana như khi dùng tay trên gemini.google.com).
                        </span>
                      </span>
                    </label>
                    <label
                      className={`flex items-start gap-2 ${imageLocAiImageModesSelectable ? 'cursor-pointer' : 'cursor-not-allowed opacity-55'}`}
                    >
                      <input
                        type="radio"
                        name="imageLocalizationGeminiMode"
                        className="mt-1"
                        checked={imageLocalizationGeminiMode === 'api'}
                        onChange={() => setImageLocalizationGeminiMode('api')}
                        disabled={localizationStartBusy || !imageLocAiImageModesSelectable}
                      />
                      <span>
                        <span className="font-medium">Gemini API (GEMINI_API_KEY)</span>
                        {geminiAuthStatus?.ai_image_jobs_allowed === false ? (
                          <span className="ml-1 text-xs font-normal text-gray-400">(tạm tắt)</span>
                        ) : null}
                        <span className="mt-0.5 block text-xs text-gray-500">
                          Model sinh/sửa ảnh trên server (mặc định{' '}
                          {geminiAuthStatus?.image_model || 'gemini-3-pro-image-preview'}). Không cần cookie; cần key trong backend.
                        </span>
                      </span>
                    </label>
                    <label
                      className={`flex items-start gap-2 ${imageLocAiImageModesSelectable ? 'cursor-pointer' : 'cursor-not-allowed opacity-55'}`}
                    >
                      <input
                        type="radio"
                        name="imageLocalizationGeminiMode"
                        className="mt-1"
                        checked={imageLocalizationGeminiMode === 'openai'}
                        onChange={() => setImageLocalizationGeminiMode('openai')}
                        disabled={localizationStartBusy || !imageLocAiImageModesSelectable}
                      />
                      <span>
                        <span className="font-medium">OpenAI GPT Image (OPENAI_API_KEY)</span>
                        {geminiAuthStatus?.ai_image_jobs_allowed === false ? (
                          <span className="ml-1 text-xs font-normal text-gray-400">(tạm tắt)</span>
                        ) : null}
                        <span className="mt-0.5 block text-xs text-gray-500">
                          API <code className="text-[11px]">/v1/images/edits</code>, mặc định model{' '}
                          {geminiAuthStatus?.openai_image_model || 'gpt-image-2'} (có thể đổi{' '}
                          <code className="text-[11px]">IMAGE_LOCALIZATION_OPENAI_IMAGE_MODEL</code>).
                        </span>
                      </span>
                    </label>
                  </div>
                  {imageLocalizationGeminiMode === 'web' && (
                    <div className="mt-3 rounded-lg border border-gray-100 bg-gray-50/90 px-3 py-2 space-y-2">
                      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                        Gemini Web — Playwright Chromium
                      </p>
                      <div className="flex flex-wrap gap-4 text-sm">
                        <label className="flex cursor-pointer items-center gap-2">
                          <input
                            type="radio"
                            name="imageLocPlaywrightDisplay"
                            className="mt-0.5"
                            checked={imageLocalizationPlaywrightHeadless}
                            onChange={() => setImageLocalizationPlaywrightHeadless(true)}
                            disabled={localizationStartBusy}
                          />
                          <span>
                            <span className="font-medium text-gray-800">Ẩn trình duyệt</span>
                            <span className="ml-1 text-xs text-gray-500">
                              (headless — kiểu server sau khi cookie/profile ổn)
                            </span>
                          </span>
                        </label>
                        <label className="flex cursor-pointer items-center gap-2">
                          <input
                            type="radio"
                            name="imageLocPlaywrightDisplay"
                            className="mt-0.5"
                            checked={!imageLocalizationPlaywrightHeadless}
                            onChange={() => setImageLocalizationPlaywrightHeadless(false)}
                            disabled={localizationStartBusy}
                          />
                          <span>
                            <span className="font-medium text-gray-800">Hiện cửa sổ</span>
                            <span className="ml-1 text-xs text-gray-500">
                              (headed — màn hình hoặc RDP/VNC để xem/đăng nhập Gemini)
                            </span>
                          </span>
                        </label>
                      </div>
                      {imageLocalizationHeadlessNeedsSavedCookie ? (
                        <div
                          role="alert"
                          className="rounded-md border border-amber-300 bg-amber-50 px-2.5 py-2 text-xs text-amber-950 leading-relaxed"
                        >
                          <span className="font-semibold">Ẩn trình duyệt:</span> backend chưa có cookie Gemini đã lưu và chưa có{' '}
                          <code className="text-[11px]">gemini_logged_in.marker</code> — dán cookie vào ô phía dưới rồi bấm &quot;Lưu cookie
                          Gemini&quot;, hoặc chọn <span className="font-medium">Hiện cửa sổ</span> và đăng nhập một lần để tạo marker. Sau đó mới Chạy
                          ở chế độ ẩn.
                        </div>
                      ) : null}
                      {!imageLocalizationPlaywrightHeadless ? (
                        <p className="rounded-md border border-sky-200 bg-sky-50 px-2.5 py-2 text-xs text-sky-950 leading-relaxed">
                          <span className="font-semibold">Hiện cửa sổ:</span> nếu có Sign in / đăng nhập, hoàn thành đăng nhập trong Chromium — backend
                          sẽ <span className="font-medium">chờ</span> (mặc định ~15 phút qua{' '}
                          <code className="text-[11px]">IMAGE_LOCALIZATION_GEMINI_MANUAL_LOGIN_WAIT_MS</code>) rồi tự tiếp tục. Đã đăng nhập sẵn thì chạy
                          luôn.
                        </p>
                      ) : null}
                      <p className="text-xs text-gray-500 leading-relaxed">
                        Gửi kèm job và ghi đè <code className="text-[11px]">IMAGE_LOCALIZATION_PLAYWRIGHT_HEADLESS</code> cho lần chạy
                        này. Lần đầu mở trang, mặc định lấy theo cấu hình server (.env).
                      </p>
                    </div>
                  )}
                  {imageLocalizationGeminiMode === 'api' && (
                    <div className="mt-3 space-y-3 border-t border-gray-100 pt-3">
                      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Gemini API — model (chữ &amp; bố cục)</p>
                      <label className="block text-sm">
                        <span className="mb-1 block font-medium text-gray-700">Chọn nhanh model</span>
                        <select
                          value={geminiApiModelPresetSelectValue}
                          onChange={(e) => {
                            const id = e.target.value;
                            if (id === 'custom') return;
                            const row = IMAGE_LOC_GEMINI_MODEL_PRESETS.find((x) => x.id === id);
                            setImageLocalizationGeminiApiModel(row?.model ?? '');
                          }}
                          disabled={localizationStartBusy}
                          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                        >
                          {IMAGE_LOC_GEMINI_MODEL_PRESETS.map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.label}
                            </option>
                          ))}
                          <option value="custom">Tùy chỉnh… (ghi ID model trong ô dưới)</option>
                        </select>
                      </label>
                      <label className="block text-sm">
                        <span className="mb-1 block font-medium text-gray-700">
                          Model (ID) — ưu tiên dịch &amp; layout
                        </span>
                        <input
                          type="text"
                          value={imageLocalizationGeminiApiModel}
                          onChange={(e) => setImageLocalizationGeminiApiModel(e.target.value)}
                          disabled={localizationStartBusy}
                          placeholder={geminiAuthStatus?.image_model || 'gemini-3-pro-image-preview'}
                          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono"
                          autoComplete="off"
                        />
                        <span className="mt-1 block text-xs text-gray-500">
                          Để trống = model mặc định trên server (.env). Pro Image thường cho bố cục/chữ ổn định hơn Flash cùng đời.
                        </span>
                      </label>
                      <div className="rounded-lg border border-gray-100 bg-gray-50/80 p-3">
                        <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Đầu ra — chỉ chất lượng / độ nét ảnh</p>
                        <label className="mt-2 block text-sm">
                          <span className="mb-1 block font-medium text-gray-700">Độ phân giải (imageSize)</span>
                          <select
                            value={imageLocalizationGeminiImageSize}
                            onChange={(e) => setImageLocalizationGeminiImageSize(e.target.value)}
                            disabled={localizationStartBusy}
                            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm"
                          >
                            <option value="">Mặc định (.env IMAGE_LOCALIZATION_GEMINI_API_DEFAULT_IMAGE_SIZE)</option>
                            {(geminiAuthStatus?.gemini_api_image_sizes ?? ['2K', '4K']).map((s) => (
                              <option key={s} value={s}>
                                {s}
                              </option>
                            ))}
                          </select>
                          <span className="mt-1 block text-xs text-gray-500">
                            Chỉ 2K và 4K — không còn 512/1K. Luôn tier Standard Gemini (không Flex).
                          </span>
                        </label>
                      </div>
                    </div>
                  )}
                  {imageLocalizationGeminiMode === 'openai' && (
                    <div className="mt-3 space-y-3 border-t border-gray-100 pt-3">
                      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">GPT Image — model (chữ &amp; bố cục)</p>
                      <label className="block text-sm">
                        <span className="mb-1 block font-medium text-gray-700">Chọn nhanh model</span>
                        <select
                          value={openaiImageModelPresetSelectValue}
                          onChange={(e) => {
                            const id = e.target.value;
                            if (id === 'custom') return;
                            const row = IMAGE_LOC_OPENAI_MODEL_PRESETS.find((x) => x.id === id);
                            setImageLocalizationOpenaiModel(row?.model ?? '');
                          }}
                          disabled={localizationStartBusy}
                          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                        >
                          {IMAGE_LOC_OPENAI_MODEL_PRESETS.map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.label}
                            </option>
                          ))}
                          <option value="custom">Tùy chỉnh…</option>
                        </select>
                      </label>
                      <label className="block text-sm">
                        <span className="mb-1 block font-medium text-gray-700">Model (ID)</span>
                        <input
                          type="text"
                          value={imageLocalizationOpenaiModel}
                          onChange={(e) => setImageLocalizationOpenaiModel(e.target.value)}
                          disabled={localizationStartBusy}
                          placeholder={geminiAuthStatus?.openai_image_model || 'gpt-image-2'}
                          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono"
                          autoComplete="off"
                        />
                        <span className="mt-1 block text-xs text-gray-500">Để trống = .env</span>
                      </label>
                      <div className="rounded-lg border border-gray-100 bg-gray-50/80 p-3 space-y-3">
                        <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Đầu ra — chất lượng &amp; kích thước ảnh</p>
                        <label className="block text-sm">
                          <span className="mb-1 block font-medium text-gray-700">Gợi ý combo (có thể sửa lại hai ô dưới)</span>
                          <select
                            value={openaiOutputPresetSelectValue}
                            onChange={(e) => {
                              const id = e.target.value;
                              if (id === '__custom') return;
                              const row = IMAGE_LOC_OPENAI_OUTPUT_PRESETS.find((x) => x.id === id);
                              if (!row) {
                                setImageLocalizationOpenaiQuality('');
                                setImageLocalizationOpenaiSize('');
                                return;
                              }
                              setImageLocalizationOpenaiQuality(row.quality);
                              setImageLocalizationOpenaiSize(row.size);
                            }}
                            disabled={localizationStartBusy}
                            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm"
                          >
                            {IMAGE_LOC_OPENAI_OUTPUT_PRESETS.map((p) => (
                              <option key={p.id || 'none'} value={p.id || ''}>
                                {p.label}
                              </option>
                            ))}
                            <option value="__custom">
                              Tổ hợp tùy chỉnh (chỉnh quality / size bên dưới)
                            </option>
                          </select>
                        </label>
                        <div className="grid gap-3 sm:grid-cols-2">
                          <label className="block text-sm">
                            <span className="mb-1 block font-medium text-gray-700">Chất lượng (quality)</span>
                            <select
                              value={imageLocalizationOpenaiQuality}
                              onChange={(e) => setImageLocalizationOpenaiQuality(e.target.value)}
                              disabled={localizationStartBusy}
                              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm"
                            >
                              <option value="">Theo backend (.env)</option>
                              {(geminiAuthStatus?.openai_image_qualities ?? ['high', 'auto']).map((q) => (
                                <option key={q} value={q}>
                                  {q}
                                </option>
                              ))}
                            </select>
                            <span className="mt-1 block text-xs text-gray-500">Chỉ high hoặc auto — low/medium đã ngừng.</span>
                          </label>
                          <label className="block text-sm">
                            <span className="mb-1 block font-medium text-gray-700">Kích thước (size)</span>
                            <select
                              value={imageLocalizationOpenaiSize}
                              onChange={(e) => setImageLocalizationOpenaiSize(e.target.value)}
                              disabled={localizationStartBusy}
                              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm"
                            >
                              <option value="">
                                GPT Image — mặc định auto hoặc theo ô dưới
                              </option>
                              {(geminiAuthStatus?.openai_image_sizes ?? [
                                'auto',
                                '1024x1792',
                                '1792x1024',
                                '1536x1024',
                                '1024x1536',
                              ]).map((sz) => (
                                <option key={sz} value={sz}>
                                  {sz}
                                </option>
                              ))}
                            </select>
                          </label>
                        </div>
                      </div>
                    </div>
                  )}
                </label>
                <label className="block text-sm">
                  <span className="mb-1 block font-medium text-gray-700">Ngôn ngữ bản địa</span>
                  <select
                    value={imageLocalizationLanguage}
                    onChange={(e) => setImageLocalizationLanguage(e.target.value)}
                    disabled={localizationStartBusy}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                  >
                    <option value="vi">Tiếng Việt</option>
                    <option value="en">English</option>
                    <option value="th">Thai</option>
                    <option value="id">Indonesian</option>
                  </select>
                </label>
                <label className="flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={imageLocalizationSelectedOnly}
                    onChange={(e) => setImageLocalizationSelectedOnly(e.target.checked)}
                    disabled={localizationStartBusy || selectedProductIds.size === 0}
                  />
                  Chỉ chạy {selectedProductIds.size} sản phẩm đang chọn
                </label>
                <label className="flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={imageLocalizationForce}
                    onChange={(e) => setImageLocalizationForce(e.target.checked)}
                    disabled={localizationStartBusy}
                  />
                  Chạy lại cả ảnh đã xử lý
                </label>
                <div className="rounded-lg border border-gray-200 px-3 py-2 text-xs text-gray-600">
                  <div>Pending: {imageLocalizationSummary?.pending ?? '—'}</div>
                  <div>Done: {imageLocalizationSummary?.localized ?? '—'} · Error: {imageLocalizationSummary?.failed ?? '—'}</div>
                </div>
              </div>

              <label className="block text-sm">
                <span className="mb-1 block font-medium text-gray-700">Cookie Gemini</span>
                <textarea
                  value={imageLocalizationCookie}
                  onChange={(e) => setImageLocalizationCookie(e.target.value)}
                  placeholder="Dán Cookie header hoặc JSON cookie export của Gemini..."
                  rows={3}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono"
                />
              </label>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => void handleSaveGeminiCookie()}
                  disabled={imageLocalizationSavingCookie || !imageLocalizationCookie.trim()}
                  className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-60"
                >
                  {imageLocalizationSavingCookie ? 'Đang lưu cookie...' : 'Lưu cookie Gemini'}
                </button>
                <button
                  type="button"
                  onClick={() => void handleStartImageLocalization()}
                  disabled={localizationStartBusy || !imageLocalizationGeminiReady}
                  className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-60"
                >
                  {localizationStartBusy
                    ? 'Đang gửi job…'
                    : localizationPollActive
                      ? 'Chạy thêm job ảnh'
                      : 'Chạy bản địa hóa ảnh'}
                </button>
              </div>
              {localizationPollActive ? (
                <p className="mt-1.5 text-xs leading-snug text-gray-600">
                  Mỗi lần bấm chạy là một job riêng — khung Tiến trình hiển thị <strong>từng card</strong>. Hủy từng job bằng
                  nút trong đúng card đó (không ảnh hưởng job khác).
                </p>
              ) : null}

              {geminiAuthStatus ? (
                <p className="text-xs text-gray-600">
                  Web: {geminiAuthStatus.web?.ready ? 'sẵn sàng' : 'chưa sẵn sàng'}
                  {geminiAuthStatus.web?.cookie_deploy_block_reason ? (
                    <span className="text-red-600"> · {geminiAuthStatus.web.cookie_deploy_block_reason}</span>
                  ) : null}
                  {' · '}cookie {geminiAuthStatus.web?.cookie_count ?? 0}
                  {' · '}Playwright{' '}
                  {typeof geminiAuthStatus.playwright_headless === 'boolean'
                    ? geminiAuthStatus.playwright_headless
                      ? 'ẩn trình duyệt'
                      : 'hiện trình duyệt'
                    : '—'}
                  · profile {geminiAuthStatus.web?.profile_marker ? 'có' : 'không'}
                  {' · '}API Gemini: {geminiAuthStatus.api?.ready ? 'sẵn sàng' : 'chưa sẵn sàng'} (
                  {geminiAuthStatus.image_model}). OpenAI: {geminiAuthStatus.openai?.ready ? 'sẵn sàng' : 'chưa sẵn sàng'}{' '}
                  ({geminiAuthStatus.openai_image_model})
                </p>
              ) : null}
              {imageLocalizationError ? (
                <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                  {imageLocalizationError}
                </div>
              ) : null}
            </div>

            <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm font-semibold text-gray-900">Tiến trình</span>
                <span className="text-xs text-gray-500">
                  {localizationJobsForUi.length
                    ? localizationActiveJobCount > 0
                      ? `${localizationActiveJobCount} đang chạy · ${localizationJobsForUi.length} card`
                      : `${localizationJobsForUi.length} job (đã dừng)`
                    : localizationPollActive
                      ? 'đang tải…'
                      : 'idle'}
                </span>
              </div>

              {localizationJobsForUi.length === 0 ? (
                <p className="mt-3 text-sm text-gray-600">Chưa có job đang theo dõi trên tab này.</p>
              ) : (
                <div className="mt-3 max-h-[min(70vh,520px)] space-y-3 overflow-auto pr-0.5">
                  {localizationJobsForUi.map((job) => (
                    <div
                      key={job.job_id}
                      className={`rounded-lg border bg-white p-2.5 shadow-sm ${
                        job.status === 'error'
                          ? 'border-red-200'
                          : job.status === 'cancelled'
                            ? 'border-gray-300'
                            : job.status === 'done'
                              ? 'border-emerald-200'
                              : 'border-violet-200'
                      }`}
                    >
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <p className="truncate font-mono text-[11px] text-gray-500" title={job.job_id}>
                            {job.job_id}
                          </p>
                          <p className="text-xs font-semibold capitalize text-gray-800">{job.status}</p>
                        </div>
                      </div>

                      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-gray-200">
                        {job.percent != null ? (
                          <div
                            className="h-full rounded-full bg-violet-600 transition-[width] duration-300"
                            style={{ width: `${Math.min(100, job.percent)}%` }}
                          />
                        ) : (
                          <div className="h-full w-full rounded-full bg-violet-400/50" />
                        )}
                      </div>

                      <p className="mt-2 whitespace-pre-wrap text-xs text-gray-700">{job.message || '—'}</p>

                      {job.status === 'running' && job.current_product_id ? (
                        <p className="mt-2 rounded border border-violet-100 bg-violet-50/90 px-2 py-1.5 text-xs text-violet-950">
                          <span className="font-semibold">Đang xử lý:</span>{' '}
                          <code className="font-mono text-[11px]">{job.current_product_id}</code>
                        </p>
                      ) : null}

                      {job.job_queue_product_ids?.length ? (
                        <details className="mt-2 rounded border border-gray-100 text-[11px] text-gray-700">
                          <summary className="cursor-pointer select-none px-2 py-1 font-medium text-gray-800 hover:bg-gray-50">
                            Danh sách SP ({job.job_queue_product_ids.length}
                            {job.job_queue_truncated
                              ? ` / ${job.total ?? '?'} — chỉ hiện tối đa ${job.job_queue_product_ids.length} id đầu`
                              : ''}
                            )
                          </summary>
                          <div className="max-h-28 overflow-auto border-t border-gray-50 px-2 py-1 font-mono text-[10px] leading-relaxed text-gray-600">
                            {job.job_queue_product_ids.join(', ')}
                          </div>
                        </details>
                      ) : null}

                      {job.skipped_product_reports?.length ? (
                        <div className="mt-2 rounded border border-amber-100 bg-amber-50/90 px-2 py-1.5">
                          <p className="text-[11px] font-semibold text-amber-950">
                            Đã bỏ qua ({job.skipped_product_reports.length})
                          </p>
                          <ul className="mt-1 max-h-28 space-y-1 overflow-auto text-[11px] text-amber-950">
                            {job.skipped_product_reports.map((s, i) => (
                              <li key={`${s.product_id}-${i}`} className="border-b border-amber-100/80 pb-1 last:border-0">
                                <span className="font-mono font-medium">{s.product_id}</span>
                                {s.message ? (
                                  <span className="block whitespace-pre-wrap text-[10px] text-amber-900/90">{s.message}</span>
                                ) : null}
                              </li>
                            ))}
                          </ul>
                        </div>
                      ) : job.skipped ? (
                        <p className="mt-2 text-[11px] text-gray-500">
                          Đã bỏ qua {job.skipped} SP — chi tiết có thể chưa được backend trả về.
                        </p>
                      ) : null}

                      {job.gemini_mode === 'web' &&
                      !job.local_image_only &&
                      typeof job.playwright_headless_effective === 'boolean' ? (
                        <p className="mt-1 text-[11px] text-gray-500">
                          Playwright:{' '}
                          <span className="font-medium text-gray-700">
                            {job.playwright_headless_effective ? 'ẩn trình duyệt' : 'hiện cửa sổ'}
                          </span>
                          {job.playwright_headless_requested == null ? (
                            <span> (mặc định server / .env)</span>
                          ) : null}
                        </p>
                      ) : null}

                      {job.total != null ? (
                        <p className="mt-1 text-[11px] text-gray-500">
                          {job.current ?? 0}/{job.total} · xong {job.done ?? 0} · lỗi {job.failed ?? 0} · bỏ qua{' '}
                          {job.skipped ?? 0}
                        </p>
                      ) : null}

                      {job.recent_results?.length ? (
                        <div className="mt-2 max-h-32 space-y-1 overflow-auto rounded border border-gray-100 bg-gray-50/80 p-1.5 text-[11px] text-gray-600">
                          {job.recent_results.slice(-8).map((r) => (
                            <div key={`${r.product_id}-${r.status}-${r.message || ''}`} className="flex gap-2">
                              <span className="font-mono text-gray-800">{r.product_id}</span>
                              <span>{r.status}</span>
                              {r.message ? <span className="truncate text-gray-500">{r.message}</span> : null}
                            </div>
                          ))}
                        </div>
                      ) : null}

                      {(job.status === 'running' || job.status === 'queued') && job.job_id ? (
                        <div className="mt-3 flex flex-wrap items-center justify-end gap-2 border-t border-gray-100 pt-3">
                          <button
                            type="button"
                            onClick={() => void handleCancelImageLocalization(job.job_id)}
                            className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-xs font-medium text-gray-800 shadow-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-gray-400 focus:ring-offset-1"
                            aria-label={`Hủy job ${job.job_id} sau ảnh đang xử lý`}
                          >
                            Hủy job này sau ảnh hiện tại
                          </button>
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}
            </div>
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
                  <div className="border-b border-gray-100 bg-slate-50/90 px-4 py-2 text-xs text-slate-600">
                    <span className="font-medium text-slate-800">↔ Cuộn ngang</span> để xem đủ cột ·{' '}
                    <span className="font-medium text-slate-800">Bấm ô</span> để sửa nhanh · Enter lưu · Esc hủy ·
                    cột ảnh: JSON trong ô (cuộn trong ô) · bấm để sửa · Ctrl+Enter lưu
                  </div>
                  <div className="overflow-x-auto overscroll-x-contain max-w-full">
                    <table className="w-max min-w-full text-sm border-separate border-spacing-0">
                      <thead>
                        <tr className="border-b border-gray-200">
                          <th className="sticky left-0 z-30 min-w-[2.75rem] bg-gray-50 py-3 px-3 text-left font-semibold text-gray-700 shadow-[2px_0_6px_-2px_rgba(0,0,0,0.06)]">
                            <input
                              type="checkbox"
                              checked={allSelectedOnPage}
                              onChange={toggleSelectAllOnPage}
                              aria-label="Chọn tất cả sản phẩm trong trang"
                            />
                          </th>
                          <th className="sticky left-[2.75rem] z-30 min-w-[9.5rem] bg-gray-50 py-3 px-3 text-left font-semibold text-gray-700 shadow-[4px_0_8px_-4px_rgba(0,0,0,0.08)]">
                            ID
                          </th>
                          <th className="min-w-[5.5rem] whitespace-nowrap bg-gray-50 py-3 px-2 text-left font-semibold text-gray-700">
                            Web
                          </th>
                          <th className="min-w-[14rem] whitespace-nowrap bg-gray-50 py-3 px-2 text-left font-semibold text-gray-700">
                            Ảnh đại diện
                          </th>
                          <th className="min-w-[14rem] whitespace-nowrap bg-gray-50 py-3 px-2 text-left font-semibold text-gray-700">
                            Thư viện ảnh
                          </th>
                          <th className="min-w-[14rem] whitespace-nowrap bg-gray-50 py-3 px-2 text-left font-semibold text-gray-700">
                            Ảnh chi tiết SP
                          </th>
                          <th className="min-w-[7rem] whitespace-nowrap bg-gray-50 py-3 px-3 text-left font-semibold text-gray-700">
                            Mã SKU
                          </th>
                          <th className="min-w-[10rem] whitespace-nowrap bg-gray-50 py-3 px-3 text-left font-semibold text-gray-700">
                            Slug
                          </th>
                          <th className="min-w-[16rem] bg-gray-50 py-3 px-3 text-left font-semibold text-gray-700">
                            Tên
                          </th>
                          <th className="min-w-[6.5rem] whitespace-nowrap bg-gray-50 py-3 px-3 text-left font-semibold text-gray-700">
                            Giá
                          </th>
                          <th className="min-w-[8rem] whitespace-nowrap bg-gray-50 py-3 px-3 text-left font-semibold text-gray-700">
                            Thương hiệu
                          </th>
                          <th className="min-w-[4.5rem] whitespace-nowrap bg-gray-50 py-3 px-3 text-left font-semibold text-gray-700">
                            Tồn
                          </th>
                          <th className="min-w-[5.5rem] whitespace-nowrap bg-gray-50 py-3 px-3 text-left font-semibold text-gray-700">
                            Trạng thái
                          </th>
                          <th className="min-w-[6rem] whitespace-nowrap bg-gray-50 py-3 px-3 text-left font-semibold text-gray-700">
                            Nguồn 1688
                          </th>
                          <th className="min-w-[5.5rem] whitespace-nowrap bg-gray-50 py-3 px-3 text-left font-semibold text-gray-700">
                            Ảnh i18n
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.products.map((p) => {
                          const webUrl = adminProductPublicUrl(p.slug);
                          const formatCell = (v: string | number | null | undefined) => {
                            if (v == null || v === '') return '—';
                            if (typeof v === 'string' && v.toLowerCase() === 'nan') return '—';
                            return String(v);
                          };
                          const onEditChange = (v: string) =>
                            setEditing((x) => (x ? { ...x, value: v } : null));
                          const stickyTd =
                            'sticky z-10 bg-white py-2 px-3 align-top group-hover:bg-gray-50/80';
                          return (
                            <tr
                              key={p.id}
                              className="group border-b border-gray-100 hover:bg-gray-50/50"
                            >
                              <td className={`${stickyTd} left-0 shadow-[2px_0_6px_-2px_rgba(0,0,0,0.06)]`}>
                                <input
                                  type="checkbox"
                                  checked={selectedProductIds.has(p.product_id)}
                                  onChange={() => toggleSelectOne(p.product_id)}
                                  aria-label={`Chọn sản phẩm ${p.product_id}`}
                                />
                              </td>
                              <td
                                className={`${stickyTd} left-[2.75rem] shadow-[4px_0_8px_-4px_rgba(0,0,0,0.08)]`}
                              >
                                {editing?.productId === p.product_id &&
                                editing?.field === 'product_id' ? (
                                  <input
                                    autoFocus
                                    disabled={saving}
                                    value={editing.value}
                                    onChange={(e) => onEditChange(e.target.value)}
                                    onBlur={saveEdit}
                                    onKeyDown={handleKeyDown}
                                    className="w-full min-w-[8rem] rounded border border-gray-300 px-2 py-1 font-mono text-xs"
                                  />
                                ) : (
                                  <span
                                    role="button"
                                    tabIndex={0}
                                    className="cursor-pointer font-mono text-xs text-blue-600 hover:underline"
                                    onMouseDown={(e) => {
                                      e.preventDefault();
                                      openInlineEdit(p.product_id, 'product_id', p.product_id ?? '');
                                    }}
                                    onKeyDown={(e) => {
                                      if (e.key === 'Enter' || e.key === ' ') {
                                        e.preventDefault();
                                        openInlineEdit(p.product_id, 'product_id', p.product_id ?? '');
                                      }
                                    }}
                                    title="Bấm để sửa ID"
                                  >
                                    {p.product_id || String(p.id)}
                                  </span>
                                )}
                              </td>
                              <td className="whitespace-nowrap py-2 px-2 align-middle">
                                {webUrl ? (
                                  <a
                                    href={webUrl}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="inline-flex items-center gap-1 rounded-md border border-slate-300 bg-white px-2 py-1 text-[11px] font-medium text-slate-700 shadow-sm hover:border-slate-400 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-orange-500 focus-visible:ring-offset-1"
                                    title="Mở trang sản phẩm trên web (tab mới)"
                                  >
                                    <svg
                                      className="h-3.5 w-3.5 shrink-0 opacity-70"
                                      fill="none"
                                      stroke="currentColor"
                                      viewBox="0 0 24 24"
                                      aria-hidden
                                    >
                                      <path
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                        strokeWidth={2}
                                        d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                                      />
                                    </svg>
                                    Xem web
                                  </a>
                                ) : (
                                  <span
                                    className="inline-flex items-center rounded-md border border-dashed border-gray-200 bg-gray-50 px-2 py-1 text-[11px] text-gray-400"
                                    title="Chưa có slug"
                                  >
                                    —
                                  </span>
                                )}
                              </td>
                              <td className="py-2 px-2 align-top">
                                <AdminProductJsonFieldCell
                                  productId={p.product_id}
                                  field="main_image"
                                  raw={p.main_image}
                                  editing={editing}
                                  saving={saving}
                                  onStart={openInlineEdit}
                                  onEditChange={onEditChange}
                                  onSave={saveEdit}
                                  onCancel={cancelEdit}
                                  editMode="string"
                                />
                              </td>
                              <td className="py-2 px-2 align-top">
                                <AdminProductJsonFieldCell
                                  productId={p.product_id}
                                  field="images"
                                  raw={p.images}
                                  editing={editing}
                                  saving={saving}
                                  onStart={openInlineEdit}
                                  onEditChange={onEditChange}
                                  onSave={saveEdit}
                                  onCancel={cancelEdit}
                                  editMode="array"
                                />
                              </td>
                              <td className="py-2 px-2 align-top">
                                <AdminProductJsonFieldCell
                                  productId={p.product_id}
                                  field="gallery"
                                  raw={p.gallery}
                                  editing={editing}
                                  saving={saving}
                                  onStart={openInlineEdit}
                                  onEditChange={onEditChange}
                                  onSave={saveEdit}
                                  onCancel={cancelEdit}
                                  editMode="array"
                                />
                              </td>
                              <td className="whitespace-nowrap py-2 px-3 align-top">
                                <AdminProductEditableCell
                                  productId={p.product_id}
                                  field="code"
                                  value={p.code ?? ''}
                                  display={formatCell(p.code)}
                                  editing={editing}
                                  saving={saving}
                                  onStart={openInlineEdit}
                                  onEditChange={onEditChange}
                                  onSave={saveEdit}
                                  onKeyDown={handleKeyDown}
                                  inputClassName="w-full min-w-[6rem] rounded border border-gray-300 px-2 py-1 font-mono text-xs"
                                />
                              </td>
                              <td className="max-w-[14rem] py-2 px-3 align-top">
                                <AdminProductEditableCell
                                  productId={p.product_id}
                                  field="slug"
                                  value={p.slug ?? ''}
                                  display={
                                    <span className="block truncate font-mono text-xs">
                                      {formatCell(p.slug)}
                                    </span>
                                  }
                                  editing={editing}
                                  saving={saving}
                                  onStart={openInlineEdit}
                                  onEditChange={onEditChange}
                                  onSave={saveEdit}
                                  onKeyDown={handleKeyDown}
                                  inputClassName="w-full min-w-[9rem] rounded border border-gray-300 px-2 py-1 font-mono text-xs"
                                />
                              </td>
                              <td className="min-w-[16rem] max-w-[22rem] py-2 px-3 align-top">
                                <AdminProductEditableCell
                                  productId={p.product_id}
                                  field="name"
                                  value={p.name ?? ''}
                                  display={<span className="whitespace-normal">{p.name || '—'}</span>}
                                  editing={editing}
                                  saving={saving}
                                  onStart={openInlineEdit}
                                  onEditChange={onEditChange}
                                  onSave={saveEdit}
                                  onKeyDown={handleKeyDown}
                                  inputClassName="w-full min-w-[14rem] rounded border border-gray-300 px-2 py-1"
                                />
                              </td>
                              <td className="whitespace-nowrap py-2 px-3 align-top tabular-nums">
                                <AdminProductEditableCell
                                  productId={p.product_id}
                                  field="price"
                                  value={p.price ?? 0}
                                  display={
                                    typeof p.price === 'number'
                                      ? new Intl.NumberFormat('vi-VN').format(p.price)
                                      : formatCell(p.price)
                                  }
                                  editing={editing}
                                  saving={saving}
                                  onStart={openInlineEdit}
                                  onEditChange={onEditChange}
                                  onSave={saveEdit}
                                  onKeyDown={handleKeyDown}
                                  inputType="number"
                                />
                              </td>
                              <td className="whitespace-nowrap py-2 px-3 align-top">
                                <AdminProductEditableCell
                                  productId={p.product_id}
                                  field="brand_name"
                                  value={p.brand_name ?? ''}
                                  display={formatCell(p.brand_name)}
                                  editing={editing}
                                  saving={saving}
                                  onStart={openInlineEdit}
                                  onEditChange={onEditChange}
                                  onSave={saveEdit}
                                  onKeyDown={handleKeyDown}
                                />
                              </td>
                              <td className="whitespace-nowrap py-2 px-3 align-top tabular-nums">
                                <AdminProductEditableCell
                                  productId={p.product_id}
                                  field="available"
                                  value={p.available ?? 0}
                                  display={formatCell(p.available)}
                                  editing={editing}
                                  saving={saving}
                                  onStart={openInlineEdit}
                                  onEditChange={onEditChange}
                                  onSave={saveEdit}
                                  onKeyDown={handleKeyDown}
                                  inputType="number"
                                  inputClassName="w-20 rounded border border-gray-300 px-2 py-1"
                                />
                              </td>
                              <td className="whitespace-nowrap py-2 px-3 align-top">
                                <button
                                  type="button"
                                  disabled={saving}
                                  onClick={() => void toggleProductActive(p)}
                                  className={`rounded-md border px-2 py-1 text-xs font-medium transition-colors disabled:opacity-50 ${
                                    p.is_active !== false
                                      ? 'border-green-200 bg-green-50 text-green-700 hover:bg-green-100'
                                      : 'border-gray-200 bg-gray-50 text-gray-500 hover:bg-gray-100'
                                  }`}
                                  title="Bấm để bật/tắt hiển thị trên shop"
                                >
                                  {p.is_active !== false ? 'Hiển thị' : 'Ẩn'}
                                </button>
                              </td>
                              <td className="whitespace-nowrap py-2 px-3 align-top text-xs text-gray-600">
                                {p.source_stock_status || '—'}
                              </td>
                              <td className="whitespace-nowrap py-2 px-3 align-top">
                                <button
                                  type="button"
                                  className={`inline text-left text-xs font-medium underline-offset-2 hover:underline ${
                                    p.image_localization_status === 'localized'
                                      ? 'text-violet-700'
                                      : p.image_localization_status === 'failed'
                                        ? 'text-red-600'
                                        : 'text-gray-500'
                                  }`}
                                  title={
                                    (p.image_localization_error
                                      ? `${p.image_localization_error}\n`
                                      : '') + 'Bấm để xem báo cáo chi tiết từng ảnh'
                                  }
                                  onClick={() => void openImageLocReport(p.product_id)}
                                >
                                  {p.image_localization_status || 'pending'}
                                </button>
                              </td>
                            </tr>
                          );
                        })}
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

        {imageLocReportOpen && (
          <div
            className="fixed inset-0 z-[200] flex items-center justify-center bg-black/45 p-4"
            role="dialog"
            aria-modal="true"
            aria-labelledby="img-loc-report-title"
            onClick={() => setImageLocReportOpen(false)}
          >
            <div
              className="bg-white rounded-lg shadow-xl max-w-5xl w-full max-h-[90vh] flex flex-col overflow-hidden"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3 gap-2">
                <h2 id="img-loc-report-title" className="text-lg font-semibold text-gray-900 truncate">
                  Báo cáo bản địa hóa ảnh — {imageLocReportProductId}
                </h2>
                <button
                  type="button"
                  className="shrink-0 rounded px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-100 border border-gray-200"
                  onClick={() => setImageLocReportOpen(false)}
                >
                  Đóng (Esc)
                </button>
              </div>
              <div className="overflow-y-auto flex-1 p-4 text-sm">
                {imageLocReportLoading && (
                  <p className="text-gray-600 py-6 text-center">Đang tải báo cáo…</p>
                )}
                {imageLocReportError && (
                  <div className="rounded-lg border border-red-200 bg-red-50 text-red-800 px-4 py-3">
                    {imageLocReportError}
                  </div>
                )}
                {!imageLocReportLoading && imageLocReportData && (
                  <>
                    <div className="mb-4 flex flex-wrap gap-3 text-xs sm:text-sm text-gray-700">
                      <span>
                        <span className="text-gray-500">Trạng thái DB: </span>
                        <strong>{imageLocReportData.db_status || '—'}</strong>
                      </span>
                      {imageLocReportData.report_processed_at && (
                        <span>
                          <span className="text-gray-500">Lúc chạy: </span>
                          {imageLocReportData.report_processed_at}
                        </span>
                      )}
                      {imageLocReportData.report_language && (
                        <span>
                          <span className="text-gray-500">Ngôn ngữ: </span>
                          {imageLocReportData.report_language}
                        </span>
                      )}
                    </div>
                    {imageLocReportData.db_error && (
                      <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 text-amber-900 px-3 py-2 text-xs">
                        Lỗi lưu DB: {imageLocReportData.db_error}
                      </div>
                    )}
                    {!imageLocReportData.has_report && (
                      <p className="text-gray-600 border border-gray-100 rounded-lg p-4 bg-gray-50">
                        Chưa có file báo cáo chi tiết trong{' '}
                        <code className="text-xs bg-gray-200 px-1 rounded">product_info.image_localization</code>.
                        Chạy job bản địa hóa ảnh ít nhất một lần (và commit DB) để lưu từng URL và trạng thái.
                      </p>
                    )}
                    {imageLocReportData.has_report && (
                      <>
                        <div className="mb-4 flex flex-wrap gap-2">
                          {(
                            [
                              ['total', 'Tổng'],
                              ['deleted', 'Đã xóa'],
                              ['error', 'Lỗi'],
                              ['ai_image', 'AI ảnh'],
                              ['local_draw', 'Vẽ local'],
                              ['local_pipeline', 'Cắt/ghép'],
                              ['processed_other', 'Xử lý khác'],
                              ['kept_cdn', 'Giữ (CDN)'],
                              ['kept_other', 'Giữ khác'],
                              ['unknown', 'Không rõ'],
                            ] as const
                          ).map(([key, label]) => {
                            const v = imageLocReportData.summary[key];
                            if (key !== 'total' && v === 0) return null;
                            return (
                              <span
                                key={key}
                                className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-800"
                              >
                                {label}: {v}
                              </span>
                            );
                          })}
                        </div>
                        <div className="overflow-x-auto rounded border border-gray-200">
                          <table className="min-w-full text-left text-xs">
                            <thead className="bg-gray-50 text-gray-600">
                              <tr>
                                <th className="py-2 px-2 font-medium">Vị trí</th>
                                <th className="py-2 px-2 font-medium">Loại</th>
                                <th className="py-2 px-2 font-medium">Trạng thái</th>
                                <th className="py-2 px-2 font-medium">Ảnh gốc</th>
                                <th className="py-2 px-2 font-medium">Sau xử lý</th>
                                <th className="py-2 px-2 font-medium">Ghi chú / lý do</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100">
                              {imageLocReportData.items.map((row, idx) => (
                                <tr key={`${row.original_url}-${idx}`} className="align-top">
                                  <td className="py-2 px-2 whitespace-nowrap">
                                    {row.bucket ?? '—'}
                                    {row.index !== null && row.index !== undefined ? `[${row.index}]` : ''}
                                  </td>
                                  <td className="py-2 px-2 text-gray-800 max-w-[10rem]">{row.label_vi}</td>
                                  <td className="py-2 px-2 font-mono text-[10px]">{row.status}</td>
                                  <td className="py-2 px-2 align-top text-blue-700">
                                    <ImageLocReportUrlCell url={row.original_url} textClassName="text-blue-700" />
                                  </td>
                                  <td className="py-2 px-2 align-top">
                                    {row.final_url ? (
                                      <ImageLocReportUrlCell url={row.final_url} textClassName="text-violet-700" />
                                    ) : (
                                      <span className="text-gray-400">—</span>
                                    )}
                                  </td>
                                  <td className="py-2 px-2 text-gray-700 max-w-xl">
                                    <div>{row.message || '—'}</div>
                                    {row.detail &&
                                      Array.isArray((row.detail as { split_parts?: unknown }).split_parts) &&
                                      (row.detail as { split_parts: { method?: string; message?: string }[] })
                                        .split_parts.length > 0 && (
                                        <ul className="mt-1 list-disc pl-4 text-gray-600 text-[11px] space-y-0.5">
                                          {(
                                            row.detail as {
                                              split_parts: {
                                                part_index?: number;
                                                total_parts?: number;
                                                method?: string;
                                                message?: string;
                                              }[];
                                            }
                                          ).split_parts
                                            .slice()
                                            .sort((a, b) => (a.part_index ?? 0) - (b.part_index ?? 0))
                                            .map((p, j) => (
                                              <li key={j}>
                                                <span className="font-medium text-gray-700">
                                                  Phần {(p.part_index ?? 0) + 1}/{p.total_parts ?? '?'}:
                                                </span>{' '}
                                                {p.method === 'ai_image'
                                                  ? 'AI ảnh (Gemini/GPT)'
                                                  : p.method === 'local_draw'
                                                    ? 'OCR + DeepSeek + vẽ local'
                                                    : p.method === 'kept'
                                                      ? 'Giữ nguyên'
                                                      : p.method ?? '—'}
                                                {p.message ? (
                                                  <span className="text-gray-500"> — {p.message}</span>
                                                ) : null}
                                              </li>
                                            ))}
                                        </ul>
                                      )}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>
        )}

        {toast && (
          <div
            role={toast.type === 'err' ? 'alert' : 'status'}
            aria-live={toast.type === 'err' ? 'assertive' : 'polite'}
            className={`fixed bottom-4 right-4 max-w-md px-4 py-2 rounded-lg shadow-lg text-white text-sm ${
              toast.type === 'ok' ? 'bg-green-600' : 'bg-red-600'
            }`}
          >
            {toast.msg}
          </div>
        )}
      </div>
  );
}
