'use client';

import LazyDesktopImageSearchPopover from '@/components/LazyDesktopImageSearchPopover';

type MobileImageSearchButtonProps = {
  className?: string;
  iconClassName?: string;
};

/** Cùng panel dán ảnh / dán link / chọn file như nút máy ảnh desktop. */
export default function MobileImageSearchButton({
  className,
  iconClassName = 'block size-6 shrink-0 pointer-events-none',
}: MobileImageSearchButtonProps) {
  return (
    <LazyDesktopImageSearchPopover
      triggerPosition="inline-end"
      wrapperClassName="relative inline-flex h-full shrink-0 items-stretch self-stretch"
      triggerButtonClassName={className}
      triggerIconClassName={iconClassName}
      panelZClass="z-[5000]"
    />
  );
}
