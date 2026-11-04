/** Số hoặc link zalo.me → https://zalo.me/… Khớp backend `normalize_zalo_personal_url`. */
export function normalizeZaloPersonalUrl(raw: string): string | null {
  const text = (raw || '').trim();
  if (!text || /[<>"']/.test(text)) return null;
  const fromLink = text.match(/(?:https?:\/\/)?(?:www\.)?zalo\.me\/([0-9]{9,20})\/?/i);
  let digits = '';
  if (fromLink) {
    digits = fromLink[1];
  } else {
    let compact = text.replace(/[\s.\-()]/g, '');
    if (compact.startsWith('+')) compact = compact.slice(1);
    if (!/^\d+$/.test(compact)) return null;
    digits = compact;
  }
  if (digits.startsWith('84') && (digits.length === 11 || digits.length === 12)) {
    digits = `0${digits.slice(2)}`;
  }
  if (!/^\d+$/.test(digits) || digits.length < 9 || digits.length > 20) return null;
  if (digits.length <= 11 && !digits.startsWith('0')) {
    digits = `0${digits}`;
    if (digits.length > 11) return null;
  }
  return `https://zalo.me/${digits}`;
}
