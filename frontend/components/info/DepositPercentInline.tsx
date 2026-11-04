'use client';

import { formatDepositMinVnd } from '@/lib/order-deposit';
import { useDepositPolicy } from '@/lib/use-deposit-percent';

/** Mốc «đơn từ X» đang lưu ở quản trị. */
export function DepositHighOrderInline() {
  const { highOrderAmount } = useDepositPolicy();
  return <strong className="text-zinc-800">{formatDepositMinVnd(highOrderAmount)}</strong>;
}

/** % cọc của đơn từ mốc giá trị hàng. */
export function DepositHighOrderPercentInline() {
  const { highOrderPercent } = useDepositPolicy();
  return <strong className="text-zinc-800">{highOrderPercent}%</strong>;
}

/** «X% giá trị hàng, tối thiểu …» — lấy từ cài đặt mức cọc trên quản trị. */
export default function DepositPercentInline() {
  const { percent, minAmount } = useDepositPolicy();
  return (
    <strong className="text-zinc-800">
      {percent}% giá trị hàng, tối thiểu {formatDepositMinVnd(minAmount)}
    </strong>
  );
}
