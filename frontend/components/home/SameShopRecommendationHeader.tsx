'use client';

import Link from 'next/link';
import AgeGenderRecommendationHelpButton from '@/components/AgeGenderRecommendationHelpButton';
import type { SameAgeGenderCohortMode } from '@/types/api';

type SameShopRecommendationHeaderProps = {
  cohortMode: SameAgeGenderCohortMode | null;
  cohortLoading: boolean;
  isAuthenticated: boolean;
  hasCohortProducts: boolean;
  hint: React.ReactNode;
};

export default function SameShopRecommendationHeader({
  cohortMode,
  cohortLoading,
  isAuthenticated,
  hasCohortProducts,
  hint,
}: SameShopRecommendationHeaderProps) {
  const showHelp = !cohortLoading && cohortMode != null;
  const showEditProfile =
    !cohortLoading &&
    isAuthenticated &&
    hasCohortProducts &&
    cohortMode !== 'profile_incomplete' &&
    cohortMode !== 'requires_login';
  const showActions = showHelp || showEditProfile;

  return (
    <div className="mb-1 space-y-1.5">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
        <h2 className="text-base font-bold text-gray-900 border-b-2 border-[#ea580c] pb-1 w-fit leading-snug">
          CÓ THỂ BẠN THÍCH
        </h2>

        {showActions ? (
          <div
            className="inline-flex max-w-full shrink-0 items-center gap-0.5 rounded-full border border-orange-100 bg-orange-50/90 px-1 py-0.5"
            role="group"
            aria-label="Cá nhân hóa theo hồ sơ"
          >
            {showEditProfile ? (
              <Link
                href="/account/profile"
                className="inline-flex min-h-[30px] items-center rounded-full px-2 text-xs font-semibold text-[#ea580c] hover:bg-orange-100 hover:text-[#c2410c] transition-colors whitespace-nowrap"
              >
                Sửa tuổi / giới tính
              </Link>
            ) : (
              <span className="inline-flex min-h-[30px] items-center px-2 text-[11px] font-medium text-orange-800/90 whitespace-nowrap">
                Cá nhân hóa
              </span>
            )}
            {showHelp ? (
              <>
                <span className="h-3.5 w-px shrink-0 bg-orange-200" aria-hidden />
                <AgeGenderRecommendationHelpButton className="mr-0.5" />
              </>
            ) : null}
          </div>
        ) : null}
      </div>

      {hint ? <div className="text-xs text-gray-600 leading-snug">{hint}</div> : null}
    </div>
  );
}
