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

/** Phân đoạn mã nguồn A/T (1688): A…/4 = ô ảnh màu; A…/45/4 = size 45 + ô ảnh 4. */
export type ListingSourceSkuSegments = {
  base: string;
  size?: string;
  colorImageIndex?: number;
  unit?: string;
};

const LISTING_BASE_RE = /^([AT]\d{6,})$/i;
const SIZE_LIKE_RE = /^(xxs|xs|s|m|l|xl|xxl|xxxl|2xl|3xl|4xl|5xl|\d{1,2}(?:\.\d)?|\d{2,3})$/i;

export function parseListingSourceSkuSegments(sku: string): ListingSourceSkuSegments | null {
  const raw = sku.trim();
  if (!raw.includes('/')) return null;
  const parts = raw.split('/').map((p) => p.trim()).filter(Boolean);
  if (parts.length < 2 || !LISTING_BASE_RE.test(parts[0])) return null;

  const base = parts[0];
  if (parts.length === 2) {
    const seg = parts[1];
    if (/^\d+$/.test(seg)) {
      return { base, colorImageIndex: parseInt(seg, 10) };
    }
    if (SIZE_LIKE_RE.test(seg)) {
      return { base, size: seg.toUpperCase() };
    }
    return { base };
  }

  if (parts.length === 3) {
    const mid = parts[1];
    const tail = parts[2];
    if (SIZE_LIKE_RE.test(mid) && mid.match(/^[a-z]+$/i)) {
      return { base, size: mid.toUpperCase(), unit: tail };
    }
    if (SIZE_LIKE_RE.test(mid) && /^\d+$/.test(tail)) {
      if (parseInt(tail, 10) === 1) {
        return { base, size: mid, unit: tail };
      }
      return { base, size: mid, colorImageIndex: parseInt(tail, 10) };
    }
  }

  return { base };
}

