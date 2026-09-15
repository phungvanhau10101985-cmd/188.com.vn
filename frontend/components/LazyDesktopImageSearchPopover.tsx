'use client';

import { useEffect, useState, type ComponentType } from 'react';

type Props = {
  triggerButtonClassName?: string;
  triggerIconClassName?: string;
  wrapperClassName?: string;
  panelZClass?: string;
  triggerPosition?: 'overlay-right' | 'inline-end';
};

const DEFAULT_TRIGGER =
  'text-gray-500 hover:text-[#ea580c] p-1 rounded-md focus:outline-none focus:ring-2 focus:ring-[#ea580c]/40';
const DEFAULT_ICON = 'w-5 h-5';

type PopoverProps = Props & { initialOpen?: boolean };

function triggerWrapClass(props: Props): string {
  if (props.wrapperClassName) return props.wrapperClassName;
  return props.triggerPosition === 'inline-end'
    ? 'relative inline-flex shrink-0 items-center'
    : 'absolute right-11 top-1/2 -translate-y-1/2';
}

function CameraGlyph({ className }: { className: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z"
      />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  );
}

/**
 * Trì hoãn tải bundle tìm theo ảnh đến khi người dùng bấm máy ảnh —
 * giữ nút hiện trong lúc tải để không bị "bấm không ra gì".
 */
export default function LazyDesktopImageSearchPopover({
  triggerButtonClassName = DEFAULT_TRIGGER,
  triggerIconClassName = DEFAULT_ICON,
  wrapperClassName,
  panelZClass = 'z-[5000]',
  triggerPosition = 'overlay-right',
}: Props) {
  const [opened, setOpened] = useState(false);
  const [Comp, setComp] = useState<ComponentType<PopoverProps> | null>(null);
  const wrapClass = triggerWrapClass({ wrapperClassName, triggerPosition });

  useEffect(() => {
    const w = typeof window !== 'undefined' ? window : null;
    if (!w) return;
    const ric = w.requestIdleCallback?.bind(w);
    let idleId: ReturnType<typeof requestIdleCallback> | undefined;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    const warm = () => {
      void import('@/components/DesktopImageSearchPopover').then((m) => {
        setComp(() => m.default);
      });
    };
    if (ric) idleId = ric(warm, { timeout: 4500 });
    else timeoutId = setTimeout(warm, 2800);
    return () => {
      if (idleId != null && w.cancelIdleCallback) w.cancelIdleCallback(idleId);
      if (timeoutId != null) clearTimeout(timeoutId);
    };
  }, []);

  const openNow = () => {
    setOpened(true);
    if (Comp) return;
    void import('@/components/DesktopImageSearchPopover').then((m) => {
      setComp(() => m.default);
    });
  };

  if (opened && Comp) {
    return (
      <Comp
        triggerButtonClassName={triggerButtonClassName}
        triggerIconClassName={triggerIconClassName}
        wrapperClassName={wrapperClassName}
        panelZClass={panelZClass}
        triggerPosition={triggerPosition}
        initialOpen
      />
    );
  }

  return (
    <div className={wrapClass}>
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          openNow();
        }}
        className={triggerButtonClassName}
        aria-label="Tìm kiếm bằng ảnh"
        aria-expanded={false}
        aria-haspopup="dialog"
        title="Tìm theo ảnh"
      >
        <CameraGlyph className={triggerIconClassName} />
      </button>
    </div>
  );
}
