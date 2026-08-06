export type LadipageListKind = 'category' | 'product_single' | 'products_multi';

export const LADIPAGE_KIND_TABS: {
  slug: string;
  kind: LadipageListKind;
  label: string;
  description: string;
}[] = [
  {
    slug: '1-san-pham',
    kind: 'product_single',
    label: '1 sản phẩm',
    description: 'Landing trên PDP — tự sinh khi khách xem hoặc tạo thủ công.',
  },
  {
    slug: 'danh-muc',
    kind: 'category',
    label: 'Danh mục',
    description: 'Trang /lp/… theo danh mục cấp 3, lưới SP bán chạy.',
  },
  {
    slug: 'nhieu-san-pham',
    kind: 'products_multi',
    label: 'Nhiều sản phẩm',
    description: 'Landing chọn nhiều SP cụ thể (URL /lp/…).',
  },
];

export const DEFAULT_LADIPAGE_KIND_SLUG = '1-san-pham';

export const LADIPAGE_ADMIN_LIST_BASE = '/admin/ladipage/list';

export function ladipageListHref(kindSlug: string): string {
  return `${LADIPAGE_ADMIN_LIST_BASE}/${kindSlug}`;
}

export function ladipageKindFromSlug(slug: string): LadipageListKind | null {
  const row = LADIPAGE_KIND_TABS.find((t) => t.slug === slug);
  return row?.kind ?? null;
}

export function ladipageTabFromSlug(slug: string) {
  return LADIPAGE_KIND_TABS.find((t) => t.slug === slug) ?? null;
}
