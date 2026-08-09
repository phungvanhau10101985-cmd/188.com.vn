/**
 * SEO helpers cho trang Ladipage public (`/lp/<slug>`).
 */
import type { LadipageSection } from '@/lib/admin-api';
import type { FaqItem, HeroSectionData, MaterialSectionData } from '@/components/ladipage/types';

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || process.env.NEXT_PUBLIC_DOMAIN || 'https://188.com.vn';

export function absoluteLadipageImage(img?: string | null): string {
  if (!img) return '';
  if (img.startsWith('http')) return img;
  if (img.startsWith('//')) return 'https:' + img;
  if (img.startsWith('/')) return SITE_URL + img;
  return SITE_URL + '/' + img;
}

/** Ảnh OG fallback: hero → material section. */
export function heroImageFromSections(sections: LadipageSection[]): string {
  const hero = sections.find((s) => s.section_type === 'hero');
  const heroData = hero?.data as HeroSectionData | undefined;
  if (heroData?.image_url) return absoluteLadipageImage(heroData.image_url);

  const material = sections.find((s) => s.section_type === 'material');
  const materialData = material?.data as MaterialSectionData | undefined;
  if (materialData?.image_url) return absoluteLadipageImage(materialData.image_url);

  return '';
}

export function faqItemsFromSections(sections: LadipageSection[]): FaqItem[] {
  const faq = sections.find((s) => s.section_type === 'faq');
  const items = (faq?.data as { items?: FaqItem[] } | undefined)?.items;
  if (!Array.isArray(items)) return [];
  return items.filter((item) => item.q?.trim() && item.a?.trim());
}

export function buildFaqPageJsonLd(items: FaqItem[], pageUrl: string): object | null {
  const valid = items.filter((item) => item.q?.trim() && item.a?.trim());
  if (valid.length === 0) return null;
  const url = pageUrl.startsWith('http') ? pageUrl : `${SITE_URL}${pageUrl}`;
  return {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    url,
    mainEntity: valid.map((item) => ({
      '@type': 'Question',
      name: item.q.trim(),
      acceptedAnswer: {
        '@type': 'Answer',
        text: item.a.trim(),
      },
    })),
  };
}

/** BreadcrumbList: Trang chủ → bộ sưu tập ladipage. */
export function buildLadipageBreadcrumbJsonLd(pageTitle: string, pageUrl: string): object {
  const url = pageUrl.startsWith('http') ? pageUrl : `${SITE_URL}${pageUrl}`;
  const name = pageTitle.trim() || 'Bộ sưu tập';
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: [
      { '@type': 'ListItem', position: 1, name: 'Trang chủ', item: SITE_URL },
      { '@type': 'ListItem', position: 2, name, item: url },
    ],
  };
}
