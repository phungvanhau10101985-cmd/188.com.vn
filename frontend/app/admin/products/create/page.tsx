'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  adminBunnyCdnAPI,
  manualProductCreateAPI,
  type ManualProductCreateMode,
  type ManualProductJob,
  type ManualProductJobCreatePayload,
  type ManualProductRefPoolItem,
  type ManualProductJobSummary,
} from '@/lib/admin-api';
import { useToast } from '@/components/ToastProvider';

const STEPS_MANUAL = ['Chế độ', 'Thuộc tính', 'Ảnh', 'Đăng'] as const;
const STEPS_AI = ['Chế độ', 'Thuộc tính', 'Cài đặt Studio', 'Studio ảnh'] as const;

type ColorRow = { key: string; name: string; img: string };

function newColorRow(partial?: Partial<ColorRow>): ColorRow {
  return {
    key: partial?.key || `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    name: partial?.name || '',
    img: partial?.img || '',
  };
}

function Thumb({ url, onRemove }: { url: string; onRemove?: () => void }) {
  return (
    <div className="relative w-24 h-24 rounded-lg overflow-hidden border border-slate-200 bg-slate-50 shrink-0">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={url} alt="" className="w-full h-full object-cover" />
      {onRemove ? (
        <button
          type="button"
          onClick={onRemove}
          className="absolute top-1 right-1 bg-black/60 text-white text-xs px-1.5 py-0.5 rounded"
          aria-label="Xóa ảnh"
        >
          ×
        </button>
      ) : null}
    </div>
  );
}

const REF_PICKER_MAX = 3;

type StudioImageModel = 'pro' | 'flash' | 'flash3';
type StudioAspectRatio = '1:1' | '3:4' | '4:3' | '9:16' | '16:9';

const STUDIO_IMAGE_MODEL_KEY = '188-admin-manual-product-image-model';
const STUDIO_ASPECT_RATIO_KEY = '188-admin-manual-product-aspect-ratio';
const CREATE_DRAFT_KEY = '188-admin-product-create-draft-v1';

type ProductCreateDraft = {
  v: 1;
  savedAt: string;
  step: number;
  mode: ManualProductCreateMode;
  jobId: string | null;
  gender: string;
  productName: string;
  material: string;
  noSize: boolean;
  sizes: string[];
  colorRows: ColorRow[];
  formKind: 'color' | 'gallery' | 'detail' | 'material';
  formColorName: string;
  formPrompt: string;
  formRefUrls: string[];
  formAttachUrl: string;
  price: string;
  available: string;
  notes: string;
  mainImage: string;
  galleryImages: string[];
  detailImages: string[];
  refImages: string[];
  modelPresence: 'none' | 'model';
  modelGender: '' | 'female' | 'male';
  modelAgeGroup: '' | 'baby' | 'child' | 'teen' | 'adult' | 'middle_aged';
  modelEthnicity: '' | 'asian' | 'western';
  shotStyle: 'studio' | 'lifestyle' | 'outdoor';
};

function loadProductCreateDraft(): ProductCreateDraft | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(CREATE_DRAFT_KEY);
    if (!raw) return null;
    const d = JSON.parse(raw) as ProductCreateDraft;
    if (d?.v !== 1) return null;
    return d;
  } catch {
    return null;
  }
}

function saveProductCreateDraft(draft: ProductCreateDraft) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(CREATE_DRAFT_KEY, JSON.stringify({ ...draft, savedAt: new Date().toISOString() }));
  } catch {
    /* quota */
  }
}

function clearProductCreateDraft() {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(CREATE_DRAFT_KEY);
}

function resolveResumeStep(
  mode: ManualProductCreateMode,
  job: ManualProductJob | null,
  fallback: number,
): number {
  if (!job || job.status === 'done') return fallback;
  const jobMode = (job.mode || job.payload?.mode || mode) as ManualProductCreateMode;
  if (jobMode === 'ai') {
    if (
      [
        'awaiting_input',
        'awaiting_approval',
        'ready_to_publish',
        'awaiting_colors',
        'generating',
        'queued',
        'publishing',
        'failed',
      ].includes(job.status)
    ) {
      return 3;
    }
  } else if (job.status !== 'done') {
    return 3;
  }
  return fallback;
}

function colorRowsFromPayload(
  payload: Partial<ManualProductJobCreatePayload> | null | undefined,
): ColorRow[] {
  const raw = payload?.colors;
  if (!Array.isArray(raw) || raw.length === 0) return [newColorRow()];
  return raw.map((c, i) => {
    if (typeof c === 'string') return newColorRow({ name: c, key: `res-${i}` });
    if (c && typeof c === 'object') {
      const row = c as { name?: string; img?: string };
      return newColorRow({ name: row.name || '', img: row.img || '', key: `res-${i}` });
    }
    return newColorRow({ key: `res-${i}` });
  });
}

function applyJobPayloadToDraft(job: ManualProductJob, draft: ProductCreateDraft): ProductCreateDraft {
  const p: Partial<ManualProductJobCreatePayload> = job.payload || {};
  return {
    ...draft,
    mode: (p.mode as ManualProductCreateMode) || draft.mode,
    jobId: job.job_id,
    productName: (p.product_name || job.vision_product_name || draft.productName || '').trim(),
    material: (p.material || draft.material || '').trim(),
    gender: (p.gender || draft.gender || 'Nữ').trim(),
    price: p.price != null ? String(p.price) : draft.price,
    available: p.available != null ? String(p.available) : draft.available,
    notes: (p.notes || draft.notes || '').trim(),
    noSize: Boolean(p.no_size),
    sizes: Array.isArray(p.sizes) ? p.sizes.map(String) : draft.sizes,
    colorRows: colorRowsFromPayload(p),
    mainImage: (p.main_image || draft.mainImage || '').trim(),
    galleryImages: Array.isArray(p.images) ? p.images.map(String) : draft.galleryImages,
    detailImages: Array.isArray(p.gallery) ? p.gallery.map(String) : draft.detailImages,
    refImages: Array.isArray(p.ref_image_urls) ? p.ref_image_urls.map(String) : draft.refImages,
    modelPresence: p.model_presence === 'model' ? 'model' : draft.modelPresence,
    modelGender:
      p.model_gender === 'female' || p.model_gender === 'male'
        ? p.model_gender
        : draft.modelGender,
    modelAgeGroup:
      p.model_age_group === 'baby' ||
      p.model_age_group === 'child' ||
      p.model_age_group === 'teen' ||
      p.model_age_group === 'adult' ||
      p.model_age_group === 'middle_aged'
        ? p.model_age_group
        : draft.modelAgeGroup,
    modelEthnicity:
      p.model_ethnicity === 'asian' || p.model_ethnicity === 'western'
        ? p.model_ethnicity
        : draft.modelEthnicity,
    shotStyle:
      p.shot_style === 'lifestyle' || p.shot_style === 'outdoor'
        ? p.shot_style
        : draft.shotStyle,
    step: resolveResumeStep((p.mode as ManualProductCreateMode) || draft.mode, job, draft.step),
  };
}

function syncStudioFormFromJob(job: ManualProductJob) {
  const phaseRaw = job.studio?.phase || 'color';
  const phase = phaseRaw === 'main' ? 'gallery' : phaseRaw;
  const pool = job.studio?.ref_pool || [];
  const slot = job.studio?.current_slot;
  const approvedColorCount = (job.studio?.colors || []).filter((c) =>
    (c?.img || '').trim(),
  ).length;
  // Đang duyệt slot màu → index của slot; đang chờ tạo màu mới → index màu tiếp theo
  const colorIdx =
    job.status === 'awaiting_approval' && slot?.kind === 'color'
      ? colorSlotIndex(job.studio, slot)
      : approvedColorCount;
  const formKindResolved: 'color' | 'gallery' | 'detail' | 'material' =
    phase === 'gallery' || phase === 'detail' || phase === 'material'
      ? phase
      : phase === 'main'
        ? 'gallery'
        : 'color';
  // Chỉ giữ tên màu khi đang duyệt ảnh vừa tạo của đúng slot đó.
  // Không lấy vision_colors[0] (tên màu #1) — màu #2+ phải upload ảnh mới rồi AI mới đọc.
  const formColorName =
    job.status === 'awaiting_approval' && slot?.kind === 'color'
      ? String(slot?.name || '').trim()
      : '';
  return {
    formKind: formKindResolved,
    formRefUrls:
      job.status === 'awaiting_approval' && slot
        ? syncRefUrlsFromJob(job)
        : studioDefaultRefUrls(pool, formKindResolved, colorIdx),
    formColorName,
    formPrompt: (slot?.user_prompt || '').trim(),
    formAttachUrl: (slot?.attach_url || '').trim(),
  };
}

function studioDefaultRefUrls(
  pool: ManualProductRefPoolItem[],
  kind: 'color' | 'gallery' | 'detail' | 'material',
  colorIndex = 0,
): string[] {
  if (kind === 'color') {
    return [];
  }
  // Gallery / chi tiết / chất liệu: ưu tiên ảnh màu đã tạo làm ref
  const approved = pool
    .filter(
      (p) =>
        p.kind === 'ref' ||
        p.kind === 'color' ||
        p.kind === 'gallery' ||
        p.kind === 'detail' ||
        p.kind === 'material',
    )
    .map((p) => p.url)
    .filter(Boolean) as string[];
  return approved.slice(0, REF_PICKER_MAX);
}

function firstApprovedColorRow(studio: ManualProductJob['studio']): { url: string; name: string } {
  for (const row of studio?.colors || []) {
    const u = (row?.img || '').trim();
    if (u) return { url: u, name: (row?.name || '').trim() || 'Màu #1' };
  }
  const fromPool = (studio?.ref_pool || []).find((p) => p.kind === 'color' && p.url);
  if (fromPool?.url) {
    const lbl = (fromPool.label || '').trim();
    return { url: fromPool.url, name: lbl || 'Màu #1' };
  }
  return { url: '', name: '' };
}

function firstApprovedColorUrl(studio: ManualProductJob['studio']): string {
  return firstApprovedColorRow(studio).url;
}

function colorSlotIndex(studio: ManualProductJob['studio'], slot?: { index?: number | null } | null): number {
  return Math.max(0, Number(slot?.index ?? 0) || 0);
}

/** Chỉ giữ URL có trong pool; màu #2+ luôn giữ ảnh màu #1 (khuôn mặt). */
function sanitizeFormRefUrls(
  urls: string[],
  pool: ManualProductRefPoolItem[],
  kind: 'color' | 'gallery' | 'detail' | 'material',
  colorIndex = 0,
  studio?: ManualProductJob['studio'],
): string[] {
  const poolSet = new Set(pool.map((p) => p.url).filter(Boolean));
  const filtered = urls.filter((u) => poolSet.has(u));
  if (kind === 'color' && colorIndex >= 1) {
    const face = firstApprovedColorUrl(studio || null);
    return filtered.filter((u) => u !== face).slice(0, REF_PICKER_MAX);
  }
  if (kind === 'color' && colorIndex === 0) {
    return filtered.slice(0, REF_PICKER_MAX);
  }
  if (filtered.length) return filtered.slice(0, REF_PICKER_MAX);
  return studioDefaultRefUrls(pool, kind, colorIndex);
}

function syncRefUrlsFromJob(fresh: ManualProductJob) {
  const pool = fresh.studio?.ref_pool || [];
  const slot = fresh.studio?.current_slot;
  const kind =
    slot?.kind === 'gallery' || slot?.kind === 'detail' || slot?.kind === 'material'
      ? slot.kind
      : 'color';
  const idx = colorSlotIndex(fresh.studio, slot);
  const fromSlot = Array.isArray(slot?.ref_urls) ? slot!.ref_urls!.filter(Boolean) : [];
  return sanitizeFormRefUrls(
    fromSlot,
    pool,
    kind as 'color' | 'gallery' | 'detail' | 'material',
    idx,
    fresh.studio,
  );
}

function loadStudioImageModel(): StudioImageModel {
  if (typeof window === 'undefined') return 'pro';
  const v = localStorage.getItem(STUDIO_IMAGE_MODEL_KEY);
  return v === 'flash' || v === 'flash3' ? v : 'pro';
}

function loadStudioAspectRatio(): StudioAspectRatio {
  if (typeof window === 'undefined') return '1:1';
  const v = localStorage.getItem(STUDIO_ASPECT_RATIO_KEY);
  return v === '3:4' || v === '4:3' || v === '9:16' || v === '16:9' ? v : '1:1';
}

function studioAspectClass(ratio: StudioAspectRatio): string {
  if (ratio === '3:4') return 'aspect-[3/4]';
  if (ratio === '4:3') return 'aspect-[4/3]';
  if (ratio === '9:16') return 'aspect-[9/16]';
  if (ratio === '16:9') return 'aspect-[16/9]';
  return 'aspect-square';
}

function StudioAiImageSettings({
  imageModel,
  aspectRatio,
  onImageModelChange,
  onAspectRatioChange,
  disabled,
  compact = false,
}: {
  imageModel: StudioImageModel;
  aspectRatio: StudioAspectRatio;
  onImageModelChange: (v: StudioImageModel) => void;
  onAspectRatioChange: (v: StudioAspectRatio) => void;
  disabled?: boolean;
  compact?: boolean;
}) {
  return (
    <div
      className={`grid gap-3 ${compact ? 'grid-cols-1 sm:grid-cols-2' : 'grid-cols-1 sm:grid-cols-2'} rounded-lg border border-slate-200 bg-slate-50/80 p-3`}
    >
      <label className="block text-sm min-w-0">
        <span className="font-medium text-slate-800">Model tạo ảnh AI</span>
        <select
          className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white"
          value={imageModel}
          disabled={disabled}
          onChange={(e) => {
            const v = e.target.value as StudioImageModel;
            onImageModelChange(v);
            if (typeof window !== 'undefined') localStorage.setItem(STUDIO_IMAGE_MODEL_KEY, v);
          }}
        >
          <option value="pro">Pro — chất lượng cao (~3.350₫/ảnh, 2K)</option>
          <option value="flash">Flash — rẻ, nhanh (~1.000₫/ảnh, ~1K)</option>
          <option value="flash3">Flash 3.1 — cân bằng (~2.500₫/ảnh, 2K)</option>
        </select>
      </label>
      <label className="block text-sm min-w-0">
        <span className="font-medium text-slate-800">Tỷ lệ khung hình</span>
        <select
          className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white"
          value={aspectRatio}
          disabled={disabled}
          onChange={(e) => {
            const v = e.target.value as StudioAspectRatio;
            onAspectRatioChange(v);
            if (typeof window !== 'undefined') localStorage.setItem(STUDIO_ASPECT_RATIO_KEY, v);
          }}
        >
          <option value="1:1">1:1 — Vuông (SP / Ladipage)</option>
          <option value="3:4">3:4 — Dọc (mobile)</option>
          <option value="4:3">4:3 — Ngang</option>
          <option value="9:16">9:16 — Story / Reels</option>
          <option value="16:9">16:9 — Banner ngang</option>
        </select>
      </label>
      <p className={`text-[11px] text-slate-500 ${compact ? 'sm:col-span-2' : 'sm:col-span-2'}`}>
        Lưu tự động trên trình duyệt — áp dụng mọi lần tạo / tạo lại cho đến khi bạn đổi lại.
      </p>
    </div>
  );
}

function StudioFaceRefCard({
  url,
  colorName,
  compact = false,
}: {
  url: string;
  colorName: string;
  compact?: boolean;
}) {
  if (!url) return null;
  return (
    <div
      className={`rounded-xl border-2 border-sky-300 bg-sky-50/80 p-2 ${
        compact ? 'max-w-[8rem]' : 'max-w-xs'
      }`}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={url}
        alt=""
        className={`w-full rounded-lg object-cover bg-white ${compact ? 'h-16' : 'h-24'}`}
      />
      <p className="mt-1.5 text-[10px] font-semibold text-sky-900 leading-tight">
        Khuôn mặt người mẫu (ảnh màu #1)
      </p>
      <p className="text-[10px] text-sky-800 leading-tight">
        {colorName ? `«${colorName}»` : 'Màu đầu'} — <strong>chỉ</strong> giữ khuôn mặt; không lấy mẫu/màu SP
        từ ảnh này.
      </p>
      <span className="mt-1 inline-block rounded-full bg-sky-200 px-2 py-0.5 text-[9px] font-semibold uppercase text-sky-900">
        Khóa · ref mặt
      </span>
    </div>
  );
}

function toggleRefUrl(prev: string[], url: string, max = REF_PICKER_MAX): string[] {
  if (prev.includes(url)) return prev.filter((x) => x !== url);
  if (prev.length >= max) return [...prev.slice(1), url];
  return [...prev, url];
}

function StudioRefPicker({
  items,
  selectedUrls,
  onChange,
  disabled,
  compact = false,
  lockedUrls = [],
}: {
  items: ManualProductRefPoolItem[];
  selectedUrls: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
  compact?: boolean;
  lockedUrls?: string[];
}) {
  const lockedSet = new Set(lockedUrls.filter(Boolean));
  const visibleSelected = selectedUrls.filter(
    (u) => lockedSet.has(u) || items.some((item) => item.url === u),
  );
  if (!items.length) {
    return (
      <p className="text-xs text-slate-500 rounded-lg border border-dashed border-slate-200 px-3 py-2">
        Chưa có ảnh trong pool — upload ảnh mẫu SP hoặc tạo ảnh màu trước.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <div
        className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${
          selectedUrls.length
            ? 'bg-orange-100 text-orange-800'
            : 'bg-slate-100 text-slate-600'
        }`}
      >
        {visibleSelected.length
          ? `Đã chọn ${visibleSelected.length}/${REF_PICKER_MAX} ảnh`
          : `Chưa chọn — bấm ảnh để chọn (tối đa ${REF_PICKER_MAX})`}
      </div>
      <div className={`flex flex-wrap ${compact ? 'gap-2' : 'gap-3'}`}>
        {items.map((item) => {
          const selectedIndex = visibleSelected.indexOf(item.url);
          const checked = selectedIndex >= 0;
          const isLocked = lockedSet.has(item.url);
          const label = item.label || item.kind || 'Ảnh';
          return (
            <button
              key={item.id || item.url}
              type="button"
              disabled={disabled || isLocked}
              aria-pressed={checked}
              aria-label={checked ? `Bỏ chọn ${label}` : `Chọn ${label}`}
              onClick={() => {
                if (isLocked) return;
                const next = toggleRefUrl(selectedUrls, item.url);
                onChange([...lockedUrls.filter(Boolean), ...next.filter((u) => !lockedSet.has(u))].slice(0, REF_PICKER_MAX));
              }}
              className={`group relative text-left rounded-xl border-2 p-1.5 transition-all ${
                compact ? 'w-[5.5rem]' : 'w-[7rem]'
              } ${
                checked
                  ? 'border-[#ea580c] bg-orange-50 shadow-md ring-2 ring-orange-200/80'
                  : 'border-dashed border-slate-300 bg-slate-50 opacity-80 hover:border-slate-400 hover:bg-white hover:opacity-100 hover:shadow-sm'
              } ${disabled ? 'cursor-not-allowed opacity-60' : ''}`}
            >
              <span
                className={`absolute top-1.5 right-1.5 z-10 flex h-5 w-5 items-center justify-center rounded-full border-2 shadow-sm ${
                  checked
                    ? 'border-white bg-[#ea580c] text-white'
                    : 'border-white/90 bg-white/80 text-transparent group-hover:border-slate-300 group-hover:bg-slate-100'
                }`}
                aria-hidden
              >
                {checked ? (
                  visibleSelected.length > 1 ? (
                    <span className="text-[10px] font-bold leading-none">{selectedIndex + 1}</span>
                  ) : (
                    <svg className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor">
                      <path
                        fillRule="evenodd"
                        d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                        clipRule="evenodd"
                      />
                    </svg>
                  )
                ) : null}
              </span>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={item.url}
                alt=""
                className={`w-full rounded-md bg-slate-100 object-cover ${
                  compact ? 'h-16' : 'h-20'
                } ${checked ? '' : 'grayscale-[15%] group-hover:grayscale-0'}`}
              />
              <div
                className={`mt-1 truncate text-[10px] leading-tight ${
                  checked ? 'font-semibold text-[#c2410c]' : 'text-slate-600'
                }`}
              >
                {label}
              </div>
              {checked ? (
                <div className="mt-0.5 text-[9px] font-semibold uppercase tracking-wide text-[#ea580c]">
                  {isLocked ? 'Cố định' : 'Đã chọn'}
                </div>
              ) : (
                <div className="mt-0.5 text-[9px] text-slate-400 group-hover:text-slate-500">
                  Bấm để chọn
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** Nhập size → Enter / dấu phẩy → chip trong mảng `string[]` chuẩn. */
function SizeChipsInput({
  sizes,
  onChange,
  disabled,
}: {
  sizes: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
}) {
  const [draft, setDraft] = useState('');

  function commitDraft() {
    const parts = draft
      .split(/[,;/|]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (!parts.length) {
      setDraft('');
      return;
    }
    const seen = new Set(sizes.map((s) => s.toLowerCase()));
    const merged = [...sizes];
    for (const p of parts) {
      if (seen.has(p.toLowerCase())) continue;
      seen.add(p.toLowerCase());
      merged.push(p);
    }
    onChange(merged);
    setDraft('');
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5 min-h-[36px]">
        {sizes.map((sz) => (
          <span
            key={sz}
            className="inline-flex items-center gap-1 rounded-md bg-slate-100 border border-slate-200 px-2 py-1 text-sm text-slate-800"
          >
            {sz}
            {!disabled ? (
              <button
                type="button"
                className="text-slate-500 hover:text-slate-900"
                aria-label={`Xóa size ${sz}`}
                onClick={() => onChange(sizes.filter((x) => x !== sz))}
              >
                ×
              </button>
            ) : null}
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          disabled={disabled}
          className="flex-1 border border-slate-300 rounded-lg px-3 py-2 text-sm"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ',') {
              e.preventDefault();
              commitDraft();
            }
            if (e.key === 'Backspace' && !draft && sizes.length) {
              onChange(sizes.slice(0, -1));
            }
          }}
          onBlur={commitDraft}
          placeholder="Gõ size rồi Enter (VD: S hoặc 39)"
        />
        <button
          type="button"
          disabled={disabled || !draft.trim()}
          onClick={commitDraft}
          className="px-3 py-2 rounded-lg border border-slate-300 text-sm disabled:opacity-40"
        >
          Thêm
        </button>
      </div>
    </div>
  );
}

const STUDIO_MIN_COLOR_IMAGES = 1;
const STUDIO_MIN_GALLERY_IMAGES = 2;
const STUDIO_MIN_MATERIAL_IMAGES = 1;
const POLL_BUSY = new Set(['queued', 'generating', 'publishing', 'running']);
const INTERACTIVE_STATUSES = new Set([
  'awaiting_colors',
  'awaiting_input',
  'awaiting_approval',
  'ready_to_publish',
]);

export default function AdminManualProductCreatePage() {
  const { pushToast } = useToast();
  const [step, setStep] = useState(0);
  const [mode, setMode] = useState<ManualProductCreateMode>('manual');

  const [gender, setGender] = useState('Nữ');
  const [productName, setProductName] = useState('');
  const [material, setMaterial] = useState('');
  const [noSize, setNoSize] = useState(false);
  const [sizes, setSizes] = useState<string[]>([]);
  const [colorRows, setColorRows] = useState<ColorRow[]>([newColorRow()]);
  const [formKind, setFormKind] = useState<'color' | 'gallery' | 'detail' | 'material'>('color');
  const [formColorName, setFormColorName] = useState('');
  const [formPrompt, setFormPrompt] = useState('');
  const [formRefUrls, setFormRefUrls] = useState<string[]>([]);
  const [formAttachUrl, setFormAttachUrl] = useState('');
  const [price, setPrice] = useState('');
  const [available, setAvailable] = useState('500');
  const [notes, setNotes] = useState('');

  const [mainImage, setMainImage] = useState('');
  const [galleryImages, setGalleryImages] = useState<string[]>([]);
  const [detailImages, setDetailImages] = useState<string[]>([]);
  const [refImages, setRefImages] = useState<string[]>([]);
  const [imageModel, setImageModel] = useState<StudioImageModel>(() => loadStudioImageModel());
  const [aspectRatio, setAspectRatio] = useState<StudioAspectRatio>(() => loadStudioAspectRatio());
  const [modelPresence, setModelPresence] = useState<'none' | 'model'>('none');
  const [modelGender, setModelGender] = useState<'' | 'female' | 'male'>('');
  const [modelAgeGroup, setModelAgeGroup] = useState<
    '' | 'baby' | 'child' | 'teen' | 'adult' | 'middle_aged'
  >('');
  const [modelEthnicity, setModelEthnicity] = useState<'' | 'asian' | 'western'>('');
  const [shotStyle, setShotStyle] = useState<'studio' | 'lifestyle' | 'outdoor'>('studio');

  const [uploading, setUploading] = useState(false);
  const [formError, setFormError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [studioBusy, setStudioBusy] = useState(false);
  const [job, setJob] = useState<ManualProductJob | null>(null);
  const [draftReady, setDraftReady] = useState(false);
  const [resumeNotice, setResumeNotice] = useState<string | null>(null);
  const [serverSessions, setServerSessions] = useState<ManualProductJobSummary[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const steps = mode === 'ai' ? STEPS_AI : STEPS_MANUAL;

  const stopPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => () => stopPoll(), [stopPoll]);

  const draftSnapshot = useCallback((): ProductCreateDraft => {
    return {
      v: 1,
      savedAt: new Date().toISOString(),
      step,
      mode,
      jobId: job?.job_id || null,
      gender,
      productName,
      material,
      noSize,
      sizes,
      colorRows,
      formKind,
      formColorName,
      formPrompt,
      formRefUrls,
      formAttachUrl,
      price,
      available,
      notes,
      mainImage,
      galleryImages,
      detailImages,
      refImages,
      modelPresence,
      modelGender,
      modelAgeGroup,
      modelEthnicity,
      shotStyle,
    };
  }, [
    step,
    mode,
    job?.job_id,
    gender,
    productName,
    material,
    noSize,
    sizes,
    colorRows,
    formKind,
    formColorName,
    formPrompt,
    formRefUrls,
    formAttachUrl,
    price,
    available,
    notes,
    mainImage,
    galleryImages,
    detailImages,
    refImages,
    modelPresence,
    modelGender,
    modelAgeGroup,
    modelEthnicity,
    shotStyle,
  ]);

  const startPolling = useCallback(
    (jobId: string, opts?: { stopOnInteractive?: boolean }) => {
      stopPoll();
      pollRef.current = setInterval(async () => {
        try {
          const fresh = await manualProductCreateAPI.getJob(jobId);
          setJob(fresh);
          if (fresh.status === 'done') {
            stopPoll();
            setSubmitting(false);
            setStudioBusy(false);
            clearProductCreateDraft();
            pushToast({
              title: 'Đăng sản phẩm thành công',
              description: fresh.result?.name || fresh.result?.product_id || '',
              variant: 'success',
            });
            return;
          }
          if (fresh.status === 'failed') {
            stopPoll();
            setSubmitting(false);
            setStudioBusy(false);
            return;
          }
          if (opts?.stopOnInteractive && INTERACTIVE_STATUSES.has(fresh.status)) {
            stopPoll();
            setSubmitting(false);
            setStudioBusy(false);
            if (fresh.status === 'awaiting_approval') {
              setFormRefUrls(syncRefUrlsFromJob(fresh));
              const slot = fresh.studio?.current_slot;
              if (slot?.user_prompt) setFormPrompt(String(slot.user_prompt));
              if (slot?.attach_url) setFormAttachUrl(String(slot.attach_url));
              if (slot?.name) setFormColorName(String(slot.name));
            } else if (fresh.status === 'awaiting_input' || fresh.status === 'awaiting_colors') {
              const phase = fresh.studio?.phase || 'color';
              setFormKind(
                phase === 'gallery' || phase === 'detail' || phase === 'material'
                  ? phase
                  : phase === 'main'
                    ? 'gallery'
                    : 'color',
              );
              setFormPrompt('');
              const pool = fresh.studio?.ref_pool || [];
              const nextColorIdx = (fresh.studio?.colors || []).filter((c) =>
                (c?.img || '').trim(),
              ).length;
              setFormRefUrls(studioDefaultRefUrls(pool, 'color', nextColorIdx));
              setFormAttachUrl('');
              setFormColorName('');
            }
          }
        } catch {
          /* keep polling */
        }
      }, 2000);
    },
    [stopPoll, pushToast],
  );

  const applyDraftState = useCallback((d: ProductCreateDraft) => {
    setStep(d.step);
    setMode(d.mode);
    setGender(d.gender);
    setProductName(d.productName);
    setMaterial(d.material);
    setNoSize(d.noSize);
    setSizes(d.sizes);
    setColorRows(d.colorRows.length ? d.colorRows : [newColorRow()]);
    setFormKind(d.formKind);
    setFormColorName(d.formColorName);
    setFormPrompt(d.formPrompt);
    setFormRefUrls(d.formRefUrls);
    setFormAttachUrl(d.formAttachUrl);
    setPrice(d.price);
    setAvailable(d.available);
    setNotes(d.notes);
    setMainImage(d.mainImage);
    setGalleryImages(d.galleryImages);
    setDetailImages(d.detailImages);
    setRefImages(d.refImages);
    setModelPresence(d.modelPresence);
    setModelGender(d.modelGender);
    setModelAgeGroup(d.modelAgeGroup);
    setModelEthnicity(d.modelEthnicity);
    setShotStyle(d.shotStyle);
  }, []);

  const resumeJobById = useCallback(
    async (jobId: string, notice?: string) => {
      try {
        const fresh = await manualProductCreateAPI.getJob(jobId);
        const base: ProductCreateDraft = loadProductCreateDraft() || {
          v: 1,
          savedAt: new Date().toISOString(),
          step: 0,
          mode: (fresh.mode as ManualProductCreateMode) || 'ai',
          jobId,
          gender: 'Nữ',
          productName: '',
          material: '',
          noSize: false,
          sizes: [],
          colorRows: [newColorRow()],
          formKind: 'color',
          formColorName: '',
          formPrompt: '',
          formRefUrls: [],
          formAttachUrl: '',
          price: '',
          available: '500',
          notes: '',
          mainImage: '',
          galleryImages: [],
          detailImages: [],
          refImages: [],
          modelPresence: 'none',
          modelGender: '',
          modelAgeGroup: '',
          modelEthnicity: '',
          shotStyle: 'studio',
        };
        const merged = applyJobPayloadToDraft(fresh, { ...base, jobId });
        const studioSync = syncStudioFormFromJob(fresh);
        applyDraftState({
          ...merged,
          formKind: studioSync.formKind,
          formRefUrls: studioSync.formRefUrls.length ? studioSync.formRefUrls : merged.formRefUrls,
          // Studio sync thắng draft — tránh mang tên màu #1 sang form màu #2+
          formColorName: studioSync.formColorName,
          formPrompt: studioSync.formPrompt,
          formAttachUrl: studioSync.formAttachUrl,
        });
        setJob(fresh);
        if (fresh.status === 'awaiting_approval') {
          const slot = fresh.studio?.current_slot;
          if (slot?.user_prompt) setFormPrompt(String(slot.user_prompt));
          setFormRefUrls(syncRefUrlsFromJob(fresh));
          if (slot?.attach_url) setFormAttachUrl(String(slot.attach_url));
          if (slot?.name) setFormColorName(String(slot.name));
        }
        setResumeNotice(
          notice ||
            fresh.message ||
            'Đã khôi phục phiên làm việc — tiếp tục từ chỗ đang dở.',
        );
        if (POLL_BUSY.has(fresh.status)) {
          startPolling(jobId, { stopOnInteractive: true });
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Không tải được phiên';
        setFormError(msg);
      }
    },
    [applyDraftState, startPolling],
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const local = loadProductCreateDraft();
      if (local) {
        applyDraftState(local);
        if (local.jobId) {
          await resumeJobById(
            local.jobId,
            'Đã khôi phục phiên trên trình duyệt — tiếp tục tạo sản phẩm.',
          );
        } else {
          setResumeNotice('Đã khôi phục bản nháp form — tiếp tục nhập liệu.');
        }
      } else {
        try {
          const rows = await manualProductCreateAPI.listJobs({ active: true, limit: 5 });
          if (!cancelled && rows.length) setServerSessions(rows);
        } catch {
          /* ignore */
        }
      }
      if (!cancelled) setDraftReady(true);
    })();
    return () => {
      cancelled = true;
    };
  }, [applyDraftState, resumeJobById]);

  useEffect(() => {
    if (!draftReady) return;
    if (job?.status === 'done') {
      clearProductCreateDraft();
      return;
    }
    const t = window.setTimeout(() => {
      saveProductCreateDraft(draftSnapshot());
    }, 500);
    return () => window.clearTimeout(t);
  }, [draftReady, draftSnapshot, job?.status]);

  useEffect(() => {
    if (!draftReady || job?.status === 'done') return;
    const flush = () => saveProductCreateDraft(draftSnapshot());
    window.addEventListener('beforeunload', flush);
    return () => window.removeEventListener('beforeunload', flush);
  }, [draftReady, draftSnapshot, job?.status]);

  useEffect(() => {
    if (!draftReady || mode !== 'ai' || step !== 3 || !job?.job_id) return;
    let cancelled = false;
    (async () => {
      try {
        const fresh = await manualProductCreateAPI.getJob(job.job_id);
        if (cancelled) return;
        setJob(fresh);
        if (fresh.status === 'awaiting_approval') {
          const slot = fresh.studio?.current_slot;
          if (slot?.user_prompt) setFormPrompt(String(slot.user_prompt));
          setFormRefUrls(syncRefUrlsFromJob(fresh));
          if (slot?.attach_url) setFormAttachUrl(String(slot.attach_url));
          if (slot?.name) setFormColorName(String(slot.name));
        } else if (fresh.status === 'awaiting_input' || fresh.status === 'awaiting_colors') {
          const studioSync = syncStudioFormFromJob(fresh);
          setFormKind(studioSync.formKind);
          if (studioSync.formRefUrls.length) setFormRefUrls(studioSync.formRefUrls);
          // Luôn đồng bộ (kể cả '') — không giữ tên màu cũ từ ảnh trước
          setFormColorName(studioSync.formColorName);
        }
        if (POLL_BUSY.has(fresh.status)) {
          startPolling(job.job_id, { stopOnInteractive: true });
        }
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [draftReady, mode, step, job?.job_id, startPolling]);

  function discardSavedSession() {
    clearProductCreateDraft();
    setResumeNotice(null);
    setServerSessions([]);
    setJob(null);
    stopPoll();
    setFormError('');
    applyDraftState({
      v: 1,
      savedAt: new Date().toISOString(),
      step: 0,
      mode: 'manual',
      jobId: null,
      gender: 'Nữ',
      productName: '',
      material: '',
      noSize: false,
      sizes: [],
      colorRows: [newColorRow()],
      formKind: 'color',
      formColorName: '',
      formPrompt: '',
      formRefUrls: [],
      formAttachUrl: '',
      price: '',
      available: '500',
      notes: '',
      mainImage: '',
      galleryImages: [],
      detailImages: [],
      refImages: [],
      modelPresence: 'none',
      modelGender: '',
      modelAgeGroup: '',
      modelEthnicity: '',
      shotStyle: 'studio',
    });
    pushToast({ title: 'Đã xóa bản nháp', description: 'Bắt đầu phiên mới.', variant: 'success' });
  }

  const structuredColors = useMemo(
    () =>
      colorRows
        .map((r) => ({ name: r.name.trim(), img: r.img.trim() }))
        .filter((r) => r.name),
    [colorRows],
  );

  const studio = job?.studio;
  const currentSlot = studio?.current_slot;
  const pendingColorIndex = useMemo(() => {
    if (formKind !== 'color') return 0;
    return (studio?.colors || []).filter((c) => (c?.img || '').trim()).length;
  }, [formKind, studio?.colors]);
  const approvalColorIndex = colorSlotIndex(studio, currentSlot);
  const lockedModelFaceUrls = useMemo(() => {
    const face = firstApprovedColorUrl(studio);
    return face ? [face] : [];
  }, [studio]);
  const firstColorRef = useMemo(() => firstApprovedColorRow(studio), [studio]);
  const sanitizedFormRefUrls = useMemo(() => {
    const kindForSanitize =
      job?.status === 'awaiting_approval' &&
      (currentSlot?.kind === 'gallery' ||
        currentSlot?.kind === 'detail' ||
        currentSlot?.kind === 'material' ||
        currentSlot?.kind === 'color')
        ? (currentSlot.kind as 'color' | 'gallery' | 'detail' | 'material')
        : formKind;
    return sanitizeFormRefUrls(
      formRefUrls,
      studio?.ref_pool || [],
      kindForSanitize,
      job?.status === 'awaiting_approval' ? approvalColorIndex : pendingColorIndex,
      studio,
    );
  }, [
    formRefUrls,
    studio,
    formKind,
    job?.status,
    currentSlot?.kind,
    approvalColorIndex,
    pendingColorIndex,
  ]);

  useEffect(() => {
    if (!draftReady || !job || formKind !== 'color') return;
    const idx =
      job.status === 'awaiting_approval' ? approvalColorIndex : pendingColorIndex;
    if (idx >= 1 && lockedModelFaceUrls.length) {
      const withoutFace = formRefUrls.filter((u) => u !== lockedModelFaceUrls[0]);
      if (withoutFace.length !== formRefUrls.length) {
        setFormRefUrls(withoutFace);
      }
    }
  }, [
    draftReady,
    job,
    job?.status,
    formKind,
    approvalColorIndex,
    pendingColorIndex,
    lockedModelFaceUrls,
    formRefUrls,
  ]);

  const studioPublishCheck = useMemo(() => {
    const colorCount = (studio?.colors || []).filter((c) => (c?.img || '').trim()).length;
    const galleryCount = (studio?.images || []).length;
    const detailCount = (studio?.gallery || []).filter((u) => (u || '').trim()).length;
    const materialOk = Boolean((studio?.material_image || '').trim());
    return {
      colorCount,
      galleryCount,
      detailCount,
      materialOk,
      canPublish: Boolean(studio?.can_publish),
    };
  }, [studio]);
  const canPublish = studioPublishCheck.canPublish;

  const progressLabel = useMemo(() => {
    if (!job) return '';
    if (job.status === 'done') return 'Hoàn tất';
    if (job.status === 'failed') return 'Thất bại';
    return job.message || job.step || 'Đang xử lý…';
  }, [job]);

  async function uploadFiles(files: FileList | null, purpose: 'catalog' | 'ref') {
    if (!files || files.length === 0) return [] as string[];
    setUploading(true);
    setFormError('');
    try {
      const urls: string[] = [];
      const subfolder =
        purpose === 'ref' ? 'manual-products/refs' : 'manual-products/uploads';
      for (const file of Array.from(files)) {
        try {
          const res = await adminBunnyCdnAPI.upload(file, subfolder);
          urls.push(res.public_url);
        } catch (bunnyErr) {
          const res = await manualProductCreateAPI.uploadImage(file, purpose);
          urls.push(res.public_url);
          void bunnyErr;
        }
      }
      return urls;
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Upload thất bại';
      const hint = /fetch failed|không kết nối|Failed to fetch|ECONNREFUSED/i.test(msg)
        ? ' Backend chưa chạy hoặc chưa restart sau khi thêm API — mở cửa sổ uvicorn cổng 8001 rồi thử lại.'
        : '';
      setFormError(msg + hint);
      pushToast({ title: 'Upload lỗi', description: msg + hint, variant: 'error' });
      return [] as string[];
    } finally {
      setUploading(false);
    }
  }

  function updateColorRow(key: string, patch: Partial<ColorRow>) {
    setColorRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }

  function validateStep(s: number): string {
    if (s === 1) {
      if (mode === 'manual' && !productName.trim()) return 'Vui lòng nhập tên sản phẩm.';
      if (!material.trim()) return 'Vui lòng nhập chất liệu.';
      const p = Number(price);
      if (!Number.isFinite(p) || p <= 0) return 'Giá bán phải > 0.';
    }
    if (s === 2) {
      if (!noSize && sizes.length === 0) {
        return 'Thêm size (Enter sau mỗi size) hoặc chọn «Không có size».';
      }
      if (mode === 'manual') {
        if (!mainImage) return 'Cần ảnh chính.';
        const colorsWithImg = colorRows.filter((r) => r.img.trim() && r.name.trim());
        if (colorsWithImg.length < STUDIO_MIN_COLOR_IMAGES) {
          return `Cần ít nhất ${STUDIO_MIN_COLOR_IMAGES} ảnh màu (có tên + ảnh).`;
        }
        if (galleryImages.length < STUDIO_MIN_GALLERY_IMAGES) {
          return `Cần ít nhất ${STUDIO_MIN_GALLERY_IMAGES} ảnh gallery.`;
        }
        const incomplete = colorRows.some((r) => r.img && !r.name.trim());
        if (incomplete) return 'Mỗi ảnh màu cần có tên màu.';
      } else {
        if (modelPresence === 'model') {
          if (!modelGender) return 'Chọn «Có người mẫu» thì cần chọn giới tính người mẫu.';
          if (!modelAgeGroup) return 'Chọn «Có người mẫu» thì cần chọn tuổi người mẫu.';
          if (!modelEthnicity) return 'Chọn «Có người mẫu» thì cần chọn quốc tịch/gốc người mẫu.';
        }
      }
    }
    return '';
  }

  function goNext() {
    const err = validateStep(step);
    if (err) {
      setFormError(err);
      return;
    }
    setFormError('');
    const next = Math.min(steps.length - 1, step + 1);
    setStep(next);
    if (mode === 'ai' && next === 3 && (!job || job.status === 'failed')) {
      void startAiStudio();
    }
  }

  function goBack() {
    setFormError('');
    setStep((x) => Math.max(0, x - 1));
  }

  async function startManualJob() {
    const err = validateStep(1) || validateStep(2);
    if (err) {
      setFormError(err);
      setStep(err.includes('ảnh') || err.includes('Ảnh') || err.includes('size') || err.includes('màu') ? 2 : 1);
      return;
    }
    setFormError('');
    setSubmitting(true);
    setJob(null);
    try {
      const payload = {
        mode: 'manual' as const,
        price: Number(price),
        product_name: productName.trim(),
        material: material.trim(),
        gender,
        no_size: noSize,
        sizes: noSize ? [] : sizes,
        colors: structuredColors.map((c) => ({ name: c.name, img: c.img })),
        available: Math.max(0, Number(available) || 500),
        notes: notes.trim(),
        main_image: mainImage,
        images: galleryImages,
        gallery: [],
        require_taxonomy: false,
      };
      const created = await manualProductCreateAPI.createJob(payload);
      setJob(created);
      startPolling(created.job_id, { stopOnInteractive: false });
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Không tạo được job';
      setFormError(msg);
      setSubmitting(false);
      pushToast({ title: 'Không thể đăng', description: msg, variant: 'error' });
    }
  }

  async function startAiStudio() {
    const err = validateStep(1) || validateStep(2);
    if (err) {
      setFormError(err);
      setStep(2);
      return;
    }
    setFormError('');
    setSubmitting(true);
    setJob(null);
    try {
      const payload = {
        mode: 'ai' as const,
        price: Number(price),
        product_name: '',
        material: material.trim(),
        gender,
        no_size: noSize,
        sizes: noSize ? [] : sizes,
        colors: [],
        available: Math.max(0, Number(available) || 500),
        notes: notes.trim(),
        main_image: null,
        images: [],
        gallery: [],
        ref_image_urls: [],
        image_model: imageModel,
        aspect_ratio: aspectRatio,
        model_presence: modelPresence,
        model_gender: modelPresence === 'model' ? modelGender : '',
        model_age_group: modelPresence === 'model' ? modelAgeGroup : '',
        model_ethnicity: modelPresence === 'model' ? modelEthnicity : '',
        shot_style: shotStyle,
        require_taxonomy: true,
      };
      const created = await manualProductCreateAPI.createJob(payload);
      setJob(created);
      startPolling(created.job_id, { stopOnInteractive: true });
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Không tạo được session AI';
      setFormError(msg);
      setSubmitting(false);
      pushToast({ title: 'Không thể bắt đầu', description: msg, variant: 'error' });
    }
  }

  async function submitAdopt() {
    if (!job?.job_id) return;
    if (formKind !== 'gallery' && formKind !== 'detail') return;
    if (job.status === 'generating' || job.status === 'publishing') {
      setFormError('Ảnh đang được tạo — vui lòng đợi vài giây.');
      return;
    }
    const urls = sanitizedFormRefUrls.filter(Boolean);
    if (!urls.length) {
      setFormError('Chọn ít nhất 1 ảnh đã tạo để dùng làm ảnh mục này.');
      return;
    }
    setFormError('');
    setStudioBusy(true);
    try {
      const fresh = await manualProductCreateAPI.adoptImages(job.job_id, {
        kind: formKind,
        urls,
      });
      setJob(fresh);
      setFormPrompt('');
      const pool = fresh.studio?.ref_pool || [];
      setFormRefUrls(studioDefaultRefUrls(pool, formKind, 0));
      setStudioBusy(false);
      pushToast({
        title: formKind === 'gallery' ? 'Đã thêm ảnh gallery' : 'Đã thêm ảnh chi tiết',
        description: fresh.message || '',
        variant: 'success',
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Không dùng được ảnh đã chọn';
      setFormError(msg);
      setStudioBusy(false);
      pushToast({ title: 'Không thêm được ảnh', description: msg, variant: 'error' });
    }
  }

  async function submitGenerate(overrides?: {
    kind?: typeof formKind;
    name?: string;
    prompt?: string;
    ref_urls?: string[];
    attach_url?: string;
  }) {
    if (!job?.job_id) return;
    if (job.status === 'awaiting_approval') {
      await regenerateImage();
      return;
    }
    if (job.status === 'generating' || job.status === 'publishing') {
      setFormError('Ảnh đang được tạo — vui lòng đợi vài giây.');
      return;
    }
    const kind = overrides?.kind || formKind;
    // Màu mới: không gửi tên sẵn (tránh dùng tên màu #1). AI đọc từ ảnh mẫu vừa upload.
    const name =
      kind === 'color' ? '' : (overrides?.name ?? formColorName).trim();
    const prompt = (overrides?.prompt ?? formPrompt).trim();
    const pool = studio?.ref_pool || [];
    const colorIdx = kind === 'color' ? pendingColorIndex : 0;
    let refs = overrides?.ref_urls ?? formRefUrls;
    refs = sanitizeFormRefUrls(refs, pool, kind, colorIdx, studio);
    const attach = overrides?.attach_url ?? formAttachUrl;
    if ((kind === 'gallery' || kind === 'detail') && !prompt) {
      setFormError(
        kind === 'gallery'
          ? 'Gallery bắt buộc nhập ý muốn tạo ảnh (DeepSeek sẽ chuẩn hóa prompt).'
          : 'Ảnh chi tiết bắt buộc nhập ý muốn tạo ảnh (DeepSeek sẽ chuẩn hóa prompt).',
      );
      return;
    }
    if (kind === 'color') {
      if (colorIdx === 0 && refs.length === 0 && !attach.trim()) {
        setFormError('Ảnh màu đầu: upload ảnh mẫu sản phẩm — AI tự đọc tên màu.');
        return;
      }
      if (colorIdx >= 1) {
        const face = firstApprovedColorUrl(studio);
        const userRefs = refs.filter((u) => u !== face);
        if (userRefs.length === 0 && !attach.trim()) {
          setFormError('Ảnh màu tiếp theo: upload ảnh mẫu SP — AI tự đọc màu.');
          return;
        }
      }
    } else if (refs.length === 0 && !attach.trim()) {
      setFormError('Chọn ít nhất 1 ảnh tham khảo hoặc upload ảnh kèm.');
      return;
    }
    setFormError('');
    setStudioBusy(true);
    try {
      const fresh = await manualProductCreateAPI.generateImage(job.job_id, {
        kind,
        name: kind === 'color' ? name : '',
        prompt,
        ref_urls: refs.slice(0, 3),
        attach_url: attach || '',
        image_model: imageModel,
        aspect_ratio: aspectRatio,
      });
      setJob(fresh);
      startPolling(job.job_id, { stopOnInteractive: true });
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Không tạo được ảnh';
      setFormError(msg);
      setStudioBusy(false);
      pushToast({ title: 'Tạo ảnh lỗi', description: msg, variant: 'error' });
    }
  }

  async function approveImage() {
    if (!job?.job_id) return;
    setFormError('');
    setStudioBusy(true);
    try {
      const fresh = await manualProductCreateAPI.approveImage(job.job_id);
      setJob(fresh);
      setFormAttachUrl('');
      const phase = fresh.studio?.phase || 'color';
      setFormKind(
        phase === 'gallery' || phase === 'detail' || phase === 'material'
          ? phase
          : phase === 'main'
            ? 'gallery'
            : 'color',
      );
      setFormPrompt('');
      if (phase === 'color') {
        setFormColorName('');
        setFormRefUrls([]);
      }
      setStudioBusy(false);
      if (POLL_BUSY.has(fresh.status)) {
        startPolling(job.job_id, { stopOnInteractive: true });
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Không duyệt được ảnh';
      setFormError(msg);
      setStudioBusy(false);
    }
  }

  async function regenerateImage() {
    if (!job?.job_id) return;
    const slot = job.studio?.current_slot;
    const slotKind = (slot?.kind || '').trim();
    if ((slotKind === 'gallery' || slotKind === 'detail') && !formPrompt.trim()) {
      setFormError(
        slotKind === 'gallery'
          ? 'Gallery bắt buộc nhập ý muốn tạo ảnh (DeepSeek sẽ chuẩn hóa prompt).'
          : 'Ảnh chi tiết bắt buộc nhập ý muốn tạo ảnh (DeepSeek sẽ chuẩn hóa prompt).',
      );
      return;
    }
    setFormError('');
    setStudioBusy(true);
    const colorIdx = colorSlotIndex(job.studio, slot);
    const pool = job.studio?.ref_pool || [];
    const refs = sanitizeFormRefUrls(
      formRefUrls,
      pool,
      slotKind === 'gallery' || slotKind === 'detail' || slotKind === 'material'
        ? (slotKind as 'gallery' | 'detail' | 'material')
        : 'color',
      colorIdx,
      job.studio,
    );
    setFormRefUrls(refs);
    try {
      const fresh = await manualProductCreateAPI.regenerateImage(job.job_id, {
        prompt: formPrompt.trim() || null,
        ref_urls: refs,
        attach_url: formAttachUrl || null,
        image_model: imageModel,
        aspect_ratio: aspectRatio,
      });
      setJob(fresh);
      startPolling(job.job_id, { stopOnInteractive: true });
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Không tạo lại được';
      setFormError(msg);
      setStudioBusy(false);
    }
  }

  async function publishAiJob() {
    if (!job?.job_id) return;
    setFormError('');
    setSubmitting(true);
    setStudioBusy(true);
    try {
      const fresh = await manualProductCreateAPI.publishJob(job.job_id);
      setJob(fresh);
      startPolling(job.job_id, { stopOnInteractive: false });
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Không đăng được';
      setFormError(msg);
      setSubmitting(false);
      setStudioBusy(false);
      pushToast({ title: 'Không thể đăng', description: msg, variant: 'error' });
    }
  }

  async function retryJob() {
    if (!job?.job_id) return;
    setFormError('');
    setSubmitting(true);
    try {
      const restarted = await manualProductCreateAPI.retryJob(job.job_id);
      setJob(restarted);
      startPolling(job.job_id, { stopOnInteractive: mode === 'ai' });
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Retry thất bại';
      setFormError(msg);
      setSubmitting(false);
    }
  }

  function slotKindLabel(kind?: string | null, name?: string | null, index?: number) {
    if (kind === 'color') {
      if (name?.trim()) return `Ảnh màu «${name.trim()}»`;
      // #1: AI đọc tên SP + tên màu; #2+: chỉ đọc màu
      return (index ?? 0) >= 1
        ? 'Ảnh màu (AI đọc màu từ ảnh)'
        : 'Ảnh màu (AI đọc tên từ ảnh)';
    }
    if (kind === 'main') return 'Ảnh chính';
    if (kind === 'gallery') return `Ảnh gallery ${(index ?? 0) + 1}`;
    if (kind === 'detail') return `Ảnh chi tiết ${(index ?? 0) + 1}`;
    if (kind === 'material') return 'Ảnh chất liệu (Ladipage)';
    return 'Ảnh';
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Đăng sản phẩm thủ công / AI</h1>
          <p className="text-sm text-slate-600 mt-1">
            {mode === 'ai'
              ? 'Tạo từng ảnh → duyệt → Đăng (DeepSeek + taxonomy + Ladipage).'
              : 'Upload ảnh sẵn + DeepSeek viết tên/mô tả + Ladipage.'}
          </p>
        </div>
        <Link href="/admin/products" className="text-sm text-slate-600 underline shrink-0">
          ← Danh sách SP
        </Link>
      </div>

      <ol className="flex flex-wrap gap-2">
        {steps.map((label, i) => (
          <li
            key={label}
            className={`text-sm px-3 py-1.5 rounded-full border ${
              i === step
                ? 'bg-slate-900 text-white border-slate-900'
                : i < step
                  ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                  : 'bg-white text-slate-500 border-slate-200'
            }`}
          >
            {i + 1}. {label}
          </li>
        ))}
      </ol>

      {formError ? (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          {formError}
        </div>
      ) : null}

      {resumeNotice ? (
        <div
          className="bg-sky-50 border border-sky-200 text-sky-900 rounded-lg px-4 py-3 text-sm flex flex-wrap items-start justify-between gap-3"
          role="status"
        >
          <p>{resumeNotice}</p>
          <button
            type="button"
            onClick={discardSavedSession}
            className="shrink-0 text-sm font-medium underline text-sky-800"
          >
            Bắt đầu mới
          </button>
        </div>
      ) : null}

      {!resumeNotice && serverSessions.length > 0 ? (
        <div className="bg-amber-50 border border-amber-200 text-amber-950 rounded-lg px-4 py-3 text-sm space-y-2">
          <p className="font-medium">Có phiên tạo sản phẩm đang dở trên server</p>
          <ul className="space-y-2">
            {serverSessions.map((s) => (
              <li
                key={s.job_id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-100 bg-white/70 px-3 py-2"
              >
                <div className="min-w-0">
                  <div className="font-medium truncate">
                    {s.product_name || s.material || 'Sản phẩm chưa đặt tên'}
                  </div>
                  <div className="text-xs text-amber-900/80">
                    {s.mode === 'ai' ? 'AI Studio' : 'Thủ công'} · {s.status}
                    {s.message ? ` · ${s.message}` : ''}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => resumeJobById(s.job_id, 'Đã khôi phục phiên từ server.')}
                  className="shrink-0 text-sm font-medium px-3 py-1.5 rounded-lg bg-amber-600 text-white hover:bg-amber-700"
                >
                  Tiếp tục
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {step === 0 ? (
        <div className="space-y-4">
          <button
            type="button"
            onClick={() => {
              setMode('manual');
              setJob(null);
              setStep(0);
            }}
            className={`w-full text-left border rounded-xl p-4 ${
              mode === 'manual' ? 'border-slate-900 ring-2 ring-slate-900/10' : 'border-slate-200'
            }`}
          >
            <div className="font-medium text-slate-900">Bán thủ công</div>
            <p className="text-sm text-slate-600 mt-1">
              Upload ảnh chính + gallery + chi tiết + ảnh từng màu từ máy. DeepSeek viết tên và mô tả.
            </p>
          </button>
          <button
            type="button"
            onClick={() => {
              setMode('ai');
              setProductName('');
              setJob(null);
              setStep(0);
            }}
            className={`w-full text-left border rounded-xl p-4 ${
              mode === 'ai' ? 'border-slate-900 ring-2 ring-slate-900/10' : 'border-slate-200'
            }`}
          >
            <div className="font-medium text-slate-900">Đăng tự động bằng AI</div>
            <p className="text-sm text-slate-600 mt-1">
              Ảnh mẫu từng màu ở Studio → AI đọc tên → tạo/duyệt → DeepSeek viết nội dung khi đăng.
            </p>
          </button>
        </div>
      ) : null}

      {step === 1 ? (
        <div className="space-y-4 bg-white border border-slate-200 rounded-xl p-4">
          {mode === 'manual' ? (
            <label className="block text-sm">
              <span className="font-medium text-slate-800">Tên sản phẩm *</span>
              <input
                className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2"
                value={productName}
                onChange={(e) => setProductName(e.target.value)}
                placeholder="VD: Áo sơ mi linen nữ form rộng…"
              />
            </label>
          ) : null}

          <label className="block text-sm">
            <span className="font-medium text-slate-800">Giới tính</span>
            <select
              className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2"
              value={gender}
              onChange={(e) => setGender(e.target.value)}
            >
              <option>Nữ</option>
              <option>Nam</option>
              <option>Unisex</option>
            </select>
          </label>

          <label className="block text-sm">
            <span className="font-medium text-slate-800">Chất liệu *</span>
            <input
              className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2"
              value={material}
              onChange={(e) => setMaterial(e.target.value)}
              placeholder="VD: Cotton, da PU, denim…"
            />
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm">
              <span className="font-medium text-slate-800">Giá bán (VND) *</span>
              <input
                type="number"
                min={1}
                className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                placeholder="199000"
              />
            </label>
            <label className="block text-sm">
              <span className="font-medium text-slate-800">Tồn kho</span>
              <input
                type="number"
                min={0}
                className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2"
                value={available}
                onChange={(e) => setAvailable(e.target.value)}
              />
            </label>
          </div>

          {mode === 'manual' ? (
            <label className="block text-sm">
              <span className="font-medium text-slate-800">Ghi chú thêm (tuỳ chọn)</span>
              <textarea
                className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2 text-sm min-h-[64px]"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Điểm nổi bật, dịp dùng…"
              />
            </label>
          ) : null}
        </div>
      ) : null}

      {step === 2 ? (
        <div className="space-y-5 bg-white border border-slate-200 rounded-xl p-4">
          {uploading ? <p className="text-sm text-slate-600">Đang upload ảnh…</p> : null}

          <div className="space-y-2 border-b border-slate-100 pb-4">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm font-medium text-slate-800">Size</span>
              <button
                type="button"
                onClick={() => {
                  setNoSize((v) => !v);
                  if (!noSize) setSizes([]);
                }}
                className={`text-xs px-2.5 py-1 rounded-full border ${
                  noSize
                    ? 'bg-slate-900 text-white border-slate-900'
                    : 'bg-white text-slate-700 border-slate-300'
                }`}
              >
                {noSize ? 'Đã chọn: Không có size' : 'Không có size'}
              </button>
            </div>
            {!noSize ? (
              <SizeChipsInput sizes={sizes} onChange={setSizes} disabled={uploading} />
            ) : (
              <p className="text-xs text-slate-500">Sản phẩm không phân size.</p>
            )}
          </div>

          {mode === 'manual' ? (
            <div className="space-y-3 border-b border-slate-100 pb-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-slate-800">Màu sắc</div>
                  <p className="text-xs text-slate-500 mt-0.5">Mỗi dòng: tên màu + ảnh màu</p>
                </div>
                <button
                  type="button"
                  onClick={() => setColorRows((prev) => [...prev, newColorRow()])}
                  className="text-xs px-2.5 py-1 rounded-lg border border-slate-300 text-slate-700"
                >
                  + Thêm màu
                </button>
              </div>
              <div className="space-y-3">
                {colorRows.map((row, idx) => (
                  <div
                    key={row.key}
                    className="flex flex-col sm:flex-row sm:items-start gap-3 border border-slate-200 rounded-lg p-3"
                  >
                    <div className="text-xs text-slate-400 w-6 shrink-0 pt-2">{idx + 1}</div>
                    <div className="shrink-0">
                      {row.img ? (
                        <Thumb url={row.img} onRemove={() => updateColorRow(row.key, { img: '' })} />
                      ) : (
                        <div className="w-24 h-24 rounded-lg border border-dashed border-slate-300 bg-slate-50 flex items-center justify-center text-[11px] text-slate-400 text-center px-1">
                          Ảnh màu
                        </div>
                      )}
                      <input
                        type="file"
                        accept="image/*"
                        className="mt-2 block w-full text-xs max-w-[11rem]"
                        onChange={async (e) => {
                          const urls = await uploadFiles(e.target.files, 'catalog');
                          if (urls[0]) updateColorRow(row.key, { img: urls[0] });
                          e.target.value = '';
                        }}
                      />
                    </div>
                    <div className="flex-1 space-y-2">
                      <label className="block text-sm">
                        <span className="font-medium text-slate-800">Tên màu</span>
                        <input
                          className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                          value={row.name}
                          onChange={(e) => updateColorRow(row.key, { name: e.target.value })}
                          placeholder="VD: Đen, Be, Hồng phấn…"
                        />
                      </label>
                    </div>
                    <button
                      type="button"
                      className="text-xs text-red-600 underline shrink-0 self-start sm:mt-8"
                      onClick={() =>
                        setColorRows((prev) =>
                          prev.length <= 1 ? [newColorRow()] : prev.filter((r) => r.key !== row.key),
                        )
                      }
                    >
                      Xóa
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="border border-emerald-100 bg-emerald-50 rounded-lg px-3 py-2 text-xs text-emerald-900">
              Bước Studio: upload ảnh mẫu từng mốc → Tạo / duyệt / Tiếp. AI tự đọc tên màu (ảnh đầu: cả tên SP).
            </div>
          )}

          {mode === 'manual' ? (
            <>
              <div>
                <div className="text-sm font-medium text-slate-800 mb-2">Ảnh chính *</div>
                {mainImage ? <Thumb url={mainImage} onRemove={() => setMainImage('')} /> : null}
                <input
                  type="file"
                  accept="image/*"
                  className="block w-full text-sm mt-2"
                  onChange={async (e) => {
                    const urls = await uploadFiles(e.target.files, 'catalog');
                    if (urls[0]) setMainImage(urls[0]);
                    e.target.value = '';
                  }}
                />
              </div>
              <div>
                <div className="text-sm font-medium text-slate-800 mb-1">
                  Ảnh gallery * (tối thiểu {STUDIO_MIN_GALLERY_IMAGES})
                </div>
                <div className="flex flex-wrap gap-2 mb-2">
                  {galleryImages.map((u) => (
                    <Thumb
                      key={u}
                      url={u}
                      onRemove={() => setGalleryImages((prev) => prev.filter((x) => x !== u))}
                    />
                  ))}
                </div>
                <input
                  type="file"
                  accept="image/*"
                  multiple
                  className="block w-full text-sm"
                  onChange={async (e) => {
                    const urls = await uploadFiles(e.target.files, 'catalog');
                    if (urls.length) setGalleryImages((prev) => [...prev, ...urls]);
                    e.target.value = '';
                  }}
                />
              </div>
            </>
          ) : (
            <>
              <div className="border border-sky-100 bg-sky-50 rounded-lg px-3 py-2 text-xs text-sky-900 space-y-1">
                <p>
                  <strong>Không upload ảnh ở bước này.</strong> Sang Studio ảnh, mỗi màu bạn upload ảnh tham chiếu
                  riêng khi bấm Tạo.
                </p>
                <p>
                  Ảnh màu #1 chọn người mẫu → ảnh màu #2 trở đi giữ <strong>cùng khuôn mặt</strong> từ ảnh màu #1
                  đã OK.
                </p>
                <p>
                  Bắt buộc trước khi đăng: {STUDIO_MIN_COLOR_IMAGES} ảnh màu, {STUDIO_MIN_GALLERY_IMAGES} gallery,{' '}
                  {STUDIO_MIN_MATERIAL_IMAGES} ảnh chất liệu. Ảnh chi tiết sản phẩm tuỳ chọn.
                </p>
              </div>
              <label className="block text-sm">
                <span className="font-medium text-slate-800">Người mẫu</span>
                <select
                  className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2"
                  value={modelPresence}
                  onChange={(e) => {
                    const v = e.target.value as 'none' | 'model';
                    setModelPresence(v);
                    if (v === 'none') {
                      setModelGender('');
                      setModelAgeGroup('');
                      setModelEthnicity('');
                    }
                  }}
                >
                  <option value="none">Không người mẫu — chỉ sản phẩm</option>
                  <option value="model">Có người mẫu mặc đồ / cầm SP</option>
                </select>
              </label>
              {modelPresence === 'model' ? (
                <div className="grid grid-cols-2 gap-3 border border-slate-200 rounded-lg p-3 bg-slate-50">
                  <label className="block text-sm">
                    <span className="font-medium text-slate-800">Giới tính người mẫu *</span>
                    <select
                      className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2"
                      value={modelGender}
                      onChange={(e) => setModelGender(e.target.value as 'female' | 'male')}
                    >
                      <option value="">— Chọn —</option>
                      <option value="female">Nữ</option>
                      <option value="male">Nam</option>
                    </select>
                  </label>
                  <label className="block text-sm">
                    <span className="font-medium text-slate-800">Tuổi người mẫu *</span>
                    <select
                      className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2"
                      value={modelAgeGroup}
                      onChange={(e) =>
                        setModelAgeGroup(
                          e.target.value as 'baby' | 'child' | 'teen' | 'adult' | 'middle_aged',
                        )
                      }
                    >
                      <option value="">— Chọn —</option>
                      <option value="baby">Em bé (0–3 tuổi)</option>
                      <option value="child">Trẻ em (4–12 tuổi)</option>
                      <option value="teen">Thiếu niên (13–17 tuổi)</option>
                      <option value="adult">Người lớn (18–35 tuổi)</option>
                      <option value="middle_aged">Trung niên (35–55 tuổi)</option>
                    </select>
                  </label>
                  <label className="block text-sm col-span-2">
                    <span className="font-medium text-slate-800">Quốc tịch / gốc người mẫu *</span>
                    <select
                      className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2"
                      value={modelEthnicity}
                      onChange={(e) => setModelEthnicity(e.target.value as 'asian' | 'western')}
                    >
                      <option value="">— Chọn —</option>
                      <option value="asian">Châu Á</option>
                      <option value="western">Châu Âu / phương Tây</option>
                    </select>
                  </label>
                </div>
              ) : null}
              <label className="block text-sm">
                <span className="font-medium text-slate-800">Bối cảnh chụp</span>
                <select
                  className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2"
                  value={shotStyle}
                  onChange={(e) =>
                    setShotStyle(e.target.value as 'studio' | 'lifestyle' | 'outdoor')
                  }
                >
                  <option value="studio">Studio chuyên nghiệp (nền sạch)</option>
                  <option value="lifestyle">Lifestyle trong nhà</option>
                  <option value="outdoor">Phong cảnh / ngoài trời</option>
                </select>
              </label>
            </>
          )}
        </div>
      ) : null}

      {/* Manual step Đăng */}
      {mode === 'manual' && step === 3 ? (
        <div className="space-y-4 bg-white border border-slate-200 rounded-xl p-4">
          <div className="text-sm text-slate-700 space-y-1">
            <p>
              <span className="font-medium">Tên SP:</span> {productName || '—'}
            </p>
            <p>
              <span className="font-medium">Chất liệu:</span> {material || '—'}
            </p>
            <p>
              <span className="font-medium">Giá:</span> {price || '—'} VND
            </p>
            <p>
              <span className="font-medium">Màu:</span>{' '}
              {structuredColors.length
                ? structuredColors.map((c) => c.name).join(', ')
                : '—'}
            </p>
          </div>

          {job ? (
            <div className="rounded-lg border border-slate-200 p-3 space-y-2">
              <div className="flex items-center justify-between gap-2 text-sm">
                <span className="font-medium text-slate-800">{progressLabel}</span>
                <span className="text-slate-500">{job.progress ?? 0}%</span>
              </div>
              <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className={`h-full transition-all ${
                    job.status === 'failed' ? 'bg-red-500' : 'bg-emerald-500'
                  }`}
                  style={{ width: `${Math.max(4, job.progress || 0)}%` }}
                />
              </div>
              {job.status === 'failed' && job.error ? (
                <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-3 py-2 text-sm">
                  {job.error}{' '}
                  <button type="button" onClick={retryJob} className="underline font-medium">
                    Thử lại
                  </button>
                </div>
              ) : null}
              {job.status === 'done' && job.result ? (
                <div className="bg-emerald-50 border border-emerald-200 text-emerald-900 rounded-lg px-3 py-2 text-sm space-y-1">
                  <p>
                    Đã tạo <strong>{job.result.name}</strong> ({job.result.product_id})
                  </p>
                  <div className="flex flex-wrap gap-3">
                    {job.result.slug ? (
                      <Link href={`/products/${job.result.slug}`} className="underline" target="_blank">
                        Xem trang sản phẩm
                      </Link>
                    ) : null}
                    <Link href="/admin/products" className="underline">
                      Về danh sách SP
                    </Link>
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          {!job || job.status === 'failed' ? (
            <button
              type="button"
              disabled={submitting || uploading}
              onClick={startManualJob}
              className="w-full sm:w-auto px-5 py-2.5 rounded-lg bg-slate-900 text-white text-sm font-medium disabled:opacity-50"
            >
              {submitting ? 'Đang đăng…' : 'Bắt đầu đăng sản phẩm'}
            </button>
          ) : null}
        </div>
      ) : null}

      {/* AI Studio — từng mốc */}
      {mode === 'ai' && step === 3 ? (
        <div className="space-y-4 bg-white border border-slate-200 rounded-xl p-4">
          {!job ||
          (submitting && !INTERACTIVE_STATUSES.has(job.status) && job.status !== 'done' && job.status !== 'failed') ? (
            <div className="rounded-lg border border-slate-200 p-3 space-y-2">
              <p className="text-sm font-medium text-slate-800">
                {job ? progressLabel : 'Đang khởi tạo session AI…'}
              </p>
              <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-500 transition-all"
                  style={{ width: `${Math.max(4, job?.progress || 8)}%` }}
                />
              </div>
              {!job ? (
                <button type="button" onClick={startAiStudio} className="text-sm underline text-slate-700">
                  Bắt đầu lại
                </button>
              ) : null}
            </div>
          ) : null}

          {job?.status === 'failed' ? (
            <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-3 py-2 text-sm">
              {job.error || job.message}{' '}
              <button type="button" onClick={retryJob} className="underline font-medium">
                Thử lại
              </button>
            </div>
          ) : null}

          {job && (job.status === 'generating' || job.status === 'publishing') ? (
            <div className="rounded-lg border border-slate-200 p-3 space-y-2">
              <div className="flex items-center justify-between gap-2 text-sm">
                <span className="font-medium text-slate-800">{progressLabel}</span>
                <span className="text-slate-500">{job.progress ?? 0}%</span>
              </div>
              <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-500 transition-all"
                  style={{ width: `${Math.max(4, job.progress || 0)}%` }}
                />
              </div>
            </div>
          ) : null}

          {/* Form tạo theo mốc */}
          {job &&
          (job.status === 'awaiting_input' ||
            job.status === 'awaiting_colors') ? (
            <div className="space-y-4">
              {job.vision_product_name ? (
                <p className="text-sm text-slate-800">
                  <span className="font-medium">Tên SEO:</span> {job.vision_product_name}
                </p>
              ) : null}

              <div className="flex flex-wrap gap-2">
                {(
                  [
                    ['color', 'Ảnh màu'],
                    ['gallery', 'Ảnh gallery'],
                    ['material', 'Ảnh chất liệu'],
                    ['detail', 'Ảnh chi tiết sản phẩm'],
                  ] as const
                ).map(([k, label]) => (
                  <button
                    key={k}
                    type="button"
                    onClick={() => {
                      setFormKind(k);
                      setFormPrompt('');
                      const nextColorIdx =
                        k === 'color'
                          ? (studio?.colors || []).filter((c) => (c?.img || '').trim()).length
                          : 0;
                      setFormRefUrls(studioDefaultRefUrls(studio?.ref_pool || [], k, nextColorIdx));
                    }}
                    className={`text-xs px-3 py-1.5 rounded-full border ${
                      formKind === k
                        ? 'bg-slate-900 text-white border-slate-900'
                        : 'bg-white text-slate-700 border-slate-300'
                    }`}
                  >
                    {label}
                    {k === 'detail' ? (
                      <span className="ml-1 opacity-80 font-normal">(tuỳ chọn)</span>
                    ) : null}
                  </button>
                ))}
              </div>

              {formKind === 'color' ? (
                <p className="text-xs text-sky-900 bg-sky-50 border border-sky-100 rounded-lg px-3 py-2">
                  {pendingColorIndex === 0 ? (
                    <>
                      Ảnh màu <strong>đầu tiên</strong>: upload ảnh mẫu SP — AI tự đọc tên SP + tên màu. Mỗi lần
                      Tạo lại → người mẫu khác (cùng cài đặt tuổi/giới tính).
                    </>
                  ) : (
                    <>
                      Ảnh màu <strong>thứ {pendingColorIndex + 1}</strong>: upload{' '}
                      <strong>ảnh mẫu SP mới</strong> — AI lấy <strong>kiểu đồ từ ảnh này</strong>, chỉ giữ{' '}
                      <strong>khuôn mặt</strong> từ ảnh màu #1 (không dùng lại sản phẩm màu #1).
                    </>
                  )}
                </p>
              ) : null}

              {formKind === 'gallery' ? (
                <p className="text-xs text-sky-900 bg-sky-50 border border-sky-100 rounded-lg px-3 py-2">
                  Chọn ảnh màu / ảnh đã tạo để <strong>dùng luôn làm gallery</strong>, hoặc chọn làm tham khảo rồi{' '}
                  <strong>Tạo mới</strong>. Nhập ý muốn (vd đeo vai, đứng nghiêng) — DeepSeek chuẩn hóa prompt:{' '}
                  <strong>giữ nguyên SP</strong>, chỉ đổi tư thế/cách dùng. Cần đủ {STUDIO_MIN_GALLERY_IMAGES} ảnh
                  gallery trước khi đăng.
                </p>
              ) : null}

              {formKind === 'detail' ? (
                <p className="text-xs text-violet-900 bg-violet-50 border border-violet-100 rounded-lg px-3 py-2">
                  Ảnh chi tiết <strong>tuỳ chọn để đăng</strong> — chọn ảnh đã tạo để dùng luôn, hoặc tạo mới. Nhập ý
                  muốn — DeepSeek chuẩn hóa prompt: <strong>giữ nguyên SP</strong>, chỉ đổi góc/cách dùng.
                </p>
              ) : null}

              {formKind === 'material' ? (
                <p className="text-xs text-amber-900 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
                  Ảnh cận cảnh chất liệu — AI đọc chất liệu đã nhập ở bước 1
                  {material.trim() ? (
                    <>
                      : <strong>{material.trim()}</strong>
                    </>
                  ) : (
                    ' (chưa có — quay lại bước Thuộc tính để nhập)'
                  )}
                  , soạn 3 ưu điểm/điểm đáng mua (DeepSeek) rồi in trực tiếp lên ảnh dạng nhãn tiếng Việt.
                  Sau khi duyệt, ảnh + nội dung dùng cho section «Chất liệu» trên Ladipage.
                </p>
              ) : null}

              <div className="space-y-4">
                {formKind === 'color' && pendingColorIndex >= 1 && firstColorRef.url ? (
                  <div>
                    <div className="text-sm font-medium text-slate-800 mb-2">
                      Khuôn mẫu người mẫu (từ ảnh màu #1)
                    </div>
                    <StudioFaceRefCard url={firstColorRef.url} colorName={firstColorRef.name} />
                  </div>
                ) : null}

                <div>
                  <div className="text-sm font-medium text-slate-800 mb-1">
                    {formKind === 'color'
                      ? pendingColorIndex >= 1
                        ? 'Ảnh mẫu sản phẩm mới *'
                        : 'Ảnh mẫu sản phẩm *'
                      : 'Chọn ảnh tham khảo (tối đa 3) *'}
                  </div>
                  <p className="text-xs text-slate-500 mb-2">
                    {formKind === 'color' && pendingColorIndex === 0
                      ? 'Upload ảnh mẫu SP khách — AI lấy kiểu, màu, cắt may từ ảnh; người mẫu theo cài đặt Studio.'
                      : formKind === 'color' && pendingColorIndex >= 1
                        ? 'Upload ảnh mẫu SP khách cho màu này — AI thay sản phẩm theo ảnh mới; chỉ giữ khuôn mặt từ ảnh màu #1.'
                        : formKind === 'gallery' || formKind === 'detail'
                          ? 'Gồm ảnh màu và ảnh đã tạo. Có thể dùng luôn làm ảnh mục này, hoặc chọn làm tham khảo rồi tạo mới.'
                          : 'Gồm ảnh đã tạo. Chọn màu nào → tạo theo ảnh màu đó.'}
                  </p>
                  {formKind === 'color' ? (
                    <>
                      {formAttachUrl ? (
                        <div className="mb-2">
                          <Thumb url={formAttachUrl} onRemove={() => setFormAttachUrl('')} />
                          <p className="text-[10px] text-emerald-800 mt-1">Mẫu SP (màu + kiểu) gửi cho AI</p>
                        </div>
                      ) : null}
                      <input
                        type="file"
                        accept="image/*"
                        disabled={studioBusy || uploading}
                        className="block w-full text-sm mb-1"
                        onChange={async (e) => {
                          const urls = await uploadFiles(e.target.files, 'ref');
                          if (urls[0]) setFormAttachUrl(urls[0]);
                          e.target.value = '';
                        }}
                      />
                    </>
                  ) : null}
                </div>

                {formKind !== 'color' && (studio?.ref_pool || []).length > 0 ? (
                  <StudioRefPicker
                    items={studio?.ref_pool || []}
                    selectedUrls={sanitizedFormRefUrls}
                    onChange={setFormRefUrls}
                    disabled={studioBusy}
                  />
                ) : null}
              </div>

              <StudioAiImageSettings
                imageModel={imageModel}
                aspectRatio={aspectRatio}
                onImageModelChange={setImageModel}
                onAspectRatioChange={setAspectRatio}
                disabled={studioBusy || uploading}
              />

              <label className="block text-sm">
                <span className="font-medium text-slate-800">
                  Nội dung muốn tạo ảnh{' '}
                  {formKind === 'gallery' || formKind === 'detail' ? (
                    <span className="text-red-600">*</span>
                  ) : (
                    <span className="font-normal text-slate-500">(tuỳ chọn)</span>
                  )}
                </span>
                <textarea
                  className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2 text-sm min-h-[72px] disabled:opacity-50"
                  value={formPrompt}
                  disabled={studioBusy || uploading}
                  onChange={(e) => setFormPrompt(e.target.value)}
                  placeholder={
                    formKind === 'gallery' || formKind === 'detail'
                      ? 'Bắt buộc — VD: đeo túi trên vai, đứng ¾, cầm túi bằng tay… (DeepSeek sẽ soạn lệnh giữ nguyên SP).'
                      : 'VD: tay ngắn, cổ V, mặc chéo vạt, đứng ¾… — để trống thì AI tự theo ảnh mẫu.'
                  }
                  required={formKind === 'gallery' || formKind === 'detail'}
                />
                {formKind === 'gallery' || formKind === 'detail' ? (
                  <p className="mt-1 text-[11px] text-slate-500">
                    DeepSeek viết lại thành prompt chuẩn: giữ nguyên sản phẩm từ ảnh mẫu; chỉ đổi thế đứng/cách dùng
                    theo ý bạn.
                  </p>
                ) : null}
              </label>

              <div className="flex flex-wrap gap-2">
                {(formKind === 'gallery' || formKind === 'detail') && sanitizedFormRefUrls.length > 0 ? (
                  <button
                    type="button"
                    disabled={studioBusy || uploading}
                    onClick={() => submitAdopt()}
                    className="px-4 py-2.5 rounded-lg border border-emerald-600 text-emerald-800 bg-emerald-50 text-sm font-medium disabled:opacity-50"
                  >
                    {studioBusy
                      ? 'Đang lưu…'
                      : formKind === 'gallery'
                        ? `Dùng ${sanitizedFormRefUrls.length} ảnh đã chọn làm gallery`
                        : `Dùng ${sanitizedFormRefUrls.length} ảnh đã chọn làm chi tiết`}
                  </button>
                ) : null}
                <button
                  type="button"
                  disabled={
                    studioBusy ||
                    uploading ||
                    ((formKind === 'gallery' || formKind === 'detail') && !formPrompt.trim())
                  }
                  onClick={() => submitGenerate()}
                  className="px-4 py-2.5 rounded-lg bg-slate-900 text-white text-sm font-medium disabled:opacity-50"
                >
                  {studioBusy
                    ? 'Đang tạo…'
                    : `Tạo mới ${slotKindLabel(
                        formKind,
                        formColorName,
                        formKind === 'color'
                          ? pendingColorIndex
                          : formKind === 'gallery'
                            ? studioPublishCheck.galleryCount
                            : formKind === 'detail'
                              ? studioPublishCheck.detailCount
                              : 0,
                      )}`}
                </button>
              </div>
            </div>
          ) : null}

          {/* Duyệt ảnh vừa tạo */}
          {job?.status === 'awaiting_approval' ? (
            <div className="space-y-4">
              {currentSlot?.url ? (
                <div className="space-y-2">
                  <div className="text-sm font-medium text-slate-800">
                    {slotKindLabel(currentSlot.kind, currentSlot.name, currentSlot.index)}
                    {currentSlot.attempt ? ` · lần ${currentSlot.attempt}` : ''}
                  </div>
                  <div
                    className={`relative w-full max-w-md ${studioAspectClass(aspectRatio)} rounded-xl overflow-hidden border border-slate-200 bg-slate-50`}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={currentSlot.url} alt="" className="w-full h-full object-contain" />
                  </div>
                </div>
              ) : (
                <p className="text-sm text-amber-800 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
                  {job.error || 'Chưa có ảnh — sửa prompt/ref rồi Tạo lại.'}
                </p>
              )}

              {currentSlot?.kind === 'color' ? (
                <div>
                  {approvalColorIndex === 0 ? (
                    <p className="text-xs text-sky-800 bg-sky-50 border border-sky-100 rounded-lg px-2 py-1.5">
                      Tạo lại ảnh màu đầu → người mẫu khác (cùng tuổi/giới tính đã cài).
                    </p>
                  ) : (
                    <div className="space-y-2">
                      <p className="text-xs text-amber-800 bg-amber-50 border border-amber-100 rounded-lg px-2 py-1.5">
                        Upload ảnh mẫu SP mới nếu cần đổi mẫu — khuôn mặt giữ từ màu #1.
                      </p>
                      {firstColorRef.url ? (
                        <StudioFaceRefCard
                          url={firstColorRef.url}
                          colorName={firstColorRef.name}
                          compact
                        />
                      ) : null}
                      {formAttachUrl ? (
                        <div>
                          <Thumb url={formAttachUrl} onRemove={() => setFormAttachUrl('')} />
                        </div>
                      ) : null}
                      <input
                        type="file"
                        accept="image/*"
                        disabled={studioBusy || uploading}
                        className="block w-full text-sm"
                        onChange={async (e) => {
                          const urls = await uploadFiles(e.target.files, 'ref');
                          if (urls[0]) setFormAttachUrl(urls[0]);
                          e.target.value = '';
                        }}
                      />
                    </div>
                  )}
                </div>
              ) : null}

              {currentSlot?.kind === 'gallery' ||
              currentSlot?.kind === 'detail' ||
              currentSlot?.kind === 'material' ? (
                <div>
                  <div className="text-sm font-medium text-slate-800 mb-1">
                    Ảnh tham khảo đã chọn (tối đa 3) — có thể chọn lại trước khi Tạo lại
                  </div>
                  <p className="text-xs text-slate-500 mb-2">
                    Giữ nguyên lựa chọn lần tạo trước; bấm ảnh để bỏ/chọn thêm rồi Tạo lại.
                  </p>
                  <StudioRefPicker
                    items={studio?.ref_pool || []}
                    selectedUrls={sanitizedFormRefUrls}
                    onChange={setFormRefUrls}
                    disabled={studioBusy}
                    compact
                  />
                </div>
              ) : null}

              <StudioAiImageSettings
                imageModel={imageModel}
                aspectRatio={aspectRatio}
                onImageModelChange={setImageModel}
                onAspectRatioChange={setAspectRatio}
                disabled={studioBusy}
                compact
              />

              <label className="block text-sm">
                <span className="font-medium text-slate-800">
                  Nội dung muốn tạo ảnh{' '}
                  {currentSlot?.kind === 'gallery' || currentSlot?.kind === 'detail' ? (
                    <span className="text-red-600">*</span>
                  ) : (
                    <span className="font-normal text-slate-500">(tuỳ chọn)</span>
                  )}
                </span>
                <textarea
                  className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2 text-sm min-h-[72px] disabled:opacity-50"
                  value={formPrompt}
                  disabled={studioBusy}
                  onChange={(e) => setFormPrompt(e.target.value)}
                  placeholder={
                    currentSlot?.kind === 'gallery' || currentSlot?.kind === 'detail'
                      ? 'Bắt buộc — sửa ý (vd đeo vai) rồi Tạo lại. DeepSeek giữ nguyên SP, chỉ đổi tư thế/cách dùng.'
                      : 'Sửa mô tả rồi bấm Tạo lại — VD: tay ngắn, cổ V, đứng nghiêng…'
                  }
                  required={currentSlot?.kind === 'gallery' || currentSlot?.kind === 'detail'}
                />
              </label>

              <div className="flex flex-wrap gap-2 items-end">
                <button
                  type="button"
                  disabled={studioBusy || !currentSlot?.url}
                  onClick={approveImage}
                  className="px-4 py-2.5 rounded-lg bg-emerald-700 text-white text-sm font-medium disabled:opacity-50"
                >
                  OK — Tiếp
                </button>
                <button
                  type="button"
                  disabled={
                    studioBusy ||
                    ((currentSlot?.kind === 'gallery' || currentSlot?.kind === 'detail') &&
                      !formPrompt.trim())
                  }
                  onClick={regenerateImage}
                  className="px-4 py-2.5 rounded-lg border border-slate-300 text-slate-800 text-sm font-medium disabled:opacity-50"
                >
                  Tạo lại
                </button>
              </div>
            </div>
          ) : null}

          {/* Đã duyệt + Đăng */}
          {job && job.status !== 'done' && job.status !== 'queued' ? (
            <div className="space-y-2 border-t border-slate-100 pt-3">
              <div className="text-xs font-medium text-slate-600 uppercase tracking-wide">
                Tiến độ ảnh trước khi đăng
              </div>
              <ul className="text-sm space-y-1">
                <li className={studioPublishCheck.colorCount >= STUDIO_MIN_COLOR_IMAGES ? 'text-emerald-700' : 'text-slate-700'}>
                  Ảnh màu: {studioPublishCheck.colorCount}/{STUDIO_MIN_COLOR_IMAGES}
                  {studioPublishCheck.colorCount >= STUDIO_MIN_COLOR_IMAGES ? ' ✓' : ''}
                </li>
                <li className={studioPublishCheck.galleryCount >= STUDIO_MIN_GALLERY_IMAGES ? 'text-emerald-700' : 'text-slate-700'}>
                  Gallery: {studioPublishCheck.galleryCount}/{STUDIO_MIN_GALLERY_IMAGES}
                  {studioPublishCheck.galleryCount >= STUDIO_MIN_GALLERY_IMAGES ? ' ✓' : ''}
                </li>
                <li className={studioPublishCheck.materialOk ? 'text-emerald-700' : 'text-slate-700'}>
                  Ảnh chất liệu: {studioPublishCheck.materialOk ? 1 : 0}/{STUDIO_MIN_MATERIAL_IMAGES}
                  {studioPublishCheck.materialOk ? ' ✓' : ''}
                </li>
                <li className={studioPublishCheck.detailCount > 0 ? 'text-emerald-700' : 'text-slate-500'}>
                  Ảnh chi tiết (tuỳ chọn): {studioPublishCheck.detailCount}
                  {studioPublishCheck.detailCount > 0 ? ' ✓' : ''}
                </li>
              </ul>
              <div className="text-xs font-medium text-slate-600 uppercase tracking-wide pt-1">
                Đã tạo / chọn được làm ref
              </div>
              <div className="flex flex-wrap gap-2">
                {(studio?.ref_pool || []).map((item) => (
                  <div key={`p-${item.id || item.url}`} className="text-center">
                    <Thumb url={item.url} />
                    <div className="text-[11px] text-slate-600 mt-0.5 max-w-[6rem] truncate">
                      {item.label}
                    </div>
                  </div>
                ))}
              </div>
              {canPublish ? (
                <button
                  type="button"
                  disabled={submitting || studioBusy || job.status === 'publishing'}
                  onClick={publishAiJob}
                  className="w-full sm:w-auto px-5 py-2.5 rounded-lg bg-slate-900 text-white text-sm font-medium disabled:opacity-50"
                >
                  {submitting || job.status === 'publishing'
                    ? 'Đang đăng (DeepSeek + taxonomy)…'
                    : 'Đăng sản phẩm'}
                </button>
              ) : (
                <p className="text-xs text-amber-800 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
                  Chưa đủ ảnh để đăng — hoàn thành checklist phía trên (màu, gallery, chất liệu).
                </p>
              )}
              <p className="text-xs text-slate-500">
                Bắt buộc: {STUDIO_MIN_COLOR_IMAGES} ảnh màu, {STUDIO_MIN_GALLERY_IMAGES} gallery,{' '}
                {STUDIO_MIN_MATERIAL_IMAGES} ảnh chất liệu. Ảnh chi tiết sản phẩm là tuỳ chọn.
              </p>
            </div>
          ) : null}

          {job?.status === 'done' && job.result ? (
            <div className="bg-emerald-50 border border-emerald-200 text-emerald-900 rounded-lg px-3 py-2 text-sm space-y-1">
              <p>
                Đã tạo <strong>{job.result.name}</strong> ({job.result.product_id})
              </p>
              <div className="flex flex-wrap gap-3">
                {job.result.slug ? (
                  <Link href={`/products/${job.result.slug}`} className="underline" target="_blank">
                    Xem trang sản phẩm
                  </Link>
                ) : null}
                {job.result.ladipage_id ? (
                  <Link href={`/admin/ladipage/${job.result.ladipage_id}/edit`} className="underline">
                    Sửa Ladipage
                  </Link>
                ) : null}
                <Link href="/admin/products" className="underline">
                  Về danh sách SP
                </Link>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="flex items-center justify-between gap-3 pt-2">
        <button
          type="button"
          onClick={goBack}
          disabled={step === 0 || submitting || studioBusy}
          className="px-4 py-2 rounded-lg border border-slate-300 text-sm disabled:opacity-40"
        >
          Quay lại
        </button>
        {step < steps.length - 1 ? (
          <button
            type="button"
            onClick={goNext}
            disabled={uploading || submitting}
            className="px-4 py-2 rounded-lg bg-slate-900 text-white text-sm font-medium disabled:opacity-50"
          >
            {mode === 'ai' && step === 2 ? 'Tiếp — Studio ảnh' : 'Tiếp tục'}
          </button>
        ) : null}
      </div>
    </div>
  );
}
