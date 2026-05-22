/**
 * Nội dung chuyển khoản đặt cọc — khớp backend `build_transfer_content_for_order`
 * (SEPAY_TRANSFER_PREFIX + order_code, mặc định `SEVQR DH090`).
 */
export function buildSepayTransferContent(orderCode: string | null | undefined): string {
  const code = (orderCode || '').trim();
  if (!code) return '';

  const transferPrefix = (process.env.NEXT_PUBLIC_SEPAY_TRANSFER_PREFIX || 'SEVQR').trim();
  const contentPrefix = (process.env.NEXT_PUBLIC_SEPAY_CONTENT_PREFIX || 'DH').trim();
  const label = transferPrefix || contentPrefix;

  return label ? `${label} ${code}`.trim() : code;
}
