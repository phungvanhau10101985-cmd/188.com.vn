'use client';

import { useState } from 'react';
import Image from 'next/image';

interface EditableImageProps {
  src?: string | null;
  alt: string;
  className?: string;
  editable?: boolean;
  isBusy?: boolean;
  initialPrompt?: string;
  onRegenerate?: (prompt: string) => void | Promise<void>;
  aspectClassName?: string;
}

/** Ảnh AI: hiển thị bình thường; ở chế độ editable cho phép nhập prompt và tạo lại ngay tại chỗ. */
export default function EditableImage({
  src,
  alt,
  className = '',
  editable = false,
  isBusy = false,
  initialPrompt = '',
  onRegenerate,
  aspectClassName = 'aspect-square',
}: EditableImageProps) {
  const [showPopover, setShowPopover] = useState(false);
  const [prompt, setPrompt] = useState(initialPrompt);

  return (
    <div className={`group/img relative overflow-hidden rounded-xl bg-gray-100 ${aspectClassName} ${className}`}>
      {src ? (
        <Image
          src={src}
          alt={alt}
          fill
          sizes="(max-width: 768px) 100vw, 50vw"
          className="object-cover"
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center px-4 text-center text-sm text-gray-400">
          {isBusy ? 'Đang tạo ảnh bằng AI…' : 'Chưa có ảnh'}
        </div>
      )}

      {isBusy && (
        <div className="absolute inset-0 flex items-center justify-center bg-white/70">
          <span className="h-7 w-7 animate-spin rounded-full border-2 border-orange-500 border-t-transparent" />
        </div>
      )}

      {editable && onRegenerate && !isBusy && !showPopover && (
        <button
          type="button"
          onClick={() => setShowPopover(true)}
          className="absolute bottom-2 right-2 rounded-full bg-black/70 px-3 py-1 text-xs font-medium text-white opacity-0 shadow transition group-hover/img:opacity-100"
        >
          ✨ Tạo lại ảnh
        </button>
      )}

      {showPopover && onRegenerate && (
        <div className="absolute inset-x-2 bottom-2 z-20 rounded-lg border border-gray-200 bg-white p-3 shadow-xl">
          <label className="mb-1 block text-xs font-medium text-gray-600">Mô tả ảnh muốn AI tạo</label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            className="mb-2 w-full rounded-md border border-gray-300 p-2 text-xs text-gray-800 outline-none focus:border-orange-400"
            rows={3}
          />
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setShowPopover(false)}
              className="rounded-md px-2 py-1 text-xs text-gray-500 hover:bg-gray-100"
            >
              Hủy
            </button>
            <button
              type="button"
              onClick={async () => {
                setShowPopover(false);
                await onRegenerate(prompt.trim());
              }}
              className="rounded-md bg-orange-600 px-3 py-1 text-xs font-medium text-white hover:bg-orange-700"
            >
              Tạo lại ảnh
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
