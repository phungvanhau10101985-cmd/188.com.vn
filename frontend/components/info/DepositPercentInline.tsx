'use client';

import { formatDepositMinVnd, partialPercentForLines } from '@/lib/order-deposit';
import { useDepositPolicy } from '@/lib/use-deposit-percent';

/** Mốc «đơn từ X» đang lưu ở quản trị. */
export function DepositHighOrderInline() {
  const { highOrderAmount } = useDepositPolicy();
  return <strong className="text-zinc-800">{formatDepositMinVnd(highOrderAmount)}</strong>;
}

/** % thực tế của đơn từ mốc đó: không thấp hơn 30%, và không thấp hơn % cọc trước. */
export function DepositHighOrderPercentInline() {
  const { percent } = useDepositPolicy();
  return <strong className="text-zinc-800">{partialPercentForLines(percent, true)}%</strong>;
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
