/**
 * Chuỗi dùng trong URL /danh-muc/... khi API không gửi slug (fallback tên có dấu).
 * Gần với slug tiếng Việt phía backend — tránh href kiểu encodeURIComponent("Giày dép Nam").
 */
export function categorySegmentForUrl(nameOrSlug: string | undefined | null): string {
  const s = (nameOrSlug || '').trim();
  if (!s) return '';
  const compact = s.replace(/\s+/g, '');
  if (/^[a-z0-9-]+$/i.test(compact) && !/\s/.test(s)) {
    return s.toLowerCase();
  }
  return s
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/đ/gi, 'd')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}
