'use client';

import { useId } from 'react';
import { useRouter } from 'next/navigation';
import { storePendingImageAndNavigate } from '@/lib/nanoai-pending-image';

type MobileImageSearchButtonProps = {
  className?: string;
  iconClassName?: string;
};

/** Bấm là mở chọn ảnh ngay — dùng trên header mobile và trang /tim-kiem. */
export default function MobileImageSearchButton({
  className,
  iconClassName = 'block size-[18px] shrink-0 pointer-events-none',
}: MobileImageSearchButtonProps) {
  const inputId = useId();
  const router = useRouter();

  const onImagePick = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = '';
    if (!f) return;
    try {
      await storePendingImageAndNavigate(f, router);
    } catch {
      router.push('/tim-theo-anh');
    }
  };

  return (
    <>
      <input
        id={inputId}
        type="file"
        accept="image/jpeg,image/png,image/webp,image/gif"
        className="sr-only"
        tabIndex={-1}
        onChange={onImagePick}
      />
      <label
        htmlFor={inputId}
        className={className}
        aria-label="Tìm bằng ảnh"
        title="Tìm theo ảnh (NanoAI)"
      >
        <svg
          className={iconClassName}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          preserveAspectRatio="xMidYMid meet"
          aria-hidden
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z"
          />
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M15 13a3 3 0 11-6 0 3 3 0 016 0z"
          />
        </svg>
      </label>
    </>
  );
}
