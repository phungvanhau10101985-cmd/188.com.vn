'use client';

import { formatDepositMinVnd } from '@/lib/order-deposit';
import { useDepositPolicy } from '@/lib/use-deposit-percent';

/** «X% giá trị hàng, tối thiểu …» — lấy từ cài đặt mức cọc trên quản trị. */
export default function DepositPercentInline() {
  const { percent, minAmount } = useDepositPolicy();
  return (
    <strong className="text-zinc-800">
      {percent}% giá trị hàng, tối thiểu {formatDepositMinVnd(minAmount)}
    </strong>
  );
}
