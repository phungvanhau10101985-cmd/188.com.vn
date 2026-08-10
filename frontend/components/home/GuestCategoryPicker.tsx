'use client';

import { useEffect, useState } from 'react';
import LoadingLink from '@/components/ui/LoadingLink';
import { apiClient } from '@/lib/api-client';
import { categoryTileHref, formatItemCount, tileTitle } from '@/components/category/CategoryCatalogMarquee';
import { setGuestCategoryInterest } from '@/lib/guest-category-interest';
import { trackEvent } from '@/lib/analytics';
import type { HeroCategoryTile } from '@/types/api';

const PICKER_TILE_COUNT = 10;
/** Lấy dư từ catalog-tiles (trộn L2/L3) rồi lọc L2 phía client — tránh gọi API riêng. */
const CATALOG_FETCH_LIMIT = 80;

/**
 * Khách chưa đăng nhập, chưa xem sản phẩm nào (không có tín hiệu gì) — thay vì đoán/hỏi
 * giới tính, hỏi trực tiếp muốn xem danh mục gì (danh mục cấp 2, đa dạng ngành hàng).
 * Bấm vào → lưu lựa chọn (để lần sau ghé lại tự mở đúng danh mục đó) + mở trang danh mục.
 */
export default function GuestCategoryPicker() {
  const [tiles, setTiles] = useState<HeroCategoryTile[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setError(false);
    apiClient
      .getCategoryCatalogTiles(CATALOG_FETCH_LIMIT)
      .then((res) => {
        if (cancelled) return;
        const level2 = (res.tiles || [])
          .filter((t) => t.level === 2 && t.product_count > 0)
          .sort((a, b) => b.product_count - a.product_count)
          .slice(0, PICKER_TILE_COUNT);
        setTiles(level2);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handlePick = (tile: HeroCategoryTile) => {
    const href = categoryTileHref(tile);
    setGuestCategoryInterest(href, tileTitle(tile));
    trackEvent('guest_category_picker_click', { category: tile.category, subcategory: tile.subcategory });
  };

  return (
    <div>
      <p className="mb-3 text-sm font-medium text-gray-700">Hôm nay bạn muốn xem gì?</p>
      {tiles === null && !error ? (
        <div className="flex flex-wrap gap-2" aria-hidden>
          {[...Array(8)].map((_, i) => (
            <div key={i} className="h-9 w-24 animate-pulse rounded-full bg-gray-100" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-gray-500">
          Không tải được danh mục gợi ý.{' '}
          <LoadingLink href="/danh-muc" className="font-semibold text-[#ea580c] hover:underline">
            Xem tất cả danh mục
          </LoadingLink>
        </p>
      ) : (tiles ?? []).length === 0 ? (
        <LoadingLink
          href="/danh-muc"
          className="inline-flex items-center rounded-full bg-[#ea580c] px-3 py-1.5 text-xs font-semibold text-white hover:bg-[#c2410c]"
        >
          Xem tất cả danh mục
        </LoadingLink>
      ) : (
        <div className="flex flex-wrap gap-2">
          {(tiles ?? []).map((tile) => (
            <LoadingLink
              key={`${tile.category}-${tile.subcategory}`}
              href={categoryTileHref(tile)}
              onClick={() => handlePick(tile)}
              className="inline-flex items-center gap-1.5 rounded-full border border-orange-200 bg-white px-3 py-1.5 text-xs font-semibold text-[#ea580c] transition-colors hover:bg-orange-50"
            >
              {tileTitle(tile)}
              {tile.product_count > 0 ? (
                <span className="text-[10px] font-normal text-gray-400">
                  {formatItemCount(tile.product_count)}
                </span>
              ) : null}
            </LoadingLink>
          ))}
          <LoadingLink
            href="/danh-muc"
            className="inline-flex items-center rounded-full bg-gray-50 px-3 py-1.5 text-xs font-semibold text-gray-600 hover:bg-gray-100"
          >
            Xem tất cả →
          </LoadingLink>
        </div>
      )}
    </div>
  );
}
