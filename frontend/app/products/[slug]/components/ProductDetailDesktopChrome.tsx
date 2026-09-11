'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import type { Product } from '@/types/api';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { useCart } from '@/features/cart/hooks/useCart';
import { useFavorites } from '@/features/favorites/hooks/useFavorites';
import { usePersonalizedCategoryTree } from '@/lib/use-personalized-category-tree';
import { useAppCategoryTreeBase } from '@/lib/app-category-tree-context';
import { useLoginRedirectHref } from '@/lib/use-login-redirect-href';
import {
  persistRelatedFiltersFromProduct,
  buildHomeListingSearchParams,
  filtersFromProduct,
  searchParamsToEncodedQueryString,
} from '@/lib/product-related-tabs';
import { cdnUrl } from '@/lib/cdn-url';
import { getStorefrontHomeHref } from '@/lib/admin-origin';
import { MOBILE_SEARCH_HREF } from '@/lib/mobile-search-path';
import LazyDesktopImageSearchPopover from '@/components/LazyDesktopImageSearchPopover';
import ProductHeader from './ProductHeader/ProductHeader';

interface ProductDetailDesktopChromeProps {
  product: Product;
}

/**
 * Breadcrumb + thanh «cùng loại» trên PDP desktop.
 * Khi cuộn, thanh này ghim thành head rút gọn (logo / tìm / icon).
 */
export default function ProductDetailDesktopChrome({ product }: ProductDetailDesktopChromeProps) {
  const appCategoryTree = useAppCategoryTreeBase();
  const categoryTree = usePersonalizedCategoryTree(appCategoryTree.length > 0 ? appCategoryTree : undefined);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [openLevel1, setOpenLevel1] = useState<string | null>(null);
  const [isStickyPinned, setIsStickyPinned] = useState(false);
  const stickyBarRef = useRef<HTMLDivElement>(null);
  const menuCloseTimerRef = useRef<number | null>(null);
  const { getCartItemCount } = useCart();
  const { isAuthenticated, user, isLoading: authLoading } = useAuth();
  const [accountNavReady, setAccountNavReady] = useState(false);
  const { favoriteCount } = useFavorites();
  const loginHref = useLoginRedirectHref();

  useEffect(() => {
    persistRelatedFiltersFromProduct(product);
  }, [product]);

  useEffect(() => {
    setAccountNavReady(true);
  }, []);

  useEffect(() => {
    if (categoryTree.length && !openLevel1) setOpenLevel1(categoryTree[0].name);
  }, [categoryTree, openLevel1]);

  useEffect(() => {
    let rafId = 0;
    const measure = () => {
      rafId = 0;
      if (!stickyBarRef.current) return;
      const rect = stickyBarRef.current.getBoundingClientRect();
      setIsStickyPinned(rect.top <= 0);
    };
    const handleScroll = () => {
      if (rafId) return;
      rafId = requestAnimationFrame(measure);
    };
    measure();
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', handleScroll);
      if (rafId) cancelAnimationFrame(rafId);
    };
  }, []);

  const handleMenuEnter = () => {
    if (menuCloseTimerRef.current) {
      window.clearTimeout(menuCloseTimerRef.current);
      menuCloseTimerRef.current = null;
    }
    setIsMenuOpen(true);
    if (!openLevel1 && categoryTree.length) setOpenLevel1(categoryTree[0].name);
  };

  const handleMenuLeave = () => {
    if (menuCloseTimerRef.current) window.clearTimeout(menuCloseTimerRef.current);
    menuCloseTimerRef.current = window.setTimeout(() => setIsMenuOpen(false), 150);
  };

  const openCategory = categoryTree.find((c) => c.name === openLevel1);
  const displayCartCount = getCartItemCount();

  const homeListingParams = useMemo(() => {
    const f = filtersFromProduct(product);
    return {
      bestselling: buildHomeListingSearchParams('bestselling', f),
      lower: buildHomeListingSearchParams('lower_price', f),
      same: buildHomeListingSearchParams('same_price', f),
      higher: buildHomeListingSearchParams('higher_price', f),
    };
  }, [product]);

  return (
    <>
      <ProductHeader product={product} />
      <div
        ref={stickyBarRef}
        className={`sticky top-0 left-0 right-0 z-[30] overflow-visible backdrop-blur border-b border-gray-100 ${isStickyPinned ? 'bg-[#ea580c]' : 'bg-white/95'}`}
      >
        <div className="max-w-7xl mx-auto px-4 py-0">
          <div className="grid grid-cols-[minmax(12rem,17.33rem)_minmax(0,1fr)_9.33rem] items-center gap-2 md:gap-3 xl:grid-cols-[minmax(13.33rem,21.33rem)_minmax(0,1fr)_9.33rem]">
            <div className={`min-w-0 overflow-visible ${isStickyPinned ? '' : 'pointer-events-none opacity-0'}`}>
              <div className="flex min-w-0 items-center gap-2">
                <Link
                  href={getStorefrontHomeHref()}
                  className="flex shrink-0 items-center rounded-md py-0.5 hover:bg-white/10 transition-colors"
                  aria-label="Về trang chủ 188.com.vn"
                >
                  <Image
                    src={cdnUrl('/logo head 188.png')}
                    data-allow-png
                    alt="188.com.vn"
                    width={140}
                    height={35}
                    className="h-7 w-auto max-w-[6.5rem] md:max-w-[8rem] object-contain object-left"
                  />
                </Link>
                <div
                  className="relative"
                  onMouseEnter={handleMenuEnter}
                  onMouseLeave={handleMenuLeave}
                >
                  <button
                    type="button"
                    className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-[11px] font-medium bg-white/20 text-white hover:bg-white/30 shadow-sm whitespace-nowrap"
                  >
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                    </svg>
                    Danh mục
                  </button>

                  {isStickyPinned && isMenuOpen && (
                    <div
                      className="absolute left-0 top-full mt-0 w-[720px] bg-white border border-gray-200 shadow-lg rounded-xl overflow-hidden z-[40] py-2"
                      onMouseEnter={handleMenuEnter}
                      onMouseLeave={handleMenuLeave}
                    >
                      <div className="grid grid-cols-[220px_1fr]">
                        <div className="bg-gray-50/80 border-r border-gray-100 p-3">
                          <div className="grid grid-cols-1 gap-1">
                            {categoryTree.length === 0 && (
                              <div className="text-xs text-gray-500">Chưa có danh mục.</div>
                            )}
                            {categoryTree.map((level1) => {
                              const slug1 = level1.slug || level1.name;
                              const isActive = openLevel1 === level1.name;
                              return (
                                <Link
                                  key={level1.name}
                                  href={`/danh-muc/${encodeURIComponent(slug1)}`}
                                  onMouseEnter={() => setOpenLevel1(level1.name)}
                                  className={`px-2.5 py-2 rounded-md text-xs font-medium truncate ${
                                    isActive ? 'bg-orange-50 text-orange-700' : 'text-gray-700 hover:bg-white'
                                  }`}
                                >
                                  {level1.name}
                                </Link>
                              );
                            })}
                          </div>
                        </div>
                        <div className="p-3">
                          {!openCategory && (
                            <div className="text-xs text-gray-500">Di chuột vào danh mục để xem cấp 2, cấp 3.</div>
                          )}
                          {openCategory && (
                            <div className="grid grid-cols-2 gap-3">
                              {openCategory.children.map((level2) => {
                                const slug1 = openCategory.slug || openCategory.name;
                                const slug2 = level2.slug || level2.name;
                                return (
                                  <div key={level2.name} className="min-w-0">
                                    <Link
                                      href={`/danh-muc/${encodeURIComponent(slug1)}/${encodeURIComponent(slug2)}`}
                                      className="block text-xs font-semibold text-gray-800 hover:text-[#ea580c]"
                                    >
                                      {level2.name}
                                    </Link>
                                    {level2.children && level2.children.length > 0 && (
                                      <div className="mt-1 flex flex-col gap-1">
                                        {level2.children.map((level3) => {
                                          const name3 = level3.name;
                                          const slug3 = level3.slug || level3.name;
                                          return (
                                            <Link
                                              key={name3}
                                              href={`/danh-muc/${encodeURIComponent(slug1)}/${encodeURIComponent(slug2)}/${encodeURIComponent(slug3)}`}
                                              className="text-[11px] text-gray-600 hover:text-[#ea580c] truncate"
                                            >
                                              {name3}
                                            </Link>
                                          );
                                        })}
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
                <div className="relative z-[105] ml-2 flex w-full min-w-[8rem] flex-1 items-stretch overflow-hidden rounded-lg bg-white lg:ml-3">
                  <Link
                    href={MOBILE_SEARCH_HREF}
                    className="flex min-w-0 flex-1 items-center py-1.5 pl-2.5 pr-1.5 text-xs text-gray-500 hover:text-gray-700"
                    aria-label="Mở trang tìm kiếm"
                  >
                    Tìm kiếm...
                  </Link>
                  <div className="flex shrink-0 items-center gap-0.5 border-l border-gray-100/80 bg-white px-1">
                    <LazyDesktopImageSearchPopover
                      panelZClass="z-[110]"
                      triggerPosition="inline-end"
                      triggerButtonClassName="text-gray-500 hover:text-[#ea580c] p-0.5 rounded-md focus:outline-none focus:ring-2 focus:ring-[#ea580c]/40 [&_svg]:h-4 [&_svg]:w-4"
                    />
                    <Link
                      href={MOBILE_SEARCH_HREF}
                      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-gray-500 hover:text-[#ea580c]"
                      aria-label="Mở trang tìm kiếm"
                    >
                      <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                        />
                      </svg>
                    </Link>
                  </div>
                </div>
              </div>
            </div>

            <div className={`flex flex-wrap items-center justify-center gap-2 ${isStickyPinned ? 'bg-transparent px-2 py-1.5' : 'bg-[#ea580c] rounded-lg px-2 py-1.5'}`}>
              {homeListingParams.bestselling && (
                <Link
                  href={`/?${searchParamsToEncodedQueryString(homeListingParams.bestselling)}`}
                  className="px-2.5 py-1.5 rounded-md text-xs font-semibold text-white bg-white/20 hover:bg-white/30 transition-colors"
                >
                  Sản phẩm bán chạy
                </Link>
              )}
              {homeListingParams.lower && (
                <Link
                  href={`/?${searchParamsToEncodedQueryString(homeListingParams.lower)}`}
                  className="px-2.5 py-1.5 rounded-md text-xs font-semibold text-white bg-white/20 hover:bg-white/30 transition-colors"
                >
                  Cùng loại giá thấp hơn
                </Link>
              )}
              {homeListingParams.same && (
                <Link
                  href={`/?${searchParamsToEncodedQueryString(homeListingParams.same)}`}
                  className="px-2.5 py-1.5 rounded-md text-xs font-semibold text-white bg-white/20 hover:bg-white/30 transition-colors"
                >
                  Cùng loại cùng tầm giá
                </Link>
              )}
              {homeListingParams.higher && (
                <Link
                  href={`/?${searchParamsToEncodedQueryString(homeListingParams.higher)}`}
                  className="px-2.5 py-1.5 rounded-md text-xs font-semibold text-white bg-white/20 hover:bg-white/30 transition-colors"
                >
                  Cùng loại giá cao hơn
                </Link>
              )}
            </div>

            <div className={`justify-self-end ${isStickyPinned ? '' : 'pointer-events-none opacity-0'}`}>
              <div className="flex h-5 items-center gap-4 px-2">
                <Link href="/da-xem" className="flex items-center text-white/90 hover:text-white transition-colors group">
                  <div className="w-5 h-5 bg-white/20 rounded-full flex items-center justify-center group-hover:bg-white/30 transition-colors">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  </div>
                </Link>

                {accountNavReady && !authLoading ? (
                  isAuthenticated ? (
                    <Link href="/account" className="flex items-center text-white/90 hover:text-white transition-colors group">
                      <div className="w-5 h-5 bg-white/20 rounded-full flex items-center justify-center group-hover:bg-white/30 transition-colors">
                        <span className="text-white font-semibold text-[11px]">
                          {user?.full_name?.charAt(0) || 'U'}
                        </span>
                      </div>
                    </Link>
                  ) : (
                    <Link href={loginHref} className="flex items-center text-white/90 hover:text-white transition-colors group">
                      <div className="w-5 h-5 bg-white/20 rounded-full flex items-center justify-center group-hover:bg-white/30 transition-colors">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                        </svg>
                      </div>
                    </Link>
                  )
                ) : (
                  <div
                    className="flex h-5 items-center text-white/90"
                    aria-busy="true"
                    aria-label="Đang kiểm tra đăng nhập"
                  >
                    <div className="h-5 w-5 shrink-0 rounded-full bg-white/15" />
                  </div>
                )}

                <Link href="/favorites" className="flex items-center text-white/90 hover:text-white transition-colors group relative">
                  <div className="w-5 h-5 bg-white/20 rounded-full flex items-center justify-center group-hover:bg-white/30 transition-colors relative">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
                    </svg>
                    {favoriteCount > 0 && (
                      <span className="absolute -right-px -top-px bg-white text-[#ea580c] rounded-full min-w-[11px] h-3 px-0.5 text-[7px] sm:text-[8px] flex items-center justify-center font-semibold leading-none shadow-sm ring-1 ring-black/5">
                        {favoriteCount}
                      </span>
                    )}
                  </div>
                </Link>

                <Link href="/cart" className="flex items-center text-white/90 hover:text-white transition-colors group relative">
                  <div className="w-5 h-5 bg-white/20 rounded-full flex items-center justify-center group-hover:bg-white/30 transition-colors relative">
                    <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
                    </svg>
                    {displayCartCount > 0 && (
                      <span className="absolute -right-px -top-px bg-white text-[#ea580c] rounded-full min-w-[11px] h-3 px-0.5 text-[7px] sm:text-[8px] flex items-center justify-center font-semibold leading-none shadow-sm ring-1 ring-black/5">
                        {displayCartCount}
                      </span>
                    )}
                  </div>
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
