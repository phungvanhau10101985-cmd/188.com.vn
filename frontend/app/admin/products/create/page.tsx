'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  adminBunnyCdnAPI,
  manualProductCreateAPI,
  type ManualProductCreateMode,
  type ManualProductJob,
} from '@/lib/admin-api';
import { useToast } from '@/components/ToastProvider';

const STEPS_MANUAL = ['Chế độ', 'Thuộc tính', 'Ảnh', 'Đăng'] as const;
const STEPS_AI = ['Chế độ', 'Thuộc tính', 'Ảnh gốc', 'Studio ảnh'] as const;

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

const POLL_BUSY = new Set(['queued', 'generating', 'publishing', 'running']);

export default function AdminManualProductCreatePage() {
  const { pushToast } = useToast();
  const [step, setStep] = useState(0);
  const [mode, setMode] = useState<ManualProductCreateMode>('manual');

  const [gender, setGender] = useState('Nữ');
  const [productName, setProductName] = useState('');
  const [material, setMaterial] = useState('');
  const [style, setStyle] = useState('Châu Á');
  const [noSize, setNoSize] = useState(false);
  const [sizes, setSizes] = useState<string[]>([]);
  const [colorRows, setColorRows] = useState<ColorRow[]>([newColorRow()]);
  const [formKind, setFormKind] = useState<'color' | 'gallery' | 'detail'>('color');
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
  const [imageModel, setImageModel] = useState<'pro' | 'flash' | 'flash3'>('pro');
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
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const steps = mode === 'ai' ? STEPS_AI : STEPS_MANUAL;

  const stopPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => () => stopPoll(), [stopPoll]);

  const structuredColors = useMemo(
    () =>
      colorRows
        .map((r) => ({ name: r.name.trim(), img: r.img.trim() }))
        .filter((r) => r.name),
    [colorRows],
  );

  const studio = job?.studio;
  const currentSlot = studio?.current_slot;
  const canPublish = Boolean(
    studio?.can_publish ||
      studio?.main_image ||
      (studio?.colors || []).some((c) => c?.img),
  );
  const interactiveStatuses = new Set([
    'awaiting_colors',
    'awaiting_input',
    'awaiting_approval',
    'ready_to_publish',
  ]);

  const progressLabel = useMemo(() => {
    if (!job) return '';
    if (job.status === 'done') return 'Hoàn tất';
    if (job.status === 'failed') return 'Thất bại';
    return job.message || job.step || 'Đang xử lý…';
  }, [job]);

  function startPolling(jobId: string, opts?: { stopOnInteractive?: boolean }) {
    stopPoll();
    pollRef.current = setInterval(async () => {
      try {
        const fresh = await manualProductCreateAPI.getJob(jobId);
        setJob(fresh);
        if (fresh.status === 'done') {
          stopPoll();
          setSubmitting(false);
          setStudioBusy(false);
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
        if (opts?.stopOnInteractive && interactiveStatuses.has(fresh.status)) {
          stopPoll();
          setSubmitting(false);
          setStudioBusy(false);
          if (fresh.status === 'awaiting_input' || fresh.status === 'awaiting_colors') {
            const phase = fresh.studio?.phase || 'color';
            setFormKind(
              phase === 'gallery' || phase === 'detail'
                ? phase
                : phase === 'main'
                  ? 'gallery'
                  : 'color',
            );
            setFormPrompt('');
            const pool = fresh.studio?.ref_pool || [];
            const defaults = pool
              .filter((p) => p.kind === 'ref' || p.kind === 'color')
              .map((p) => p.url)
              .filter(Boolean)
              .slice(0, 3);
            if (defaults.length && formRefUrls.length === 0) {
              setFormRefUrls(defaults);
            }
            if ((fresh.vision_colors || []).length && !formColorName) {
              setFormColorName((fresh.vision_colors || [])[0] || '');
            }
          }
        }
      } catch {
        /* keep polling */
      }
    }, 2000);
  }

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
        const incomplete = colorRows.some((r) => r.img && !r.name.trim());
        if (incomplete) return 'Mỗi ảnh màu cần có tên màu.';
      } else {
        if (refImages.length === 0) return 'Cần ít nhất 1 ảnh gốc tham chiếu (tối đa 3).';
        if (refImages.length > 3) return 'Tối đa 3 ảnh gốc.';
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
        style,
        no_size: noSize,
        sizes: noSize ? [] : sizes,
        colors: structuredColors.map((c) => ({ name: c.name, img: c.img })),
        available: Math.max(0, Number(available) || 500),
        notes: notes.trim(),
        main_image: mainImage,
        images: galleryImages,
        gallery: detailImages,
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
        style,
        no_size: noSize,
        sizes: noSize ? [] : sizes,
        colors: [],
        available: Math.max(0, Number(available) || 500),
        notes: notes.trim(),
        main_image: null,
        images: [],
        gallery: [],
        ref_image_urls: refImages,
        image_model: imageModel,
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

  async function submitGenerate(overrides?: {
    kind?: typeof formKind;
    name?: string;
    prompt?: string;
    ref_urls?: string[];
    attach_url?: string;
  }) {
    if (!job?.job_id) return;
    const kind = overrides?.kind || formKind;
    const name = (overrides?.name ?? formColorName).trim();
    const prompt = (overrides?.prompt ?? formPrompt).trim();
    const refs = overrides?.ref_urls ?? formRefUrls;
    const attach = overrides?.attach_url ?? formAttachUrl;
    if (kind === 'color' && !name) {
      setFormError('Nhập tên màu trước khi tạo.');
      return;
    }
    if (refs.length === 0 && !attach) {
      setFormError('Chọn ít nhất 1 ảnh tham khảo hoặc gửi ảnh kèm.');
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
        phase === 'gallery' || phase === 'detail' ? phase : phase === 'main' ? 'gallery' : 'color',
      );
      setFormPrompt('');
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
    setFormError('');
    setStudioBusy(true);
    try {
      const fresh = await manualProductCreateAPI.regenerateImage(job.job_id, {
        prompt: formPrompt.trim() || null,
        ref_urls: formRefUrls.length ? formRefUrls.slice(0, 3) : null,
        attach_url: formAttachUrl || null,
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
    if (kind === 'color') return `Ảnh màu «${name || ''}»`;
    if (kind === 'main') return 'Ảnh chính';
    if (kind === 'gallery') return `Ảnh gallery ${(index ?? 0) + 1}`;
    if (kind === 'detail') return `Ảnh chi tiết ${(index ?? 0) + 1}`;
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
              Ảnh gốc → Gemini đặt tên → bạn gõ màu → tạo/duyệt từng ảnh → bấm Đăng khi đủ.
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
          ) : (
            <p className="text-xs text-emerald-800 bg-emerald-50 border border-emerald-100 rounded px-2 py-1.5">
              Mode AI: Gemini đọc ảnh gốc đặt tên SEO — không cần nhập tên.
            </p>
          )}

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

          <label className="block text-sm">
            <span className="font-medium text-slate-800">Mẫu / phong cách</span>
            <select
              className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2"
              value={style}
              onChange={(e) => setStyle(e.target.value)}
            >
              <option>Châu Á</option>
              <option>Châu Âu</option>
              <option>Khác</option>
            </select>
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

          <label className="block text-sm">
            <span className="font-medium text-slate-800">Ghi chú thêm (tuỳ chọn)</span>
            <textarea
              className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2 text-sm min-h-[64px]"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Điểm nổi bật, dịp dùng…"
            />
          </label>
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
              Bước Studio: từng mốc tạo ảnh — gõ màu + chọn ảnh tham khảo + prompt → Tạo / Tạo lại / Tiếp.
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
                <div className="text-sm font-medium text-slate-800 mb-1">Ảnh gallery</div>
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
              <div>
                <div className="text-sm font-medium text-slate-800 mb-1">Ảnh chi tiết</div>
                <div className="flex flex-wrap gap-2 mb-2">
                  {detailImages.map((u) => (
                    <Thumb
                      key={u}
                      url={u}
                      onRemove={() => setDetailImages((prev) => prev.filter((x) => x !== u))}
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
                    if (urls.length) setDetailImages((prev) => [...prev, ...urls]);
                    e.target.value = '';
                  }}
                />
              </div>
            </>
          ) : (
            <>
              <div>
                <div className="text-sm font-medium text-slate-800 mb-1">
                  Ảnh gốc tham chiếu (tối đa 3) *
                </div>
                <p className="text-xs text-slate-500 mb-2">
                  AI đọc ảnh đặt tên SEO, rồi tạo ảnh đăng theo màu bạn gõ. Ảnh gốc không đăng lên SP.
                </p>
                <div className="flex flex-wrap gap-2 mb-2">
                  {refImages.map((u) => (
                    <Thumb
                      key={u}
                      url={u}
                      onRemove={() => setRefImages((prev) => prev.filter((x) => x !== u))}
                    />
                  ))}
                </div>
                <input
                  type="file"
                  accept="image/*"
                  multiple
                  disabled={refImages.length >= 3}
                  className="block w-full text-sm"
                  onChange={async (e) => {
                    const room = 3 - refImages.length;
                    if (room <= 0) return;
                    const files = e.target.files;
                    if (!files) return;
                    const limited = Array.from(files).slice(0, room);
                    const dt = new DataTransfer();
                    limited.forEach((f) => dt.items.add(f));
                    const urls = await uploadFiles(dt.files, 'ref');
                    if (urls.length) setRefImages((prev) => [...prev, ...urls].slice(0, 3));
                    e.target.value = '';
                  }}
                />
              </div>
              <p className="text-xs text-slate-500">
                Không cần chọn số lượng ảnh trước — sang Studio sẽ tạo từng ảnh một: gõ màu, chọn ảnh
                tham khảo, viết nội dung rồi tạo; tạo lại nếu chưa ưng, tiếp tục tạo màu/gallery/chi tiết
                khi nào bạn thấy đủ.
              </p>
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
              <label className="block text-sm">
                <span className="font-medium text-slate-800">Model tạo ảnh AI</span>
                <select
                  className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2"
                  value={imageModel}
                  onChange={(e) =>
                    setImageModel(e.target.value as 'pro' | 'flash' | 'flash3')
                  }
                >
                  <option value="pro">Pro — chất lượng cao (~3.350₫/ảnh, 2K)</option>
                  <option value="flash">Flash — rẻ, nhanh (~1.000₫/ảnh, ~1K)</option>
                  <option value="flash3">Flash 3.1 — cân bằng (~2.500₫/ảnh, 2K)</option>
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
          (submitting && !interactiveStatuses.has(job.status) && job.status !== 'done' && job.status !== 'failed') ? (
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
            job.status === 'awaiting_colors' ||
            job.status === 'ready_to_publish') ? (
            <div className="space-y-4">
              {job.vision_product_name ? (
                <p className="text-sm text-slate-800">
                  <span className="font-medium">Tên SEO:</span> {job.vision_product_name}
                </p>
              ) : null}
              {(job.vision_colors || []).length ? (
                <p className="text-xs text-slate-500">
                  Gợi ý màu từ ảnh: {(job.vision_colors || []).join(', ')}
                </p>
              ) : null}

              <div className="flex flex-wrap gap-2">
                {(
                  [
                    ['color', 'Ảnh màu'],
                    ['gallery', 'Ảnh gallery'],
                    ['detail', 'Ảnh chi tiết'],
                  ] as const
                ).map(([k, label]) => (
                  <button
                    key={k}
                    type="button"
                    onClick={() => {
                      setFormKind(k);
                      setFormPrompt('');
                    }}
                    className={`text-xs px-3 py-1.5 rounded-full border ${
                      formKind === k
                        ? 'bg-slate-900 text-white border-slate-900'
                        : 'bg-white text-slate-700 border-slate-300'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {formKind === 'color' ? (
                <label className="block text-sm">
                  <span className="font-medium text-slate-800">Tên màu *</span>
                  <input
                    className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2"
                    value={formColorName}
                    onChange={(e) => setFormColorName(e.target.value)}
                    placeholder="VD: Đỏ, Be, Đen…"
                    disabled={studioBusy}
                  />
                </label>
              ) : null}

              <div>
                <div className="text-sm font-medium text-slate-800 mb-1">
                  Chọn ảnh tham khảo (tối đa 3) *
                </div>
                <p className="text-xs text-slate-500 mb-2">
                  Gồm ảnh gốc + mọi ảnh đã tạo. Chọn màu nào → tạo theo ảnh màu đó.
                </p>
                <div className="flex flex-wrap gap-3">
                  {(studio?.ref_pool || []).map((item) => {
                    const checked = formRefUrls.includes(item.url);
                    return (
                      <button
                        key={item.id || item.url}
                        type="button"
                        disabled={studioBusy}
                        onClick={() => {
                          setFormRefUrls((prev) => {
                            if (prev.includes(item.url)) return prev.filter((x) => x !== item.url);
                            if (prev.length >= 3) return [...prev.slice(1), item.url];
                            return [...prev, item.url];
                          });
                        }}
                        className={`text-left rounded-lg border p-1.5 w-[6.5rem] ${
                          checked ? 'border-emerald-600 ring-2 ring-emerald-600/20' : 'border-slate-200'
                        }`}
                      >
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={item.url}
                          alt=""
                          className="w-full h-20 object-cover rounded-md bg-slate-50"
                        />
                        <div className="text-[10px] text-slate-600 mt-1 truncate">
                          {item.label || item.kind}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <div className="text-sm font-medium text-slate-800 mb-1">Ảnh kèm (tuỳ chọn)</div>
                <p className="text-xs text-slate-500 mb-2">
                  Upload thêm ảnh gửi kèm lần tạo này (ưu tiên làm ref đầu).
                </p>
                {formAttachUrl ? (
                  <div className="mb-2">
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

              <label className="block text-sm">
                <span className="font-medium text-slate-800">Ghi chú thêm (tuỳ chọn)</span>
                <textarea
                  className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2 text-sm min-h-[64px]"
                  value={formPrompt}
                  onChange={(e) => setFormPrompt(e.target.value)}
                  disabled={studioBusy}
                  placeholder="VD: mô tả thêm chất liệu, chi tiết ảnh kèm, tay áo dài hơn…"
                />
                <p className="text-xs text-slate-500 mt-1">
                  Chỉ bổ sung vào prompt AI có sẵn (giữ nguyên màu/kiểu đã chọn) — không cần điền cũng được.
                </p>
              </label>

              <button
                type="button"
                disabled={studioBusy || uploading}
                onClick={() => submitGenerate()}
                className="px-4 py-2.5 rounded-lg bg-slate-900 text-white text-sm font-medium disabled:opacity-50"
              >
                {studioBusy ? 'Đang tạo…' : `Tạo ${slotKindLabel(formKind, formColorName, 0)}`}
              </button>
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
                  <div className="relative w-full max-w-md aspect-square rounded-xl overflow-hidden border border-slate-200 bg-slate-50">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={currentSlot.url} alt="" className="w-full h-full object-contain" />
                  </div>
                </div>
              ) : (
                <p className="text-sm text-amber-800 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
                  {job.error || 'Chưa có ảnh — sửa prompt/ref rồi Tạo lại.'}
                </p>
              )}

              <label className="block text-sm">
                <span className="font-medium text-slate-800">Ghi chú thêm (tuỳ chọn) — sửa rồi Tạo lại</span>
                <textarea
                  className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2 text-sm min-h-[64px]"
                  value={formPrompt}
                  onChange={(e) => setFormPrompt(e.target.value)}
                  disabled={studioBusy}
                  placeholder="VD: chưa ưng chỗ này, đổi ánh sáng ấm hơn…"
                />
              </label>

              <div>
                <div className="text-sm font-medium text-slate-800 mb-1">Ảnh tham khảo (tạo lại)</div>
                <div className="flex flex-wrap gap-2">
                  {(studio?.ref_pool || []).map((item) => {
                    const checked = formRefUrls.includes(item.url);
                    return (
                      <button
                        key={`r-${item.id || item.url}`}
                        type="button"
                        disabled={studioBusy}
                        onClick={() => {
                          setFormRefUrls((prev) => {
                            if (prev.includes(item.url)) return prev.filter((x) => x !== item.url);
                            if (prev.length >= 3) return [...prev.slice(1), item.url];
                            return [...prev, item.url];
                          });
                        }}
                        className={`rounded-lg border p-1 w-20 ${
                          checked ? 'border-emerald-600' : 'border-slate-200'
                        }`}
                      >
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={item.url} alt="" className="w-full h-16 object-cover rounded" />
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
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
                  disabled={studioBusy}
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
              ) : null}
              <p className="text-xs text-slate-500">
                Có ≥1 ảnh màu/chính đã OK là Đăng được — không bắt buộc tạo hết gallery.
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
