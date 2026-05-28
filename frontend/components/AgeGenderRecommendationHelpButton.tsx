'use client';

import Link from 'next/link';
import {
  AGE_GENDER_RECOMMENDATION_INFO_PATH,
  AGE_GENDER_RECOMMENDATION_TOOLTIP,
} from '@/lib/age-gender-recommendation-info';

export default function AgeGenderRecommendationHelpButton({ className = '' }: { className?: string }) {
  return (
    <span className={`group relative inline-flex ${className}`}>
      <Link
        href={AGE_GENDER_RECOMMENDATION_INFO_PATH}
        className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold leading-none text-gray-500 hover:bg-orange-100/90 hover:text-[#ea580c] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#ea580c] focus-visible:ring-offset-1 transition-colors"
        aria-label="Tại sao cần cập nhật tuổi và giới tính?"
      >
        ?
      </Link>
      <span
        role="tooltip"
        className="pointer-events-none absolute left-0 top-[calc(100%+8px)] z-30 w-[min(17rem,calc(100vw-2rem))] rounded-xl border border-gray-200 bg-gray-900 px-3 py-2.5 text-[11px] leading-relaxed text-white opacity-0 shadow-xl transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100 max-sm:hidden"
      >
        {AGE_GENDER_RECOMMENDATION_TOOLTIP}
        <span
          className="absolute -top-1 left-3 h-2 w-2 rotate-45 border-l border-t border-gray-200 bg-gray-900"
          aria-hidden
        />
      </span>
    </span>
  );
}
