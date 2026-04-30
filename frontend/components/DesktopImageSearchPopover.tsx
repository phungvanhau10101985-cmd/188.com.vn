'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { imageUrlToFile, looksLikeHttpUrl } from '@/lib/image-from-url';
import { storePendingImageAndNavigate } from '@/lib/nanoai-pending-image';

interface DesktopImageSearchPopoverProps {
  /** Class cho nút máy ảnh (absolute positioning do form cha xử lý) */
  triggerButtonClassName?: string;
  /** z-index cho panel (thanh sticky cần cao hơn header) */
  panelZClass?: string;
  /** Mount sau lazy-load: mở panel ngay (giữ UX một lần bấm máy ảnh). */
  initialOpen?: boolean;
}

/**
 * Desktop: nút máy ảnh mở panel — một khung dán ảnh/link + kéo thả + chọn file.
 * Dùng trong Header và thanh Navigation sticky.
 */
export default function DesktopImageSearchPopover({
  triggerButtonClassName = 'text-gray-500 hover:text-[#ea580c] p-1 rounded-md focus:outline-none focus:ring-2 focus:ring-[#ea580c]/40',
  panelZClass = 'z-[100]',
  initialOpen = false,
}: DesktopImageSearchPopoverProps) {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const anchorRef = useRef<HTMLDivElement>(null);
  const pasteRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(initialOpen);
  const [panelError, setPanelError] = useState<string | null>(null);
  const [panelBusy, setPanelBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (anchorRef.current?.contains(e.target as Node)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(() => pasteRef.current?.focus(), 0);
    return () => window.clearTimeout(t);
  }, [open]);

  const onFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = '';
    if (!f) return;
    setPanelError(null);
    try {
      await storePendingImageAndNavigate(f, router);
      setOpen(false);
    } catch {
      router.push('/tim-theo-anh');
      setOpen(false);
    }
  };

  const fetchUrlAndNavigate = useCallback(async (raw: string) => {
    const t = raw.trim();
    if (!t) {
      setPanelError('Dán link ảnh (https://…) vào khung bên dưới.');
      return;
    }
    if (!looksLikeHttpUrl(t)) {
      setPanelError('Link cần bắt đầu bằng http:// hoặc https://');
      return;
    }
    setPanelError(null);
    setPanelBusy(true);
    try {
      const file = await imageUrlToFile(t);
      await storePendingImageAndNavigate(file, router);
      setOpen(false);
    } catch (err) {
      setPanelError(
        err instanceof Error
          ? err.message
          : 'Không tải được ảnh (CORS hoặc link không hợp lệ). Thử lưu ảnh về máy rồi «Chọn ảnh».'
      );
    } finally {
      setPanelBusy(false);
    }
  }, [router]);

  const runPendingNavigate = useCallback(
    async (file: File) => {
      setPanelError(null);
      try {
        await storePendingImageAndNavigate(file, router);
        setOpen(false);
      } catch {
        setPanelError('Không xử lý được ảnh. Thử file nhỏ hơn hoặc JPEG/PNG.');
      }
    },
    [router]
  );

  const onPaste = (e: React.ClipboardEvent) => {
    const cd = e.clipboardData;
    if (!cd) return;
    for (const it of Array.from(cd.items)) {
      if (it.kind === 'file' && it.type.startsWith('image/')) {
        const f = it.getAsFile();
        if (f) {
          e.preventDefault();
          void runPendingNavigate(f);
          return;
        }
      }
    }
    for (const f of Array.from(cd.files)) {
      if (f.type.startsWith('image/')) {
        e.preventDefault();
        void runPendingNavigate(f);
        return;
      }
    }
    const text = cd.getData('text/plain')?.trim() ?? '';
    if (looksLikeHttpUrl(text)) {
      e.preventDefault();
      void fetchUrlAndNavigate(text);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (f?.type.startsWith('image/')) void runPendingNavigate(f);
  };

  return (
    <>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp,image/gif"
        className="hidden"
        aria-hidden
        onChange={onFileChange}
      />
      <div ref={anchorRef} className="absolute right-11 top-1/2 -translate-y-1/2">
        <button
          type="button"
          onClick={() => {
            setOpen((o) => !o);
            setPanelError(null);
          }}
          className={triggerButtonClassName}
          aria-label="Tìm kiếm bằng ảnh"
          aria-expanded={open}
          aria-haspopup="dialog"
          title="Tìm theo ảnh"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z"
            />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
        </button>
        {open && (
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Tìm kiếm bằng ảnh"
            className={`absolute right-0 top-full mt-2 ${panelZClass} w-[min(calc(100vw-2rem),20rem)] rounded-xl border border-gray-200 bg-white shadow-xl shadow-black/15 p-4 text-left`}
          >
            <div className="flex items-start justify-between gap-2 mb-3">
              <h2 className="text-sm font-bold text-gray-900 leading-tight">Tìm theo ảnh</h2>
              <button
                type="button"
                className="text-gray-400 hover:text-gray-700 text-lg leading-none px-1 rounded focus:outline-none focus:ring-2 focus:ring-[#ea580c]/30"
                aria-label="Đóng"
                onClick={() => setOpen(false)}
              >
                ×
              </button>
            </div>
            <div
              ref={pasteRef}
              tabIndex={0}
              onPaste={onPaste}
              onDragOver={(e) => e.preventDefault()}
              onDrop={onDrop}
              className="rounded-xl border-2 border-dashed border-[#ea580c]/80 bg-orange-50/50 px-4 py-4 text-center outline-none focus-visible:border-[#ea580c] focus-visible:ring-2 focus-visible:ring-[#ea580c]/25"
              aria-label="Dán ảnh, dán link ảnh hoặc kéo thả file ảnh vào đây"
            >
              <span className="font-semibold text-sm text-gray-900">Dán ảnh hoặc link</span>
              <span className="block mt-1.5 text-xs text-gray-600 leading-relaxed">
                Một chỗ duy nhất: <strong className="font-medium text-gray-800">Ctrl+V</strong> dán ảnh từ clipboard
                hoặc dán link <span className="whitespace-nowrap">(https://…)</span> — hoặc{' '}
                <strong className="font-medium text-gray-800">kéo thả</strong> ảnh vào khung này.
              </span>
              {panelBusy && (
                <span className="mt-2 inline-block text-xs text-[#ea580c] font-medium">Đang tải ảnh…</span>
              )}
            </div>
            <button
              type="button"
              disabled={panelBusy}
              onClick={() => fileInputRef.current?.click()}
              className="mt-3 w-full rounded-lg bg-[#ea580c] text-white text-sm font-medium py-2.5 hover:bg-orange-600 disabled:opacity-50"
            >
              Chọn ảnh từ máy
            </button>
            {panelError && (
              <p className="mt-2 text-xs text-red-600" role="alert">
                {panelError}
              </p>
            )}
          </div>
        )}
      </div>
    </>
  );
}
