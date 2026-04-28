/**
 * Sau khi POST tạo đơn: đi thẳng trang đặt cọc nếu backend trả đơn chờ cọc.
 */
export function shouldRedirectToDepositAfterCreate(order: {
  requires_deposit?: boolean;
  status?: string;
}): boolean {
  return Boolean(order.requires_deposit) && String(order.status ?? '') === 'waiting_deposit';
}
