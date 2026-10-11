'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  adminProductAPI,
  type AdminImageLocalizationTrial,
} from '@/lib/admin-api';
import { looksLikeHttpUrl } from '@/lib/image-from-url';

type TrialMode = 'local_only' | 'api' | 'openai';
type Slide = { trialId: string; kind: 'source' | 'result'; title: string; caption: string };

const ENGINE_LABEL: Record<string, string> = {
  local: 'Local',
  gemini: 'Gemini',
  gpt: 'GPT',
  kept: 'Giữ gốc',
  deleted: 'Đã xóa',
  error: 'Lỗi',
};

function engineClass(engine: string): string {
  if (engine === 'gemini') return 'bg-violet-100 text-violet-800';
  if (engine === 'gpt') return 'bg-sky-100 text-sky-800';
  if (engine === 'deleted' || engine === 'error') return 'bg-red-100 text-red-800';
  if (engine === 'kept') return 'bg-amber-100 text-amber-900';
  return 'bg-slate-100 text-slate-800';
}

function modeLabel(mode: TrialMode): string {
  if (mode === 'api') return 'Gemini';
  if (mode === 'openai') return 'GPT Image';
  return 'Local · DeepSeek + vẽ';
}

function expiresLabel(iso: string): string {
  const ms = new Date(iso).getTime() - Date.now();
  if (!Number.isFinite(ms)) return 'Xóa sau 7 ngày';
  const days = Math.max(0, Math.ceil(ms / 86_400_000));
  if (days <= 1) return 'Xóa trong hôm nay';
  return `Xóa sau ${days} ngày`;
}

function clipboardImageFile(data: DataTransfer | null): File | null {
  if (!data) return null;
  for (const item of Array.from(data.items)) {
    if (item.kind === 'file' && item.type.startsWith('image/')) {
      const file = item.getAsFile();
      if (file) return file;
    }
  }
  for (const file of Array.from(data.files)) {
    if (file.type.startsWith('image/')) return file;
  }
  return null;
}

function whenLabel(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString('vi-VN', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' });
}

function slidesFor(trials: AdminImageLocalizationTrial[], onlyId?: string): Slide[] {
  const rows = onlyId ? trials.filter((row) => row.id === onlyId) : trials;
  const slides: Slide[] = [];
  for (const row of rows) {
    if (row.files.source) {
      slides.push({ trialId: row.id, kind: 'source', title: row.filename || 'Ảnh gốc', caption: 'Ảnh gốc' });
    }
    if (row.files.result) {
      slides.push({
        trialId: row.id,
        kind: 'result',
        title: row.filename || 'Ảnh kết quả',
        caption: `Kết quả · ${ENGINE_LABEL[row.engine] || row.engine}`,
      });
    }
  }
  return slides;
}

function useTrialImage(trialId: string, kind: 'source' | 'result' | null) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!trialId || !kind) {
      setUrl(null);
      return;
    }
    let objectUrl = '';
    let cancel = false;
    adminProductAPI
      .fetchImageLocalizationTrialFile(trialId, kind)
      .then((blob) => {
        if (cancel) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => {
        if (!cancel) setUrl(null);
      });
    return () => {
      cancel = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [trialId, kind]);
  return url;
}

function TrialThumb({ trial }: { trial: AdminImageLocalizationTrial }) {
  const kind = trial.files.result ? 'result' : trial.files.source ? 'source' : null;
  const url = useTrialImage(trial.id, kind);
  if (!url) {
    return <div className="h-full w-full animate-pulse bg-gray-100" />;
  }
  return <img src={url} alt="" className="h-full w-full object-cover" />;
}

export function ImageLocalizationTrial({
  mode,
  language,
  openaiModel,
  openaiQuality,
  openaiSize,
}: {
  mode: TrialMode;
  language: string;
  openaiModel: string;
  openaiQuality: string;
  openaiSize: string;
}) {
  const [items, setItems] = useState<AdminImageLocalizationTrial[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [localPreview, setLocalPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [imageUrl, setImageUrl] = useState('');
  const [linkBusy, setLinkBusy] = useState(false);
  const [slides, setSlides] = useState<Slide[] | null>(null);
  const [slideIndex, setSlideIndex] = useState(0);
  const urlInputRef = useRef<HTMLInputElement>(null);
  const imageUrlRef = useRef('');
  const lastFetchedUrlRef = useRef<string | null>(null);
  const inflightUrlRef = useRef<string | null>(null);
  const fileFromUrlRef = useRef(false);
  imageUrlRef.current = imageUrl;

  const load = useCallback(async () => {
    try {
      const data = await adminProductAPI.listImageLocalizationTrials();
      setItems(data.items);
      setListError(null);
      setSelectedId((current) => current || data.items[0]?.id || null);
    } catch (err) {
      setListError(err instanceof Error ? err.message : 'Không tải được ảnh thử');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!file) {
      setLocalPreview(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setLocalPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const selected = items.find((row) => row.id === selectedId) || null;

  const pickFile = (next: File | null) => {
    if (!next) return;
    let chosen = next;
    if (!chosen.type.startsWith('image/')) {
      const ext = chosen.name.split('.').pop()?.toLowerCase() || '';
      const mime =
        ext === 'png' ? 'image/png' : ext === 'webp' ? 'image/webp' : ext === 'gif' ? 'image/gif' : ext === 'jpg' || ext === 'jpeg' ? 'image/jpeg' : '';
      if (!mime) {
        setError('Chỉ nhận file ảnh.');
        return;
      }
      chosen = new File([chosen], chosen.name, { type: mime });
    }
    if (chosen.size > 12 * 1024 * 1024) {
      setError('Ảnh lớn hơn 12MB.');
      return;
    }
    setError(null);
    setFile(chosen);
  };

  const pickLocalFile = (next: File | null) => {
    fileFromUrlRef.current = false;
    lastFetchedUrlRef.current = null;
    inflightUrlRef.current = null;
    setLinkBusy(false);
    setImageUrl('');
    pickFile(next);
  };

  const applyUrl = useCallback(async (rawInput: string) => {
    const raw = rawInput.trim();
    if (!raw) return;
    if (!looksLikeHttpUrl(raw)) {
      setError('Link cần bắt đầu bằng http:// hoặc https://');
      return;
    }
    if (raw === lastFetchedUrlRef.current || inflightUrlRef.current === raw) return;
    inflightUrlRef.current = raw;
    setLinkBusy(true);
    setError(null);
    try {
      const next = await adminProductAPI.fetchImageLocalizationTrialSource(raw);
      if (inflightUrlRef.current !== raw || imageUrlRef.current.trim() !== raw) return;
      lastFetchedUrlRef.current = raw;
      fileFromUrlRef.current = true;
      setFile(next);
    } catch (err) {
      if (inflightUrlRef.current === raw) {
        lastFetchedUrlRef.current = null;
        setError(err instanceof Error ? err.message : 'Không tải được ảnh từ link');
      }
    } finally {
      if (inflightUrlRef.current === raw) {
        inflightUrlRef.current = null;
        setLinkBusy(false);
      }
    }
  }, []);

  useEffect(() => {
    const raw = imageUrl.trim();
    if (!raw) {
      if (fileFromUrlRef.current) {
        fileFromUrlRef.current = false;
        lastFetchedUrlRef.current = null;
        setFile(null);
      }
      return;
    }
    if (!looksLikeHttpUrl(raw) || raw === lastFetchedUrlRef.current) return;
    const id = window.setTimeout(() => {
      void applyUrl(raw);
    }, 450);
    return () => window.clearTimeout(id);
  }, [imageUrl, applyUrl]);

  const onZonePaste = (event: React.ClipboardEvent) => {
    const image = clipboardImageFile(event.clipboardData);
    if (image) {
      event.preventDefault();
      event.stopPropagation();
      pickLocalFile(image);
      return;
    }
    if (event.target === urlInputRef.current) return;
    const text = event.clipboardData.getData('text/plain').trim();
    if (looksLikeHttpUrl(text)) {
      event.preventDefault();
      setError(null);
      setImageUrl(text);
    }
  };

  const run = async () => {
    if (!file || busy) return;
    setBusy(true);
    setError(null);
    try {
      const created = await adminProductAPI.runImageLocalizationTrial(file, {
        language,
        mode,
        openai_image_model: openaiModel.trim() || undefined,
        openai_image_quality: openaiQuality.trim() || undefined,
        openai_image_size: openaiSize.trim() || undefined,
      });
      setItems((prev) => [created, ...prev.filter((row) => row.id !== created.id)]);
      setSelectedId(created.id);
      fileFromUrlRef.current = false;
      lastFetchedUrlRef.current = null;
      setImageUrl('');
      setFile(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không chạy được ảnh thử');
    } finally {
      setBusy(false);
    }
  };

  const remove = async (trialId: string) => {
    try {
      await adminProductAPI.deleteImageLocalizationTrial(trialId);
      setItems((prev) => prev.filter((row) => row.id !== trialId));
      setSelectedId((current) => (current === trialId ? null : current));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không xóa được ảnh thử');
    }
  };

  const openSlides = (next: Slide[], index = 0) => {
    if (!next.length) return;
    setSlides(next);
    setSlideIndex(Math.min(index, next.length - 1));
  };

  useEffect(() => {
    if (!slides) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setSlides(null);
      if (event.key === 'ArrowRight') setSlideIndex((index) => Math.min(slides.length - 1, index + 1));
      if (event.key === 'ArrowLeft') setSlideIndex((index) => Math.max(0, index - 1));
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [slides]);

  const allSlides = useMemo(() => slidesFor(items), [items]);

  return (
    <section className="mt-4 border-t border-gray-100 pt-4" aria-labelledby="image-loc-trial-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 id="image-loc-trial-title" className="text-sm font-semibold text-gray-900">
            Cổng thử một ảnh
          </h3>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-gray-600">
            Đưa một ảnh rồi chạy. Job chỉ xử lý ảnh đó, theo chế độ đang chọn phía trên:{' '}
            <span className="font-medium text-gray-800">{modeLabel(mode)}</span>. Ảnh gốc và ảnh kết quả lưu trong thư
            mục thử và tự xóa sau 7 ngày.
          </p>
        </div>
        <button
          type="button"
          onClick={() => openSlides(allSlides)}
          disabled={allSlides.length === 0}
          className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
        >
          Mở hết ảnh thử
        </button>
      </div>

      <div
        className={`mt-3 rounded-xl border border-dashed px-4 py-4 ${
          dragOver ? 'border-violet-400 bg-violet-50' : 'border-gray-300 bg-gray-50'
        }`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragOver(false);
          const dropped = event.dataTransfer.files?.[0] || null;
          if (dropped) {
            pickLocalFile(dropped);
            return;
          }
          const text = event.dataTransfer.getData('text/plain').trim();
          if (looksLikeHttpUrl(text)) {
            setError(null);
            setImageUrl(text);
          }
        }}
        onPaste={onZonePaste}
        onMouseDown={(event) => {
          const target = event.target as HTMLElement;
          if (target.closest('button, label, input, a')) return;
          urlInputRef.current?.focus();
        }}
      >
        <div className="flex flex-wrap items-center gap-3">
          {localPreview ? (
            <img src={localPreview} alt="Ảnh sắp chạy" className="h-16 w-16 rounded-lg object-cover" />
          ) : (
            <div className="flex h-16 w-16 items-center justify-center rounded-lg bg-white text-[11px] text-gray-400">
              Ảnh
            </div>
          )}
          <div className="min-w-0">
            <p className="truncate text-sm text-gray-800">{file ? file.name : 'Kéo ảnh vào đây hoặc chọn file'}</p>
            <p className="mt-0.5 text-xs text-gray-500">
              {linkBusy ? 'Đang tải ảnh từ link…' : 'JPG, PNG, WebP. Tối đa 12MB.'}
            </p>
          </div>
          <input
            ref={urlInputRef}
            type="url"
            inputMode="url"
            autoComplete="off"
            placeholder="Dán link ảnh hoặc Ctrl+V"
            aria-label="Dán link ảnh hoặc Ctrl+V"
            value={imageUrl}
            disabled={busy || linkBusy}
            onChange={(event) => {
              setImageUrl(event.target.value);
              setError(null);
            }}
            onPaste={(event) => {
              const image = clipboardImageFile(event.clipboardData);
              if (!image) return;
              event.preventDefault();
              event.stopPropagation();
              pickLocalFile(image);
            }}
            onKeyDown={(event) => {
              if (event.key !== 'Enter') return;
              event.preventDefault();
              void applyUrl(imageUrl);
            }}
            className="min-w-[16rem] flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-200 disabled:opacity-60"
          />
          <label className="cursor-pointer rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">
            Chọn ảnh
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="sr-only"
              onChange={(event) => {
                pickLocalFile(event.target.files?.[0] || null);
                event.target.value = '';
              }}
            />
          </label>
          <button
            type="button"
            onClick={() => void run()}
            disabled={!file || busy || linkBusy}
            className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-60"
          >
            {busy ? 'Đang chạy…' : 'Chạy ảnh này'}
          </button>
        </div>
      </div>

      {error ? (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}{' '}
          <button type="button" onClick={() => void load()} className="font-medium underline">
            Tải lại
          </button>
        </div>
      ) : null}
      {listError ? (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {listError}{' '}
          <button type="button" onClick={() => void load()} className="font-medium underline">
            Thử lại
          </button>
        </div>
      ) : null}

      {selected ? <TrialDetail trial={selected} onOpen={openSlides} onDelete={() => void remove(selected.id)} /> : null}

      <div className="mt-4">
        <p className="text-xs font-medium text-gray-700">Ảnh trong 7 ngày</p>
        {items.length === 0 ? (
          <p className="mt-2 text-sm text-gray-500">Chưa có ảnh thử.</p>
        ) : (
          <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
            {items.map((trial) => (
              <button
                key={trial.id}
                type="button"
                onClick={() => setSelectedId(trial.id)}
                className={`w-28 shrink-0 overflow-hidden rounded-lg border bg-white text-left ${
                  trial.id === selectedId ? 'border-violet-500 ring-2 ring-violet-200' : 'border-gray-200'
                }`}
              >
                <div className="h-20 bg-gray-100">
                  <TrialThumb trial={trial} />
                </div>
                <div className="space-y-1 px-2 py-1.5">
                  <span className={`inline-flex rounded px-1.5 py-0.5 text-[10px] font-semibold ${engineClass(trial.engine)}`}>
                    {ENGINE_LABEL[trial.engine] || trial.engine}
                  </span>
                  <p className="truncate text-[11px] text-gray-600">{trial.filename}</p>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {slides ? (
        <TrialLightbox
          slides={slides}
          index={slideIndex}
          onClose={() => setSlides(null)}
          onIndex={setSlideIndex}
        />
      ) : null}
    </section>
  );
}

function TrialDetail({
  trial,
  onOpen,
  onDelete,
}: {
  trial: AdminImageLocalizationTrial;
  onOpen: (slides: Slide[], index?: number) => void;
  onDelete: () => void;
}) {
  const sourceUrl = useTrialImage(trial.id, trial.files.source ? 'source' : null);
  const resultUrl = useTrialImage(trial.id, trial.files.result ? 'result' : null);
  const pair = slidesFor([trial]);
  return (
    <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1.1fr)_minmax(16rem,0.9fr)]">
      <div className="rounded-xl border border-gray-200 bg-white p-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`rounded px-2 py-0.5 text-xs font-semibold ${engineClass(trial.engine)}`}>
            {ENGINE_LABEL[trial.engine] || trial.engine}
          </span>
          <span className="text-xs text-gray-600">{trial.model || 'Không gọi model ảnh'}</span>
          <span className="text-xs text-gray-400">{whenLabel(trial.created_at)}</span>
          <span className="text-xs text-gray-400">{expiresLabel(trial.expires_at)}</span>
          <span className="text-xs text-gray-400">{Math.round(trial.elapsed_ms / 100) / 10}s</span>
        </div>
        <p className="mt-2 text-sm text-gray-800">{trial.message || trial.status}</p>
        <div className="mt-3 grid grid-cols-2 gap-2">
          <figure>
            <button
              type="button"
              className="block w-full overflow-hidden rounded-lg bg-gray-100"
              onClick={() => onOpen(pair, 0)}
              disabled={!sourceUrl}
            >
              {sourceUrl ? (
                <img src={sourceUrl} alt="Ảnh gốc" className="max-h-72 w-full object-contain" />
              ) : (
                <div className="h-40 animate-pulse bg-gray-100" />
              )}
            </button>
            <figcaption className="mt-1 text-center text-[11px] text-gray-500">Ảnh gốc</figcaption>
          </figure>
          <figure>
            <button
              type="button"
              className="block w-full overflow-hidden rounded-lg bg-gray-100"
              onClick={() => onOpen(pair, pair.length > 1 ? 1 : 0)}
              disabled={!resultUrl}
            >
              {resultUrl ? (
                <img src={resultUrl} alt="Ảnh kết quả" className="max-h-72 w-full object-contain" />
              ) : (
                <div className="flex h-40 items-center justify-center text-xs text-gray-400">Không có ảnh kết quả</div>
              )}
            </button>
            <figcaption className="mt-1 text-center text-[11px] text-gray-500">Kết quả</figcaption>
          </figure>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onOpen(pair)}
            disabled={pair.length === 0}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            Mở ảnh lần này
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="rounded-lg border border-red-200 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50"
          >
            Xóa ngay
          </button>
        </div>
      </div>
      <div className="rounded-xl border border-gray-200 bg-gray-950 p-3 text-gray-100">
        <p className="text-xs font-semibold text-gray-300">Log chạy</p>
        <ol className="mt-2 max-h-80 space-y-1 overflow-auto font-mono text-[11px] leading-relaxed">
          {trial.logs.length === 0 ? <li className="text-gray-500">Không có log.</li> : null}
          {trial.logs.map((line, index) => (
            <li key={`${trial.id}-${index}`} className="whitespace-pre-wrap break-words text-gray-200">
              {line}
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

function TrialLightbox({
  slides,
  index,
  onClose,
  onIndex,
}: {
  slides: Slide[];
  index: number;
  onClose: () => void;
  onIndex: (index: number) => void;
}) {
  const slide = slides[index];
  const url = useTrialImage(slide?.trialId || '', slide?.kind || null);
  if (!slide) return null;
  return (
    <div className="fixed inset-0 z-[120] flex flex-col bg-black/80 p-4" role="dialog" aria-modal="true" aria-label="Ảnh thử">
      <div className="flex items-center justify-between gap-3 text-white">
        <p className="min-w-0 truncate text-sm">
          {slide.caption} · {slide.title} · {index + 1}/{slides.length}
        </p>
        <button type="button" onClick={onClose} className="rounded-lg bg-white/10 px-3 py-1.5 text-sm hover:bg-white/20">
          Đóng
        </button>
      </div>
      <div className="flex min-h-0 flex-1 items-center justify-center gap-3 py-4">
        <button
          type="button"
          onClick={() => onIndex(Math.max(0, index - 1))}
          disabled={index === 0}
          className="rounded-full bg-white/10 px-3 py-2 text-white disabled:opacity-30"
          aria-label="Ảnh trước"
        >
          ‹
        </button>
        {url ? (
          <img src={url} alt={slide.caption} className="max-h-full max-w-[min(100%,960px)] object-contain" />
        ) : (
          <p className="text-sm text-white/70">Đang tải ảnh…</p>
        )}
        <button
          type="button"
          onClick={() => onIndex(Math.min(slides.length - 1, index + 1))}
          disabled={index >= slides.length - 1}
          className="rounded-full bg-white/10 px-3 py-2 text-white disabled:opacity-30"
          aria-label="Ảnh sau"
        >
          ›
        </button>
      </div>
    </div>
  );
}
