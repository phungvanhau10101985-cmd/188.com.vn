import Link from "next/link";
import Image from "next/image";
import { notFound } from "next/navigation";

import {
  getSeoClusterDetail,
  getSeoClusterProducts,
  type SeoClusterProductCard,
  type SeoClusterListingFilters,
} from "@/lib/seo-cluster";
import { formatPrice } from "@/lib/utils";
import { productPathSlugFromApi } from "@/lib/product-path-slug";
import SeoClusterFiltersClient from "./SeoClusterFiltersClient";

const PAGE_SIZE = 48;

type Props = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

function spGet(sp: Record<string, string | string[] | undefined>, key: string): string | undefined {
  const v = sp[key];
  return Array.isArray(v) ? v[0] : v;
}

function parseClusterFilters(sp: Record<string, string | string[] | undefined>): {
  page: number;
  filters: SeoClusterListingFilters;
} {
  const page = Math.max(1, parseInt(String(spGet(sp, "page") ?? "1"), 10) || 1);
  const minRaw = spGet(sp, "min_price");
  const maxRaw = spGet(sp, "max_price");
  const minNum = minRaw != null && minRaw.trim() !== "" ? parseFloat(minRaw) : NaN;
  const maxNum = maxRaw != null && maxRaw.trim() !== "" ? parseFloat(maxRaw) : NaN;
  const filters: SeoClusterListingFilters = {};
  if (!Number.isNaN(minNum) && minNum >= 0) filters.minPrice = minNum;
  if (!Number.isNaN(maxNum) && maxNum >= 0) filters.maxPrice = maxNum;
  const size = spGet(sp, "size")?.trim();
  if (size) filters.size = size;
  const color = spGet(sp, "color")?.trim();
  if (color) filters.color = color;
  const styleTag = spGet(sp, "style_tag")?.trim();
  if (styleTag) filters.styleTag = styleTag;
  const sort = spGet(sp, "sort")?.trim();
  if (sort) filters.sort = sort;
  return { page, filters };
}

function serializeSearchParams(sp: Record<string, string | string[] | undefined>): string {
  const p = new URLSearchParams();
  for (const [key, val] of Object.entries(sp)) {
    if (val === undefined) continue;
    if (Array.isArray(val)) {
      for (const v of val) if (v !== undefined) p.append(key, v);
    } else {
      p.set(key, val);
    }
  }
  return p.toString();
}

function hasClusterFilters(filters: SeoClusterListingFilters): boolean {
  return Boolean(
    filters.minPrice != null ||
      filters.maxPrice != null ||
      filters.size ||
      filters.color ||
      filters.styleTag ||
      filters.sort
  );
}

export default async function SeoClusterLandingPage({ params, searchParams }: Props) {
  const { slug } = await params;
  const resolvedSearchParams = await searchParams;
  const cluster = await getSeoClusterDetail(slug);
  if (!cluster) {
    notFound();
  }

  const { page, filters } = parseClusterFilters(resolvedSearchParams);
  const listingQueryString = serializeSearchParams(resolvedSearchParams);
  const hasFilters = hasClusterFilters(filters);
  const skip = (page - 1) * PAGE_SIZE;

  // Trang 1 dùng products_sample đã có trong detail (đỡ 1 round-trip).
  // Trang 2+ gọi /products?skip=&limit=.
  const paged = page === 1 && !hasFilters && cluster.products_sample.length >= PAGE_SIZE
    ? null
    : await getSeoClusterProducts(slug, { skip, limit: PAGE_SIZE, filters });
  const products: SeoClusterProductCard[] = page === 1 && !hasFilters
    ? cluster.products_sample
    : paged?.products ?? [];
  const total = page === 1 && !hasFilters ? cluster.product_count : paged?.total ?? cluster.product_count;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const queryWithPage = (nextPage: number) => {
    const p = new URLSearchParams(listingQueryString);
    if (nextPage <= 1) p.delete("page");
    else p.set("page", String(nextPage));
    const q = p.toString();
    return q ? `/c/${cluster.slug}?${q}` : `/c/${cluster.slug}`;
  };

  return (
    <main className="max-w-7xl mx-auto px-4 py-6">
      <nav className="text-xs text-gray-500 mb-3" aria-label="Breadcrumb">
        <Link href="/" className="hover:underline">Trang chủ</Link>
        <span className="mx-1">/</span>
        <span className="text-gray-700">{cluster.name}</span>
      </nav>

      <header className="mb-5">
        <h1 className="text-2xl font-bold text-gray-900">{cluster.name}</h1>
        <p className="mt-1 text-sm text-gray-600">
          Tổng {total.toLocaleString("vi-VN")} sản phẩm — landing SEO của 188.COM.VN.
        </p>
      </header>

      <div className="sticky top-0 z-40 mb-5 border-b border-gray-200 bg-gray-50/95 px-2 py-1.5 shadow-sm backdrop-blur sm:px-3 md:top-[var(--listing-chrome-height)]">
        <SeoClusterFiltersClient slug={cluster.slug} />
      </div>

      {products.length === 0 ? (
        <div className="rounded border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          Chưa có sản phẩm nào trong cụm này. Sau khi import lại Excel sản phẩm với cat3 phù hợp, dữ liệu sẽ
          xuất hiện ở đây.
        </div>
      ) : (
        <section
          className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3"
          aria-label="Danh sách sản phẩm"
        >
          {products.map((p) => (
            <ClusterProductCard key={p.id} product={p} />
          ))}
        </section>
      )}

      {totalPages > 1 ? (
        <nav className="mt-6 flex flex-wrap items-center gap-2 text-sm" aria-label="Phân trang">
          {Array.from({ length: totalPages }).map((_, i) => {
            const n = i + 1;
            if (n === page) {
              return (
                <span
                  key={n}
                  aria-current="page"
                  className="rounded bg-orange-600 px-3 py-1 font-semibold text-white"
                >
                  {n}
                </span>
              );
            }
            return (
              <Link
                key={n}
                href={queryWithPage(n)}
                className="rounded border border-gray-300 bg-white px-3 py-1 text-gray-700 hover:bg-gray-50"
              >
                {n}
              </Link>
            );
          })}
        </nav>
      ) : null}

      {cluster.notes ? (
        <section className="mt-8 rounded border border-gray-200 bg-gray-50 p-4 text-sm text-gray-700">
          {cluster.notes}
        </section>
      ) : null}
    </main>
  );
}

function ClusterProductCard({ product }: { product: SeoClusterProductCard }) {
  const seg = productPathSlugFromApi(product.slug, product.product_id) || product.product_id;
  const href = `/products/${seg}`;
  const img = product.main_image || product.images?.[0] || "/images/og-default.jpg";
  return (
    <Link
      href={href}
      className="group block overflow-hidden rounded-lg border border-gray-200 bg-white transition-all hover:border-orange-200 hover:shadow"
    >
      <div className="relative aspect-square bg-gray-50">
        <Image
          src={img}
          alt={product.name}
          fill
          sizes="(max-width: 640px) 50vw, (max-width: 1024px) 25vw, 16vw"
          className="object-cover"
          unoptimized
        />
      </div>
      <div className="p-2">
        <div className="line-clamp-2 text-xs text-gray-800 group-hover:text-orange-600 sm:text-sm">
          {product.name}
        </div>
        <div className="mt-1 text-sm font-semibold text-orange-600">{formatPrice(product.price)}</div>
        {product.shop_name ? (
          <div className="mt-0.5 truncate text-[11px] text-gray-500">{product.shop_name}</div>
        ) : null}
      </div>
    </Link>
  );
}
