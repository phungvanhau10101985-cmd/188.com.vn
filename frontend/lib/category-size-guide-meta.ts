/** Slug danh mục cấp 1 (taxonomy DB) có trang `/info/chon-size/{cat1}`. */

export const SIZE_GUIDE_SLUG_TITLES: Record<string, string> = {
  'giay-dep-nam': 'Giày dép Nam',
  'giay-dep-nu': 'Giày dép Nữ',
  'thoi-trang-nam': 'Thời trang Nam',
  'thoi-trang-nu': 'Thời trang Nữ',
  'tui-xach-nam': 'Túi xách Nam',
  'tui-xach-nu': 'Túi xách Nữ',
  'phu-kien-nam': 'Phụ kiện Nam',
  'phu-kien-nu': 'Phụ kiện Nữ',
  'do-lot-nam': 'Đồ lót Nam',
  'do-lot-nu': 'Đồ lót Nữ',
  'trang-phuc-bau-hau-san': 'Trang phục bầu & hậu sản',
  'thoi-trang-tre-em': 'Thời trang trẻ em',
  'vali-tui-du-lich': 'Vali & túi du lịch',
  'dong-ho': 'Đồng hồ',
  'trang-suc-thoi-trang': 'Trang sức thời trang',
  'phu-kien-dien-thoai-cong-nghe': 'Phụ kiện điện thoại & công nghệ',
  'my-pham-lam-dep': 'Mỹ phẩm & làm đẹp',
  'do-gia-dung': 'Đồ gia dụng',
  'do-choi-me-be': 'Đồ chơi & mẹ bé',
  'thuc-pham-do-uong': 'Thực phẩm & đồ uống',
  'thuc-pham-chuc-nang': 'Thực phẩm chức năng',
  'van-phong-pham-sach': 'Văn phòng phẩm & sách',
  'the-thao-da-ngoai': 'Thể thao & dã ngoại',
  'phu-kien-xe-may-o-to': 'Phụ kiện xe máy & ô tô',
  'thu-cung': 'Thú cưng',
  'noi-that-trang-tri-nha': 'Nội thất & trang trí nhà',
  generic: 'Hướng dẫn chọn size (chung)',
};

export const ALL_SIZE_GUIDE_SLUGS = Object.keys(SIZE_GUIDE_SLUG_TITLES);

/**
 * Cặp slug `cat1/cat2` (khớp 2 segment đầu của Category.full_slug) có nội dung riêng.
 */
export const SIZE_GUIDE_CAT2_TITLES: Record<string, string> = {
  'thoi-trang-tre-em/giay-dep-tre-em': 'Giày dép trẻ em',
  'do-lot-nu/bra-ao-nguc-nu': 'Bra áo ngực Nữ',
  'giay-dep-nu/giay-cao-got-nu': 'Giày cao gót Nữ',
  'giay-dep-nu/giay-cuoi-du-tiec-nu': 'Giày cưới & dự tiệc Nữ',
};

export const ALL_CAT2_GUIDE_KEYS = Object.keys(SIZE_GUIDE_CAT2_TITLES);

/** Chuẩn hoá một segment slug từ API / URL. */
export function normalizeSizeGuideSegment(raw: string | null | undefined): string {
  return (raw ?? '').trim().toLowerCase();
}

/** Khoá nối hai segment (cat1/cat2). */
export function cat2GuidePathKey(cat1: string, cat2: string): string {
  const a = normalizeSizeGuideSegment(cat1);
  const b = normalizeSizeGuideSegment(cat2);
  if (!a || !b) return '';
  return `${a}/${b}`;
}

export function titleForSizeGuideSlug(slug: string): string {
  return SIZE_GUIDE_SLUG_TITLES[slug] ?? slug.replace(/-/g, ' ');
}

export function resolveSizeGuideSlug(raw: string | null | undefined): string {
  const s = normalizeSizeGuideSegment(raw);
  if (!s) return 'generic';
  if (SIZE_GUIDE_SLUG_TITLES[s]) return s;
  return 'generic';
}

/**
 * PDP / trang info: có override cat2 whitelist → [cat1, cat2]; không thì chỉ [cat1 resolved].
 */
export function resolveSizeGuideSegments(
  rawL1: string | null | undefined,
  rawL2: string | null | undefined,
): readonly [string] | readonly [string, string] {
  const l1n = normalizeSizeGuideSegment(rawL1);
  const l2n = normalizeSizeGuideSegment(rawL2);
  const key = cat2GuidePathKey(l1n, l2n);
  if (key && SIZE_GUIDE_CAT2_TITLES[key]) {
    return [l1n, l2n];
  }
  return [resolveSizeGuideSlug(l1n)] as const;
}

export function titleForSizeGuideSegments(segments: readonly string[]): string {
  if (segments.length === 2) {
    const k = `${segments[0]}/${segments[1]}`;
    return SIZE_GUIDE_CAT2_TITLES[k] ?? `${titleForSizeGuideSlug(segments[0])} — ${segments[1].replace(/-/g, ' ')}`;
  }
  return titleForSizeGuideSlug(segments[0] ?? '');
}

export function hrefChonSizeSegments(segments: readonly string[]): string {
  return `/info/chon-size/${segments.join('/')}`;
}

/** Tham số động cho `generateStaticParams` (Catch-all `slug: string[]`). */
export function allChonSizeStaticSlugParams(): { slug: string[] }[] {
  const cat1 = ALL_SIZE_GUIDE_SLUGS.map((s) => ({ slug: [s] }));
  const cat2 = ALL_CAT2_GUIDE_KEYS.map((k) => ({ slug: k.split('/') }));
  return [...cat1, ...cat2];
}

export function isValidChonSizeSlugParam(slug: string[] | undefined): boolean {
  if (!slug?.length) return false;
  if (slug.length === 1) return ALL_SIZE_GUIDE_SLUGS.includes(slug[0]);
  if (slug.length === 2) return ALL_CAT2_GUIDE_KEYS.includes(`${slug[0]}/${slug[1]}`);
  return false;
}
