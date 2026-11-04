export type ZaloOpenMode = 'personal' | 'oa';

const ZALO_OPEN_RE = /(?:^|\n)zalo_open:(personal|oa)\b\n?/;

/** Chế độ đã lưu trong gợi ý admin. Không có dòng thì null — backend coi số hợp lệ là cá nhân. */
export function readZaloOpenMode(hint: string | null | undefined): ZaloOpenMode | null {
  const match = ZALO_OPEN_RE.exec(hint || '');
  return match ? (match[1] as ZaloOpenMode) : null;
}

export function stripZaloOpenMode(hint: string | null | undefined): string {
  return (hint || '').replace(ZALO_OPEN_RE, '').trim();
}

export function withZaloOpenMode(hint: string | null | undefined, mode: ZaloOpenMode): string {
  const clean = stripZaloOpenMode(hint);
  return clean ? `zalo_open:${mode}\n${clean}` : `zalo_open:${mode}`;
}

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
