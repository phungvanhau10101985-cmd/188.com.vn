/** Chuỗi link nguồn (link_default product_url) có vẻ là chi tiết 1688 offer — dùng gợi ý UX kiểm tra tồn nguồn. */
export function looksLike1688OfferUrl(url: string | null | undefined): boolean {
  const u = (url ?? '').trim();
  if (!u || !u.includes('1688.com')) return false;
  return /\/offer\/\d+|offerId=\d+/i.test(u) || detail1688HostMatches(u);
}

function detail1688HostMatches(full: string): boolean {
  try {
    const hostname = new URL(full).hostname.toLowerCase().replace(/^www\./, '');
    return hostname === 'detail.1688.com' || hostname === 'detail.m.1688.com' || hostname === 'm.1688.com';
  } catch {
    return false;
  }
}
