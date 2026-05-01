import type { CategoryLevel1 } from '@/types/api';
import { generateSlug } from '@/lib/utils';

/**
 * Điều hướng tìm sản phẩm theo chữ — dùng chung header, nav sticky, mobile header, trang chi tiết SP.
 * - Khớp slug với tên/slug danh mục → mở /danh-muc/...
 * - Không khớp → /?q=... (HomePageClient: kho 0 trang 1 thì gọi NanoAI text-search)
 */
export function navigateProductTextSearch(
  router: { push: (href: string) => void },
  raw: string,
  categoryTree: CategoryLevel1[],
): void {
  const term = raw.trim();
  if (!term) {
    router.push('/');
    return;
  }
  const target = generateSlug(term);
  const tree = categoryTree || [];
  for (const c1 of tree) {
    const slug1 = generateSlug(c1.slug || c1.name);
    if (target === slug1) {
      router.push(`/danh-muc/${encodeURIComponent(slug1)}`);
      return;
    }
    for (const c2 of c1.children || []) {
      const slug2 = generateSlug(c2.slug || c2.name);
      if (target === slug2) {
        router.push(`/danh-muc/${encodeURIComponent(slug1)}/${encodeURIComponent(slug2)}`);
        return;
      }
      for (const c3 of c2.children || []) {
        const name3 =
          typeof c3 === 'object' && c3 !== null && 'name' in c3 ? (c3 as { name: string }).name : String(c3);
        const slug3 = generateSlug(
          typeof c3 === 'object' && c3 !== null && 'slug' in c3
            ? (c3 as { slug?: string }).slug ?? name3
            : name3,
        );
        if (target === slug3) {
          router.push(
            `/danh-muc/${encodeURIComponent(slug1)}/${encodeURIComponent(slug2)}/${encodeURIComponent(slug3)}`,
          );
          return;
        }
      }
    }
  }
  router.push(`/?q=${encodeURIComponent(term)}`);
}
