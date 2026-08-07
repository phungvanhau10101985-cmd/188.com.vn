import type { Metadata } from 'next';
import { notFound, redirect } from 'next/navigation';
import {
  getPublicLadipage,
  getProductByIdForSeo,
  getProductsByIdsForSeo,
} from '@/lib/ladipage-public';
import { productPathSlugFromApi } from '@/lib/product-path-slug';
import {
  absoluteLadipageImage,
  buildFaqPageJsonLd,
  faqItemsFromSections,
  heroImageFromSections,
} from '@/lib/ladipage-seo';
import { buildProductListJsonLd, truncateDescriptionAtSentence } from '@/lib/product-seo';
import { serializeJsonLdForScript } from '@/lib/json-ld-script';
import PublicLadipageView from '@/components/ladipage/PublicLadipageView';
import LadipageLandingMarketingTracker from './LadipageLandingMarketingTracker';

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || process.env.NEXT_PUBLIC_DOMAIN || 'https://188.com.vn';

type Props = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

/** Giữ gclid / fbclid / ttclid / UTM khi redirect /lp → /products (attribution ads). */
function buildQuerySuffix(sp: Record<string, string | string[] | undefined>): string {
  const q = new URLSearchParams();
  for (const [key, raw] of Object.entries(sp || {})) {
    if (raw == null) continue;
    if (Array.isArray(raw)) {
      raw.forEach((v) => {
        if (v != null && String(v).trim()) q.append(key, String(v));
      });
    } else if (String(raw).trim()) {
      q.set(key, String(raw));
    }
  }
  const s = q.toString();
  return s ? `?${s}` : '';
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const lp = await getPublicLadipage(slug);
  if (!lp) return { title: 'Không tìm thấy trang', robots: { index: false, follow: true } };

  const canonical = `${SITE_URL}/lp/${lp.slug}`;
  const isSingleProduct = lp.resolved_product_ids.length === 1;
  const product = isSingleProduct ? await getProductByIdForSeo(lp.resolved_product_ids[0]) : null;

  const title = lp.meta_title || lp.title;
  const rawDescription =
    lp.meta_description ||
    (product ? product.description : undefined) ||
    `${lp.title}. Mua sắm tại 188.com.vn - Xem là thích click là mê.`;
  const description = truncateDescriptionAtSentence(rawDescription, 160);
  const image =
    (product ? absoluteLadipageImage(product.main_image) || absoluteLadipageImage(product.images?.[0]) : '') ||
    heroImageFromSections(lp.sections);

  return {
    title,
    description,
    alternates: { canonical: `/lp/${lp.slug}` },
    openGraph: {
      type: 'website',
      locale: 'vi_VN',
      url: canonical,
      siteName: '188.COM.VN',
      title,
      description: description.slice(0, 200).trim(),
      images: image ? [{ url: image, width: 1200, height: 630, alt: title }] : undefined,
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description: description.slice(0, 200).trim(),
      images: image ? [image] : undefined,
    },
    robots: {
      index: true,
      follow: true,
      googleBot: { index: true, follow: true, 'max-image-preview': 'large', 'max-snippet': -1 },
    },
    ...(product
      ? {
          other: {
            'product:price:amount': String(product.price),
            'product:price:currency': 'VND',
            'product:availability': (product.available ?? 0) > 0 ? 'in stock' : 'out of stock',
          },
        }
      : {}),
  };
}

function JsonLdScript({ data }: { data: object }) {
  return (
    <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: serializeJsonLdForScript(data) }} />
  );
}

export default async function LadipagePublicPage({ params, searchParams }: Props) {
  const { slug } = await params;
  const sp = await searchParams;
  const querySuffix = buildQuerySuffix(sp);
  const lp = await getPublicLadipage(slug);
  if (!lp) {
    notFound();
  }

  const pageUrl = `/lp/${lp.slug}`;
  const faqItems = faqItemsFromSections(lp.sections);
  const faqJsonLd = buildFaqPageJsonLd(faqItems, pageUrl);
  const isSingleProduct = lp.resolved_product_ids.length === 1;

  if (isSingleProduct) {
    const product = await getProductByIdForSeo(lp.resolved_product_ids[0]);
    if (product) {
      const seg = productPathSlugFromApi(product.slug, product.product_id);
      if (seg) {
        redirect(`/products/${encodeURIComponent(seg.replace(/\//g, '-'))}${querySuffix}`);
      }
    }
  }

  const listProducts = await getProductsByIdsForSeo(lp.resolved_product_ids);
  const listJsonLd =
    listProducts.length > 0
      ? buildProductListJsonLd({
          pageUrl,
          pageTitle: lp.meta_title || lp.title,
          pageDescription: lp.meta_description || undefined,
          products: listProducts,
        })
      : null;

  return (
    <main className="py-4">
      {listJsonLd ? <JsonLdScript data={listJsonLd} /> : null}
      {faqJsonLd ? <JsonLdScript data={faqJsonLd} /> : null}
      <LadipageLandingMarketingTracker products={listProducts} listName={lp.title} />
      <PublicLadipageView
        slug={lp.slug}
        title={lp.title}
        sections={lp.sections}
        resolvedProductIds={lp.resolved_product_ids}
        initialProducts={listProducts}
      />
    </main>
  );
}
