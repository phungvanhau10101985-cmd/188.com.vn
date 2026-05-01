'use client';

import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { apiClient, NANOAI_IMAGE_SEARCH_LIMIT } from '@/lib/api-client';
import { consumePendingImageFile, NANOAI_PENDING_IMAGE_EVENT } from '@/lib/nanoai-pending-image';
import NanoaiSimilarProductCard from '@/components/NanoaiSimilarProductCard';
import type { NanoaiSearchProduct } from '@/types/api';
import { useLazyRevealList } from '@/hooks/useLazyRevealList';
import { imageUrlToFile, looksLikeHttpUrl } from '@/lib/image-from-url';
import {
  humanizeNanoaiImageSearchError,
  shouldRetryNanoaiGeminiTransient,
} from '@/lib/nanoai-search-errors';

const RETRY_AFTER_MS = 2500;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

/** Ảnh từ Header qua sessionStorage (consumePendingImageFile). */
export default function TimTheoAnhPage() {
  const timAnhFileInputId = useId();
  const urlInputRef = useRef<HTMLInputElement>(null);

  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [softMessage, setSoftMessage] = useState<string | null>(null);
  const [products, setProducts] = useState<NanoaiSearchProduct[]>([]);
  const [imageUrlInput, setImageUrlInput] = useState('');

  const lastAutoFetchedUrlRef = useRef<string | null>(null);
  const linkSearchBusyRef = useRef(false);

  const runSearch = useCallback(async (file: File) => {
    setLoading(true);
    setError(null);
    setSoftMessage(null);
    setProducts([]);
    try {
      const url = URL.createObjectURL(file);
      setPreviewUrl((prev) => {
        if (prev && prev.startsWith('blob:')) URL.revokeObjectURL(prev);
        return url;
      });

      let lastErr: string | null = null;

      for (let attempt = 0; attempt < 2; attempt++) {
        const res = await apiClient.nanoaiImageSearch(file, NANOAI_IMAGE_SEARCH_LIMIT);
        const list = Array.isArray(res.products) ? res.products : [];
        const errRaw = res.error ? String(res.error) : '';

        if (list.length > 0) {
          setProducts(list);
          if (attempt > 0) {
            setSoftMessage(null);
          }
          break;
        }

        lastErr = errRaw || null;

        const transient = shouldRetryNanoaiGeminiTransient(lastErr);
        if (transient && attempt === 0) {
          setSoftMessage('Đang thử lại sau lỗi tạm thời…');
          await sleep(RETRY_AFTER_MS);
          continue;
        }

        setProducts([]);
        if (lastErr) {
          setSoftMessage(humanizeNanoaiImageSearchError(lastErr));
        }
        break;
      }
    } catch (e) {
      const raw = e instanceof Error ? e.message : 'Không tìm được. Vui lòng thử lại.';
      setError(humanizeNanoaiImageSearchError(raw) || raw);
      setProducts([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const consume = () => {
      const file = consumePendingImageFile();
      if (file) void runSearch(file);
    };
    consume();
    window.addEventListener(NANOAI_PENDING_IMAGE_EVENT, consume);
    return () => window.removeEventListener(NANOAI_PENDING_IMAGE_EVENT, consume);
  }, [runSearch]);

  useEffect(() => {
    return () => {
      if (previewUrl && previewUrl.startsWith('blob:')) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const onFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = '';
    if (!f) return;
    await runSearch(f);
  };

  const fetchFromUrlString = useCallback(
    async (rawInput: string) => {
      if (linkSearchBusyRef.current) return;
      const raw = rawInput.trim();
      if (!raw) {
        setError('Nhập hoặc dán link ảnh (https://…).');
        return;
      }
      if (!looksLikeHttpUrl(raw)) {
        setError('Link cần bắt đầu bằng http:// hoặc https://');
        return;
      }
      setError(null);
      linkSearchBusyRef.current = true;
      try {
        const file = await imageUrlToFile(raw);
        await runSearch(file);
        lastAutoFetchedUrlRef.current = raw;
      } catch (e) {
        lastAutoFetchedUrlRef.current = null;
        setError(
          e instanceof Error
            ? e.message
            : 'Không tải được ảnh từ link (CORS hoặc link không hợp lệ).'
        );
      } finally {
        linkSearchBusyRef.current = false;
      }
    },
    [runSearch]
  );

  /** Gõ / dán link vào ô: sau ~0,5s mà chuỗi là URL hợp lệ thì tự tải ảnh và tìm (như chọn file). */
  useEffect(() => {
    const raw = imageUrlInput.trim();
    if (!raw) {
      lastAutoFetchedUrlRef.current = null;
      return;
    }
    if (!looksLikeHttpUrl(raw)) return;
    if (raw === lastAutoFetchedUrlRef.current) return;

    const id = window.setTimeout(() => {
      const latest = imageUrlInput.trim();
      if (latest !== raw) return;
      if (!looksLikeHttpUrl(latest)) return;
      if (latest === lastAutoFetchedUrlRef.current) return;
      void fetchFromUrlString(latest);
    }, 520);

    return () => window.clearTimeout(id);
  }, [imageUrlInput, fetchFromUrlString]);

  /** Dán ảnh (file) toàn trang; dán link chỉ trong ô URL (onChange + debounce). */
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const cd = e.clipboardData;
      if (!cd) return;

      const ae = document.activeElement as HTMLElement | null;
      const isOtherFormField =
        ae &&
        (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA' || ae.isContentEditable) &&
        ae !== urlInputRef.current;

      if (isOtherFormField) return;

      for (const it of Array.from(cd.items)) {
        if (it.kind === 'file' && it.type.startsWith('image/')) {
          const f = it.getAsFile();
          if (f) {
            e.preventDefault();
            void runSearch(f);
            return;
          }
        }
      }
      for (const f of Array.from(cd.files)) {
        if (f.type.startsWith('image/')) {
          e.preventDefault();
          void runSearch(f);
          return;
        }
      }
    };

    window.addEventListener('paste', onPaste);
    return () => window.removeEventListener('paste', onPaste);
  }, [runSearch]);

  const onThumbDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (f?.type.startsWith('image/')) await runSearch(f);
  };

  const { revealed, hasMore, sentinelRef, total } = useLazyRevealList(products, {
    initial: 12,
    step: 12,
  });

  return (
    <div className="max-w-7xl mx-auto px-3 pt-2 pb-4 sm:px-4 md:py-4">
      <header className="mb-2 md:mb-3">
        <h1 className="text-[15px] sm:text-base font-bold text-gray-900 leading-snug tracking-tight">
          Tìm theo ảnh
        </h1>
        <p className="text-[11px] text-gray-500 mt-0.5 leading-snug md:hidden">
          Tải ảnh, dán link vào ô bên dưới hoặc dán ảnh (Ctrl+V) — hệ thống tự tìm khi link hợp lệ
        </p>
      </header>

      <input
        id={timAnhFileInputId}
        type="file"
        accept="image/jpeg,image/png,image/webp,image/gif"
        className="sr-only"
        tabIndex={-1}
        onChange={onFileSelected}
      />

      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:gap-y-2 mb-3">
        <div className="flex items-center gap-2 shrink-0">
        <div
          className="w-14 h-14 sm:w-16 sm:h-16 rounded-md border border-gray-200 bg-gray-50 overflow-hidden flex-shrink-0 flex items-center justify-center"
          onDragOver={(e) => e.preventDefault()}
          onDrop={onThumbDrop}
          title="Ảnh đang dùng để tìm — kéo thả ảnh vào đây"
        >
          {previewUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={previewUrl} alt="Ảnh mẫu" className="w-full h-full object-cover" />
          ) : (
            <span className="text-[10px] text-gray-400 text-center leading-tight px-1 select-none">—</span>
          )}
        </div>

        <label
          htmlFor={timAnhFileInputId}
          className={`min-h-[44px] sm:min-h-0 text-sm font-medium px-3 py-2 rounded-md bg-[#ea580c] text-white hover:bg-orange-600 cursor-pointer inline-flex items-center justify-center ${
            loading ? 'opacity-50 pointer-events-none' : ''
          }`}
        >
          Tải ảnh
        </label>
        </div>

        <div className="flex flex-1 min-w-0 w-full sm:min-w-[min(100%,12rem)] sm:max-w-xl">
          <input
            ref={urlInputRef}
            type="url"
            inputMode="url"
            autoComplete="off"
            placeholder="Dán link ảnh https://… — tự tìm sau khi dán"
            value={imageUrlInput}
            onChange={(e) => {
              setImageUrlInput(e.target.value);
              setError(null);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                lastAutoFetchedUrlRef.current = null;
                void fetchFromUrlString(imageUrlInput);
              }
            }}
            className="flex-1 min-w-0 w-full min-h-[44px] sm:min-h-0 text-sm py-2 px-2.5 rounded-md border border-gray-200 text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-[#ea580c]/30 focus:border-[#ea580c]"
          />
        </div>
      </div>

      {error && (
        <p className="text-xs text-red-600 mb-2" role="alert">
          {error}
        </p>
      )}

      {softMessage && !error && products.length === 0 && !loading && (
        <p className="text-xs text-amber-800 mb-2" role="status">
          {softMessage}
        </p>
      )}

      <section aria-live="polite" className="mt-2">
        <h2 className="text-sm font-bold text-gray-900 mb-2 border-b border-[#ea580c]/40 pb-1 w-fit">
          {loading ? 'Đang tìm…' : `Kết quả (${products.length})`}
        </h2>

        {loading ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-4">
            {[...Array(10)].map((_, i) => (
              <div key={i} className="bg-white rounded-xl border border-gray-100 overflow-hidden animate-pulse">
                <div className="aspect-square bg-gray-100" />
                <div className="p-3 space-y-2">
                  <div className="h-3 bg-gray-100 rounded w-3/4" />
                  <div className="h-3 bg-gray-100 rounded w-full" />
                </div>
              </div>
            ))}
          </div>
        ) : products.length > 0 ? (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-4">
              {revealed.map((item, i) => (
                <NanoaiSimilarProductCard
                  key={item.inventory_id || `${item.sku || item.name || i}-${i}`}
                  item={item}
                />
              ))}
            </div>
            {hasMore ? (
              <p className="text-center text-xs text-gray-500 py-3" aria-live="polite">
                {revealed.length} / {total} — kéo xuống để xem thêm
              </p>
            ) : null}
            <div ref={sentinelRef} className="h-4 w-full" aria-hidden />
          </>
        ) : !loading && !error && !softMessage ? (
          <p className="text-xs text-gray-500 py-6 text-center">Chưa có kết quả.</p>
        ) : null}
      </section>
    </div>
  );
}
