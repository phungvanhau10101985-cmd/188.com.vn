import type { Metadata } from 'next';
import KhoSalePageClient from './KhoSalePageClient';
import { getApiBaseUrl } from '@/lib/api-base';
import type { Product, ProductListResponse } from '@/types/api';

const PAGE_SIZE = 48;

export const metadata: Metadata = {
  title: 'Kho sale — Hàng thanh lý xả kho',
  description:
    'Sản phẩm Sale Sốc, hàng thanh lý kho còn size — giá ưu đãi, số lượng có hạn trên 188.COM.VN.',
  alternates: { canonical: '/kho-sale' },
  robots: { index: true, follow: true },
};

async function fetchKhoSalePage(skip: number, limit: number): Promise<ProductListResponse> {
  const base = getApiBaseUrl();
  const qs = new URLSearchParams({
    warehouse_clearance_only: 'true',
    is_active: 'true',
    include_warehouse_clearance: 'true',
    skip: String(skip),
    limit: String(limit),
    sort: 'newest',
  });
  const res = await fetch(`${base}/products/?${qs.toString()}`, {
    next: { revalidate: 120 },
  });
  if (!res.ok) {
    return { products: [], total: 0, page: 1, size: limit, total_pages: 0 };
  }
  return (await res.json()) as ProductListResponse;
}

type Props = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

function spGet(sp: Record<string, string | string[] | undefined>, key: string): string | undefined {
  const v = sp[key];
  return Array.isArray(v) ? v[0] : v;
}

export default async function KhoSalePage({ searchParams }: Props) {
  const sp = await searchParams;
  const page = Math.max(1, parseInt(spGet(sp, 'page') || '1', 10) || 1);
  const skip = (page - 1) * PAGE_SIZE;
  const data = await fetchKhoSalePage(skip, PAGE_SIZE);
  const products = (data.products ?? []) as Product[];
  const total = data.total ?? products.length;
  const totalPages =
    data.total_pages ?? (total > 0 ? Math.ceil(total / PAGE_SIZE) : page > 1 ? page : 1);

  return (
    <KhoSalePageClient
      initialProducts={products}
      initialTotal={total}
      initialPage={page}
      initialTotalPages={totalPages}
      pageSize={PAGE_SIZE}
      listingQueryString={new URLSearchParams(
        Object.entries(sp).flatMap(([k, v]) => {
          if (v === undefined) return [];
          if (Array.isArray(v)) return v.map((x) => [k, x] as [string, string]);
          return [[k, v] as [string, string]];
        }),
      ).toString()}
    />
  );
}
