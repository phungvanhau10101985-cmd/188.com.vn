'use client';

import dynamic from 'next/dynamic';
import { useEffect, useState } from 'react';

const DesktopImageSearchPopover = dynamic(
  () => import('@/components/DesktopImageSearchPopover'),
  {
    ssr: false,
    loading: () => (
      <div className="absolute right-11 top-1/2 -translate-y-1/2">
        <span
          className="inline-flex h-9 w-9 items-center justify-center rounded-md bg-black/[0.06]"
          aria-hidden
        />
      </div>
    ),
  }
);

type Props = {
  triggerButtonClassName?: string;
  panelZClass?: string;
};

const DEFAULT_TRIGGER =
  'text-gray-500 hover:text-[#ea580c] p-1 rounded-md focus:outline-none focus:ring-2 focus:ring-[#ea580c]/40';

/**
 * Trì hoãn tải bundle tìm theo ảnh (fetch ảnh, nanoai-pending) đến khi người dùng bấm máy ảnh —
 * giảm JS parse/hydrate trên luồng chính cho Lighthouse / TBT.
 */
export default function LazyDesktopImageSearchPopover({
  triggerButtonClassName = DEFAULT_TRIGGER,
  panelZClass,
}: Props) {
  const [active, setActive] = useState(false);

  useEffect(() => {
    const w = typeof window !== 'undefined' ? window : null;
    if (!w) return;
    const ric = w.requestIdleCallback?.bind(w);
    let idleId: ReturnType<typeof requestIdleCallback> | undefined;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    const warm = () => {
      void import('@/components/DesktopImageSearchPopover');
    };
    if (ric) idleId = ric(warm, { timeout: 4500 });
    else timeoutId = setTimeout(warm, 2800);
    return () => {
      if (idleId != null && w.cancelIdleCallback) w.cancelIdleCallback(idleId);
      if (timeoutId != null) clearTimeout(timeoutId);
    };
  }, []);

  if (!active) {
    return (
      <div className="absolute right-11 top-1/2 -translate-y-1/2">
        <button
          type="button"
          onClick={() => setActive(true)}
          className={triggerButtonClassName}
          aria-label="Tìm kiếm bằng ảnh"
          aria-expanded={false}
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
      </div>
    );
  }

  return (
    <DesktopImageSearchPopover
      triggerButtonClassName={triggerButtonClassName}
      panelZClass={panelZClass}
      initialOpen
    />
  );
}
