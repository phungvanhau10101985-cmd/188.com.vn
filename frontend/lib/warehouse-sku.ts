/**

 * Mã kho từ cột H file EMS (MA_SP) — chỉ phần trước dấu «-» đầu tiên.

 * Vd. L3712/M/1-ĐEN-*https://... → L3712/M/1

 */

export function looksLikeRecipientNotSku(raw: string): boolean {

  const t = raw.trim();

  if (!t) return false;

  if (/[—]/.test(t) || / · /.test(t)) return true;

  if (/đường|phường|quận|huyện|thành phố|tỉnh|ngõ|thôn|xã /i.test(t)) return true;

  if (t.length > 48 && !t.includes('/')) return true;

  return false;

}



export function normalizeWarehouseSkuFromEmsLabel(raw: string): string {

  const t = raw.trim();

  if (!t || looksLikeRecipientNotSku(t)) return '';

  const dash = t.search(/[-–—]/);

  const head = (dash >= 0 ? t.slice(0, dash) : t).trim();

  if (!head || looksLikeRecipientNotSku(head)) return '';

  return head;

}

