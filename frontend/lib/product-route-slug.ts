/**
 * Chuẩn hoá segment slug từ URL /products/[slug] (Next decode, %2F, slug kho có /).
 */
export function normalizeProductRouteSlug(raw: string): string {
  let s = (raw || '').trim();
  if (!s) return '';
  for (let i = 0; i < 4; i++) {
    if (!/%[0-9A-Fa-f]{2}/.test(s)) break;
    try {
      const d = decodeURIComponent(s);
      if (d === s) break;
      s = d;
    } catch {
      break;
    }
  }
  return s.replace(/%2F/gi, '/').trim();
}
