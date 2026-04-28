'use client';

import type { NanoaiSearchProduct } from '@/types/api';
import { truncateText } from '@/lib/utils';

/** Hiển thị giá VND theo thói quen VN: nhóm nghìn + hậu tố đ (không dùng ký hiệu ₫ của Intl). */
function formatVndDong(amount: number): string {
  const n = Math.round(Number(amount));
  if (!Number.isFinite(n)) return '';
  return `${new Intl.NumberFormat('vi-VN').format(n)} đ`;
}

/** Bóc số từ price_hint (số thuần, có dấu . nghìn, hoặc đuôi VND). */
function parsePriceHintNumber(raw: string): number | null {
  const t = raw.trim().replace(/\s/g, ' ');
  if (!t) return null;
  const noVnd = t.replace(/\s*vnd\s*$/i, '').trim();
  if (/^\d+$/.test(noVnd)) {
    const v = Number(noVnd);
    return Number.isFinite(v) ? v : null;
  }
  // 1.280.000 hoặc 1,280,000 (phân tách nghìn)
  if (/^\d{1,3}([.,]\d{3})+([.,]\d+)?$/.test(noVnd)) {
    const normalized = noVnd.includes('.') && noVnd.includes(',')
      ? noVnd.replace(/\./g, '').replace(',', '.')
      : noVnd.replace(/[.,]/g, '');
    const v = Number(normalized);
    return Number.isFinite(v) ? v : null;
  }
  const loose = noVnd.replace(/[^\d]/g, '');
  if (loose.length >= 1 && /^\d+$/.test(loose)) {
    const v = Number(loose);
    return Number.isFinite(v) ? v : null;
  }
  return null;
}

function resolvePriceLine(item: NanoaiSearchProduct): string | null {
  const hint = item.price_hint?.trim();
  if (hint) {
    const n = parsePriceHintNumber(hint);
    if (n != null) return formatVndDong(n);
    return hint;
  }
  if (item.price != null && item.price !== undefined && !Number.isNaN(Number(item.price))) {
    return formatVndDong(Number(item.price));
  }
  return null;
}

/** Lấy mảng URL ảnh màu: color_image_urls + img trong color_variants + camelCase. */
function extractColorImageUrls(item: NanoaiSearchProduct): string[] {
  const a = Array.isArray(item.color_image_urls) ? item.color_image_urls : [];
  const fromVariants: string[] = [];
  const vv = item.color_variants ?? item.colorVariants;
  if (Array.isArray(vv)) {
    for (const v of vv) {
      const u = typeof v?.img === 'string' ? v.img.trim() : '';
      if (u) fromVariants.push(u);
    }
  }
  const b = Array.isArray(item.colorImageUrls) ? item.colorImageUrls : [];
  const raw = [...a, ...fromVariants, ...b];
  return raw.filter((u): u is string => typeof u === 'string' && u.trim().length > 0);
}

const cardClass =
  'product-card group bg-white rounded-xl border border-gray-100 shadow-sm hover:shadow-lg hover:border-orange-200 overflow-hidden transition-all block';

interface NanoaiSimilarProductCardProps {
  item: NanoaiSearchProduct;
}

/** Thẻ cùng phong cách SimpleProductCard, dùng cho kết quả NanoAI (có/không giá). */
export default function NanoaiSimilarProductCard({ item }: NanoaiSimilarProductCardProps) {
  const name = item.name || 'Sản phẩm';
  const img = item.image_url || '';
  const priceLine = resolvePriceLine(item);
  const colorUrlsRaw = extractColorImageUrls(item);
  const seenUrl = new Set<string>();
  const colorUrls = colorUrlsRaw.filter((u) => {
    const k = u.trim();
    if (seenUrl.has(k)) return false;
    seenUrl.add(k);
    return true;
  });
  /** Luôn hiển thị ảnh màu kể cả trùng URL/path với ảnh đại diện (chỉ dedupe trùng tuyệt đối trong danh sách). */
  const colorThumbUrls = colorUrls;
  const MAX_COLOR_THUMBS = 3;

  const colorThumbs = (justify: 'start' | 'end') =>
    colorThumbUrls.length > 0 ? (
      <div
        className={`flex flex-nowrap gap-0.5 items-center shrink-0 ${justify === 'end' ? 'justify-end' : 'justify-start'}`}
        role="list"
        aria-label="Ảnh màu sản phẩm"
      >
        {colorThumbUrls.slice(0, MAX_COLOR_THUMBS).map((url, i) => (
          <div
            role="listitem"
            key={`${url}-${i}`}
            className="h-7 w-7 sm:h-8 sm:w-8 shrink-0 overflow-hidden rounded-md border border-gray-200 bg-gray-50 ring-1 ring-black/5"
          >
            <img
              src={url}
              alt=""
              width={32}
              height={32}
              className="h-full w-full object-cover"
              loading="lazy"
              decoding="async"
            />
          </div>
        ))}
      </div>
    ) : null;

  const inner = (
    <>
      <div className="relative aspect-square bg-gray-50 overflow-hidden rounded-t-xl">
        {img ? (
          <img
            src={img}
            alt={name}
            className="absolute inset-0 h-full w-full object-cover group-hover:scale-105 transition-transform duration-300"
            loading="lazy"
            decoding="async"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-gray-200 text-gray-400 text-xs">
            Không có ảnh
          </div>
        )}
      </div>
      <div className="p-2">
        <h3 className="font-medium text-gray-900 text-xs mb-1 line-clamp-2 leading-tight group-hover:text-orange-600 transition-colors min-h-[2rem]">
          {truncateText(name, 45)}
        </h3>
        {/* Mobile: 3 ảnh một hàng, SKU + giá một hàng */}
        <div className="sm:hidden space-y-1">
          {colorThumbs('start')}
          <div className="flex flex-row flex-wrap items-baseline gap-x-2 gap-y-0 min-w-0">
            {item.sku ? (
              <span className="text-[10px] text-gray-500 truncate min-w-0">SKU: {item.sku}</span>
            ) : null}
            {priceLine ? (
              <span className="text-xs font-semibold text-gray-900 leading-tight whitespace-nowrap">{priceLine}</span>
            ) : null}
          </div>
        </div>
        {/* sm+: SKU/giá cột trái, ảnh phụ bên phải */}
        <div className="hidden sm:flex mb-0.5 gap-1.5 items-start justify-between">
          <div className="min-w-0 flex-1 space-y-0.5 pr-0.5">
            {item.sku ? (
              <p className="text-[10px] text-gray-500">SKU: {item.sku}</p>
            ) : null}
            {priceLine ? (
              <p className="text-xs font-semibold text-gray-900 leading-tight">{priceLine}</p>
            ) : null}
          </div>
          {colorThumbs('end')}
        </div>
      </div>
    </>
  );

  const hrefRaw = (item.product_url || '').trim();
  if (!hrefRaw) {
    return (
      <div className="product-card group bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden opacity-95">
        {inner}
      </div>
    );
  }

  return (
    <a href={hrefRaw} className={cardClass}>
      {inner}
    </a>
  );
}
