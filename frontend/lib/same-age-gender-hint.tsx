import Link from 'next/link';
import type { ReactNode } from 'react';
import type { SameAgeGenderCohortMode } from '@/types/api';
import { trackEvent } from '@/lib/analytics';

function trackLoginCtaClick(cohortMode: SameAgeGenderCohortMode) {
  trackEvent('recommendation_login_cta_click', { cohort_mode: cohortMode });
}

/** CTA rõ ràng hơn link chữ đơn thuần — nút cam nổi bật, có giá trị cụ thể. */
function LoginCtaButton({
  href,
  label,
  cohortMode,
}: {
  href: string;
  label: string;
  cohortMode: SameAgeGenderCohortMode;
}) {
  return (
    <Link
      href={href}
      onClick={() => trackLoginCtaClick(cohortMode)}
      className="inline-flex shrink-0 items-center rounded-full bg-[#ea580c] px-2.5 py-1 text-[11px] font-semibold text-white whitespace-nowrap transition-colors hover:bg-[#c2410c]"
    >
      {label}
    </Link>
  );
}

export function sameAgeGenderCompactHint(
  mode: SameAgeGenderCohortMode | null,
  loading: boolean,
  isAuthenticated: boolean = true
): ReactNode {
  if (loading || mode == null) return null;
  switch (mode) {
    case 'requires_login':
      return (
        <div className="flex flex-wrap items-center gap-1.5">
          <span>Điền hồ sơ để nhận ưu đãi sinh nhật & sản phẩm có thể bạn thích.</span>
          <LoginCtaButton href="/auth/login" label="Đăng nhập nhận ưu đãi" cohortMode={mode} />
        </div>
      );
    case 'profile_incomplete':
      return (
        <>
          <Link href="/account/profile" className="font-semibold text-[#ea580c] hover:underline">
            Cập nhật ngày sinh & giới tính
          </Link>{' '}
          để nhận ưu đãi sinh nhật & sản phẩm hợp tuổi, hợp gu.
        </>
      );
    case 'popular_fallback':
      // Khách chưa đăng nhập nhưng đã có sản phẩm hiển thị (fallback phổ biến) — gợi ý nhẹ,
      // không chặn hiển thị SP (khác `requires_login`/`profile_incomplete` vốn thường đi kèm
      // lưới trống).
      if (isAuthenticated) return null;
      return (
        <div className="flex flex-wrap items-center gap-1.5">
          <span>Sản phẩm nổi bật hôm nay — đăng nhập để cá nhân hoá theo gu của bạn.</span>
          <LoginCtaButton href="/auth/login" label="Đăng nhập nhận ưu đãi" cohortMode={mode} />
        </div>
      );
    default:
      return null;
  }
}
