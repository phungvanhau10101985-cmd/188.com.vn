'use client';

import { useDepositPercent } from '@/lib/use-deposit-percent';

/** «X% giá trị hàng» — X lấy từ cài đặt mức cọc trên quản trị. */
export default function DepositPercentInline() {
  const percent = useDepositPercent();
  return <strong className="text-zinc-800">{percent}% giá trị hàng</strong>;
}
