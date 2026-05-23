type PushToast = (toast: {
  title: string;
  description?: string;
  action?: { label: string; href: string };
  variant: 'success' | 'error' | 'info';
  durationMs?: number;
}) => void;

export function pushOrderReceivedConfirmedToast(pushToast: PushToast, orderId: number) {
  pushToast({
    title: 'Đã xác nhận nhận hàng',
    description:
      'Cảm ơn bạn! Nếu hài lòng, rất mong bạn đánh giá đơn hàng — ý kiến của bạn giúp 188.com.vn cải thiện sản phẩm và dịch vụ.',
    action: { label: 'Đánh giá ngay', href: `/account/orders/${orderId}/review` },
    variant: 'success',
    durationMs: 6500,
  });
}
