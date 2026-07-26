import Link from 'next/link';
import type { ReactNode } from 'react';
import type { SameAgeGenderCohortMode } from '@/types/api';

export function sameAgeGenderCompactHint(
  mode: SameAgeGenderCohortMode | null,
  loading: boolean
): ReactNode {
  if (loading || mode == null) return null;
  switch (mode) {
    case 'requires_login':
      return (
        <>
          <Link href="/auth/login" className="font-semibold text-[#ea580c] hover:underline">
            Đăng nhập
          </Link>{' '}
          và điền hồ sơ để nhận ưu đãi sinh nhật & sản phẩm có thể bạn thích.
        </>
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
    default:
      return null;
  }
}
