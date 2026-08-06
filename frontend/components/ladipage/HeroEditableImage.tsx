'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Image from 'next/image';

import type { HeroImageOption } from '@/components/ladipage/types';
import { formatHeroObjectPosition, parseHeroObjectPosition } from '@/lib/ladipage-utils';

interface HeroEditableImageProps {
  src?: string | null;
  objectPosition?: string | null;
  alt: string;
  aspectClassName?: string;
  imageOptions: HeroImageOption[];
  isBusy?: boolean;
  onSelectImage: (url: string) => void | Promise<void>;
  onSavePosition: (position: string) => void | Promise<void>;
}

export default function HeroEditableImage({
  src,
  objectPosition,
  alt,
  aspectClassName = 'aspect-[4/3]',
  imageOptions,
  isBusy = false,
  onSelectImage,
  onSavePosition,
}: HeroEditableImageProps) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState(() => parseHeroObjectPosition(objectPosition));
  const posRef = useRef(pos);
  const draggingRef = useRef(false);
  const movedRef = useRef(false);
  const frameRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const next = parseHeroObjectPosition(objectPosition);
    setPos(next);
    posRef.current = next;
  }, [objectPosition]);

  const positionStyle = formatHeroObjectPosition(pos.x, pos.y);
  posRef.current = pos;

  const updatePosFromPointer = useCallback((clientX: number, clientY: number) => {
    const el = frameRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;
    const x = ((clientX - rect.left) / rect.width) * 100;
    const y = ((clientY - rect.top) / rect.height) * 100;
    const next = { x, y };
    setPos(next);
    posRef.current = next;
  }, []);

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!open || !src || isBusy) return;
    e.preventDefault();
    draggingRef.current = true;
    movedRef.current = false;
    frameRef.current?.setPointerCapture(e.pointerId);
    updatePosFromPointer(e.clientX, e.clientY);
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!draggingRef.current) return;
    movedRef.current = true;
    updatePosFromPointer(e.clientX, e.clientY);
  };

  const finishDrag = async (pointerId: number) => {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    try {
      frameRef.current?.releasePointerCapture(pointerId);
    } catch {
      /* ignore */
    }
    if (movedRef.current) {
      await onSavePosition(formatHeroObjectPosition(posRef.current.x, posRef.current.y));
    }
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    void finishDrag(e.pointerId);
  };

  const handlePointerCancel = (e: React.PointerEvent<HTMLDivElement>) => {
    void finishDrag(e.pointerId);
  };

  const handleFrameClick = () => {
    if (isBusy) return;
    setOpen(true);
  };

  const handleSelectImage = async (url: string) => {
    if (isBusy || url === src) return;
    await onSelectImage(url);
    const centered = { x: 50, y: 50 };
    setPos(centered);
    posRef.current = centered;
    await onSavePosition(formatHeroObjectPosition(centered.x, centered.y));
  };

  return (
    <div>
      <div
        ref={frameRef}
        role="button"
        tabIndex={0}
        aria-label="Chọn và chỉnh ảnh hero"
        onClick={handleFrameClick}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            handleFrameClick();
          }
        }}
        onPointerDown={open && src ? handlePointerDown : undefined}
        onPointerMove={open && src ? handlePointerMove : undefined}
        onPointerUp={open && src ? handlePointerUp : undefined}
        onPointerCancel={open && src ? handlePointerCancel : undefined}
        className={`group/hero relative overflow-hidden rounded-xl bg-gray-100 ${aspectClassName} ${
          open && src ? 'cursor-grab ring-2 ring-orange-400 active:cursor-grabbing' : 'cursor-pointer'
        }`}
      >
        {src ? (
          <Image
            src={src}
            alt={alt}
            fill
            sizes="(max-width: 768px) 100vw, 50vw"
            className="pointer-events-none object-cover"
            style={{ objectPosition: positionStyle }}
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center px-4 text-center text-sm text-gray-400">
            {isBusy ? 'Đang tải…' : 'Bấm để chọn ảnh sản phẩm'}
          </div>
        )}

        {open && src ? (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute h-3.5 w-3.5 rounded-full border-2 border-white bg-orange-500 shadow-md"
            style={{
              left: `${pos.x}%`,
              top: `${pos.y}%`,
              transform: 'translate(-50%, -50%)',
            }}
          />
        ) : null}

        {isBusy ? (
          <div className="absolute inset-0 flex items-center justify-center bg-white/70">
            <span className="h-7 w-7 animate-spin rounded-full border-2 border-orange-500 border-t-transparent" />
          </div>
        ) : null}

        {!open && !isBusy ? (
          <div className="pointer-events-none absolute inset-x-0 bottom-0 flex justify-center bg-gradient-to-t from-black/45 to-transparent px-3 pb-3 pt-8 opacity-0 transition group-hover/hero:opacity-100">
            <span className="rounded-full bg-black/70 px-3 py-1 text-xs font-medium text-white">
              Bấm để chọn &amp; chỉnh ảnh
            </span>
          </div>
        ) : null}
      </div>

      {open ? (
        <div className="mt-3 rounded-xl border border-gray-200 bg-white p-3 shadow-sm">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs font-medium text-gray-700">
              Chọn ảnh từ sản phẩm · Kéo ảnh phía trên để chỉnh vị trí hiển thị
            </p>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded-md px-2 py-1 text-xs font-medium text-gray-600 hover:bg-gray-100"
            >
              Xong
            </button>
          </div>

          {imageOptions.length === 0 ? (
            <p className="text-xs text-gray-400">Chưa có ảnh sản phẩm trên ladipage này.</p>
          ) : (
            <div className="flex gap-2 overflow-x-auto pb-1">
              {imageOptions.map((opt) => {
                const selected = src === opt.url;
                return (
                  <button
                    key={`${opt.productId}-${opt.url}`}
                    type="button"
                    title={`${opt.productName} — ${opt.label}`}
                    disabled={isBusy}
                    onClick={(e) => {
                      e.stopPropagation();
                      void handleSelectImage(opt.url);
                    }}
                    className={`relative h-20 w-20 shrink-0 overflow-hidden rounded-lg border-2 transition disabled:opacity-50 ${
                      selected ? 'border-orange-500 ring-2 ring-orange-200' : 'border-gray-200 hover:border-orange-300'
                    }`}
                  >
                    <Image src={opt.url} alt={opt.productName} fill className="object-cover" sizes="80px" />
                    <span className="absolute inset-x-0 bottom-0 truncate bg-black/65 px-1 py-0.5 text-[10px] text-white">
                      {opt.label}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
