/** Thay placeholder trong URL mẫu QR (SePay / tuỳ chỉnh). */
export function buildQrFromTemplate(
  template: string | null | undefined,
  params: {
    bank_acc: string;
    bank_id: string;
    amount: number | string;
    des: string;
  }
): string | null {
  const t = (template || '').trim();
  if (!t) return null;
  const des = encodeURIComponent(String(params.des));
  const bank_acc = encodeURIComponent(String(params.bank_acc).trim());
  const bank_id = encodeURIComponent(String(params.bank_id).trim());
  const amount = encodeURIComponent(String(params.amount));
  return t
    .replace(/\{bank_acc\}/gi, bank_acc)
    .replace(/\{bank_id\}/gi, bank_id)
    .replace(/\{amount\}/gi, amount)
    .replace(/\{des\}/gi, des);
}

export const DEFAULT_SEPAY_QR_TEMPLATE =
  'https://qr.sepay.vn/img?acc={bank_acc}&bank={bank_id}&amount={amount}&des={des}&template=compact';
