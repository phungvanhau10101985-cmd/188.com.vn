'use client';

import { useState, useEffect, useRef, useId, useMemo } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import type { CategoryLevel1, CategoryLevel2, CategoryLevel3 } from '@/types/api';
import { storePendingImageAndNavigate } from '@/lib/nanoai-pending-image';
import { useAuth } from '@/features/auth/hooks/useAuth';
import {
  PRODUCT_RELATED_TABS,
  parseRelatedTabFromSearch,
  buildHomeListingSearchParams,
  readStoredRelatedFilters,
  type ProductRelatedTabId,
} from '@/lib/product-related-tabs';

/** Cuộn xuống: ẩn logo (thu chiều cao). Cuộn lên gần đầu trang: hiện lại — hai ngưỡng tránh nhảy scroll */
const SCROLL_COLLAPSE_Y = 72;
const SCROLL_EXPAND_Y = 28;

function slugOf(s: string | undefined): string {
  return (s || '').trim().toLowerCase().replace(/\s+/g, '-');
}

function capitalizeFirst(s: string): string {
  if (!s || !s.length) return s;
  return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
}

interface MobileHeaderProps {
  cartItemsCount: number;
  favoriteItemsCount: number;
  suggestions: string[];
  onSuggestionClick: (term: string) => void;
  initialCategoryTree?: CategoryLevel1[];
}

export default function MobileHeader({
  cartItemsCount,
  favoriteItemsCount,
  suggestions,
  onSuggestionClick,
  initialCategoryTree = [],
}: MobileHeaderProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { isAuthenticated } = useAuth();
  const [searchTerm, setSearchTerm] = useState('');
  const [isScrolled, setIsScrolled] = useState(false);
  const [categoryPanelOpen, setCategoryPanelOpen] = useState(false);
  const [openL1, setOpenL1] = useState<Set<string>>(new Set());
  const [openL2, setOpenL2] = useState<Set<string>>(new Set());
  const panelRef = useRef<HTMLDivElement>(null);
  const mobileImageInputId = useId();

  const isHome = pathname === '/';

  /** Trang chủ có filter từ tab SP liên quan — vẫn hiện nút quay lại (về trang chi tiết / trước đó) */
  const hasHomeRelatedListingFilters =
    isHome &&
    Boolean(
      searchParams.get('shop_id')?.trim() ||
        searchParams.get('shop_name')?.trim() ||
        searchParams.get('pro_lower_price')?.trim() ||
        searchParams.get('pro_high_price')?.trim()
    );
  const showHeaderBack = !isHome || hasHomeRelatedListingFilters;

  /** /products/[slug] — hiển thị tab SP liên quan trong vùng cam (thay hàng gợi ý từ khóa) */
  const isProductDetailPage =
    pathname != null &&
    pathname.startsWith('/products/') &&
    pathname.split('/').filter(Boolean).length === 2;

  const isDaXemPage =
    pathname === '/da-xem' || (pathname != null && pathname.replace(/\/$/, '') === '/da-xem');

  const isAccountPage = Boolean(pathname?.startsWith('/account'));

  const isFavoritesPage =
    pathname === '/favorites' || (pathname != null && pathname.replace(/\/$/, '') === '/favorites');

  const isCartPage =
    pathname === '/cart' || (pathname != null && pathname.replace(/\/$/, '') === '/cart');

  const activeRelatedTab = parseRelatedTabFromSearch(searchParams.get('rt'));

  const setRelatedTab = (id: ProductRelatedTabId) => {
    if (!pathname) return;
    /** Trang chi tiết: mở trang chủ với filter (shop_id / shop_name / pro_*). Thiếu dữ liệu → chỉ đổi ?rt= như cũ */
    if (isProductDetailPage) {
      const listingParams = buildHomeListingSearchParams(id, readStoredRelatedFilters());
      if (listingParams) {
        router.push(`/?${listingParams.toString()}`);
        return;
      }
    }
    const params = new URLSearchParams(searchParams.toString());
    params.set('rt', id);
    const q = params.toString();
    router.replace(q ? `${pathname}?${q}` : pathname, { scroll: false });
  };

  useEffect(() => {
    if (isHome) {
      const q = searchParams.get('q') ?? '';
      setSearchTerm(q);
    }
  }, [isHome, searchParams]);

  useEffect(() => {
    const handleScroll = () => {
      const y = window.scrollY;
      setIsScrolled((prev) => {
        if (prev) return y > SCROLL_EXPAND_Y;
        return y > SCROLL_COLLAPSE_Y;
      });
    };
    handleScroll();
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  /** Đồng bộ chiều cao header → CSS var để sticky bar (vd. tabs SP cùng loại) nằm ngay dưới header, không chui sau header cam */
  useEffect(() => {
    const el = panelRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const apply = () => {
      const h = el.offsetHeight;
      if (h > 0) {
        document.documentElement.style.setProperty('--mobile-app-header-height', `${h}px`);
      }
    };
    apply();
    const ro = new ResizeObserver(apply);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const term = searchTerm.trim();
    onSuggestionClick(term || '');
  };

  const onImagePick = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = '';
    if (!f) return;
    try {
      await storePendingImageAndNavigate(f, router);
    } catch {
      router.push('/tim-theo-anh');
    }
  };

  const toggleL1 = (name: string) => {
    setOpenL1((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const toggleL2 = (key: string) => {
    setOpenL2((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const closePanelAndGo = (href: string) => {
    setCategoryPanelOpen(false);
    setOpenL1(new Set());
    setOpenL2(new Set());
    router.push(href);
  };

  const list = initialCategoryTree || [];

  /** Gợi ý tìm kiếm (đăng nhập) hoặc chip danh mục cấp 1 — tránh hàng trống dưới ô search */
  const searchStripContent = useMemo(() => {
    if (suggestions.length > 0) {
      return { mode: 'suggestions' as const, suggestions: suggestions.slice(0, 8) };
    }
    const cats = list.slice(0, 6);
    if (cats.length > 0) {
      return { mode: 'categories' as const, categories: cats };
    }
    return { mode: 'fallback' as const };
  }, [suggestions, list]);

  /** Trang chủ không nút Back — header gọn: logo nhỏ hơn một chút, thanh search pill một khối. */
  const compactHomeChrome = isHome && !showHeaderBack;
  /** Trang chi tiết SP, đã xem, khu cá nhân, hoặc yêu thích: chrome gọn. */
  const compactChrome =
    compactHomeChrome ||
    isProductDetailPage ||
    isDaXemPage ||
    isAccountPage ||
    isFavoritesPage ||
    isCartPage;
  /** Hàng nút + ô tìm: co chỗ cho ô tìm dài hơn. */
  const tightToolbar =
    isProductDetailPage || isDaXemPage || isAccountPage || isFavoritesPage || isCartPage;

  const chipClass =
    'flex-shrink-0 text-[11px] leading-tight font-medium text-white px-2 py-1 rounded-full bg-white/18 hover:bg-white/28 whitespace-nowrap border border-white/25 shadow-sm active:scale-[0.98] transition-transform';

  const iconBtn =
    'flex-shrink-0 min-w-[44px] min-h-[44px] w-11 h-11 shrink-0 flex items-center justify-center text-white rounded-xl bg-white/15 hover:bg-white/25 active:bg-white/35 transition-colors backdrop-blur-[2px]';
  /** Trang chi tiết: không dùng 44×44 để chừng chỗ cho ô tìm (vẫn đạt tap target ~40px). */
  const iconBtnCondensed =
    'flex-shrink-0 min-w-[40px] min-h-[40px] w-10 h-10 shrink-0 flex items-center justify-center text-white rounded-lg bg-white/15 hover:bg-white/25 active:bg-white/35 transition-colors backdrop-blur-[2px]';

  return (
    <div
      ref={panelRef}
      className="md:hidden sticky top-0 z-50 bg-[#f97316] pt-[env(safe-area-inset-top,0px)]"
    >
      <header className="bg-gradient-to-b from-[#f97316] to-[#ea580c] shadow-sm border-b border-orange-800/15">
        <div className={`px-2 sm:px-2.5 transition-[padding] duration-200 ${isScrolled ? 'pt-1 pb-1' : compactChrome ? 'pt-1 pb-1.5' : 'pt-1.5 pb-1'}`}>
          {/* Thu max-height khi cuộn — ResizeObserver cập nhật --mobile-app-header-height để thanh tabs SP cùng loại dính đúng dưới */}
          <div
            className={`flex justify-center shrink-0 items-center overflow-hidden transition-[max-height,opacity] duration-200 ease-out ${
              isScrolled
                ? 'max-h-0 opacity-0 pointer-events-none'
                : compactChrome
                  ? 'max-h-9 opacity-100'
                  : 'max-h-[2.75rem] opacity-100'
            }`}
            aria-hidden={isScrolled}
            {...(isScrolled ? ({ inert: true as const } as object) : {})}
          >
            <Link
              href="/"
              tabIndex={isScrolled ? -1 : undefined}
              className={`block ${isScrolled ? 'pointer-events-none' : ''}`}
              aria-hidden={isScrolled}
            >
              <Image
                src="https://188comvn.b-cdn.net/logo%20head%20188.png"
                alt="188.com.vn"
                width={200}
                height={40}
                className={`w-auto object-contain block ${compactChrome ? 'h-8' : 'h-10 sm:h-11'}`}
                priority={
                  compactHomeChrome &&
                  !isProductDetailPage &&
                  !isDaXemPage &&
                  !isAccountPage &&
                  !isFavoritesPage &&
                  !isCartPage
                }
              />
            </Link>
          </div>

          {/* Danh mục + ô tìm kiếm (pill) + icon nhanh */}
          <div
            className={`flex items-center gap-1 relative z-10 pt-0.5 ${tightToolbar ? 'gap-1' : 'gap-1.5'} ${
              isDaXemPage || isAccountPage || isFavoritesPage || isCartPage ? 'pb-1' : ''
            }`}
          >
            {showHeaderBack && (
              <button
                type="button"
                onClick={() => router.back()}
                className={tightToolbar ? iconBtnCondensed : iconBtn}
                aria-label="Quay lại"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
              </button>
            )}

            <button
              type="button"
              onClick={() => setCategoryPanelOpen((o) => !o)}
              className={`${tightToolbar ? iconBtnCondensed : iconBtn} ${categoryPanelOpen ? '!bg-white/35 ring-1 ring-white/40' : ''}`}
              aria-label="Danh mục"
              aria-expanded={categoryPanelOpen}
            >
              <svg className="w-[22px] h-[22px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>

            <form
              onSubmit={handleSearch}
              className={`flex-1 min-w-0 flex items-stretch rounded-xl bg-white shadow-[0_1px_3px_rgba(0,0,0,0.08)] ring-1 ring-black/[0.06] overflow-hidden touch-manipulation ${tightToolbar ? 'h-10 min-h-[40px]' : 'h-11'}`}
            >
              <input
                id={mobileImageInputId}
                type="file"
                accept="image/jpeg,image/png,image/webp,image/gif"
                className="sr-only"
                tabIndex={-1}
                onChange={onImagePick}
              />
              <div className="flex flex-1 min-w-0 items-center gap-2 pl-2.5 pr-1">
                <span className="text-gray-400 shrink-0" aria-hidden>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                </span>
                <input
                  type="text"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  placeholder={
                    compactHomeChrome
                      ? 'Tìm trên 188.COM.VN…'
                      : tightToolbar
                        ? 'Tìm trên 188…'
                        : 'Tìm sản phẩm…'
                  }
                  autoComplete="off"
                  enterKeyHint="search"
                  className={`flex-1 min-w-0 h-full bg-transparent border-0 text-gray-900 placeholder:text-gray-500 focus:ring-0 focus:outline-none ${tightToolbar ? 'text-sm' : 'text-[15px]'}`}
                />
              </div>
              <div className="flex shrink-0 self-stretch divide-x divide-gray-200/90 border-l border-gray-100">
                <label
                  htmlFor={mobileImageInputId}
                  className={`flex items-center justify-center text-gray-500 hover:text-[#ea580c] hover:bg-orange-50/90 active:bg-orange-100 cursor-pointer transition-colors ${tightToolbar ? 'w-10 min-h-[40px]' : 'w-11 min-h-[44px]'}`}
                  aria-label="Tìm bằng ảnh"
                  title="Tìm theo ảnh (NanoAI)"
                >
                  <svg className="w-[18px] h-[18px] pointer-events-none" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                </label>
                <button
                  type="submit"
                  className={`flex items-center justify-center bg-[#ea580c] text-white hover:bg-[#c2410c] active:bg-orange-800 transition-colors ${tightToolbar ? 'w-10 min-h-[40px]' : 'w-11 min-h-[44px]'}`}
                  aria-label="Tìm trên 188"
                >
                  <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.25} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                </button>
              </div>
            </form>

            {!isDaXemPage && (
              <Link href="/da-xem" className={tightToolbar ? iconBtnCondensed : iconBtn} aria-label="Đã xem" title="Đã xem">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
              </Link>
            )}

            {/* Trang chủ: thanh nút thoáng — thông báo đã có ở bottom nav */}
            {isAuthenticated && !compactChrome && (
              <Link href="/account/notifications" className={`${iconBtn} relative`} aria-label="Thông báo" title="Thông báo">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                </svg>
              </Link>
            )}

            {!isCartPage && (
              <Link href="/cart" className={`${tightToolbar ? iconBtnCondensed : iconBtn} relative`} aria-label="Giỏ hàng" title="Giỏ hàng">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
                </svg>
                {cartItemsCount > 0 && (
                  <span className="absolute -right-px -top-px bg-white text-[#ea580c] rounded-full min-w-[11px] h-3 px-0.5 text-[7px] sm:text-[8px] flex items-center justify-center font-semibold leading-none shadow-sm ring-1 ring-black/5">
                    {cartItemsCount > 99 ? '99+' : cartItemsCount}
                  </span>
                )}
              </Link>
            )}
          </div>

          {/* Trang chi tiết SP: danh mục SP liên quan trong vùng cam — không để khoảng trống; các trang khác: gợi ý từ khóa */}
          {isProductDetailPage ? (
            <div
              className={`flex mt-1 -mx-0.5 px-0.5 overflow-x-auto scrollbar-hide snap-x snap-mandatory ${isScrolled ? 'gap-1 pb-0.5 pt-0' : 'gap-1.5 pb-1'}`}
              role="tablist"
              aria-label="Nhóm sản phẩm liên quan"
            >
              {PRODUCT_RELATED_TABS.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={activeRelatedTab === tab.id}
                  onClick={() => setRelatedTab(tab.id)}
                  className={`flex-shrink-0 rounded-full font-medium whitespace-nowrap transition-colors snap-start ${
                    isScrolled ? 'px-2 py-0.5 text-[10px] leading-tight' : 'px-2.5 py-1 text-[11px]'
                  } ${
                    activeRelatedTab === tab.id
                      ? 'bg-white text-[#ea580c] shadow-sm'
                      : 'bg-white/15 text-white border border-white/25 hover:bg-white/25'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          ) : isDaXemPage || isAccountPage || isFavoritesPage || isCartPage ? null : (
            <div
              className="flex items-center gap-1 mt-1 pb-1 overflow-x-auto scrollbar-hide min-h-[26px] -mx-0.5 px-0.5"
              role="navigation"
              aria-label={
                searchStripContent.mode === 'suggestions'
                  ? 'Gợi ý tìm kiếm'
                  : searchStripContent.mode === 'categories'
                    ? 'Danh mục nhanh'
                    : 'Truy cập nhanh'
              }
            >
              <div className="flex flex-nowrap items-center gap-1 min-w-0">
                {searchStripContent.mode === 'suggestions' &&
                  searchStripContent.suggestions.map((term) => (
                    <button
                      key={term}
                      type="button"
                      onClick={() => onSuggestionClick(term)}
                      className={chipClass}
                    >
                      {term}
                    </button>
                  ))}
                {searchStripContent.mode === 'categories' &&
                  searchStripContent.categories.map((cat) => {
                    const slug = cat.slug || slugOf(cat.name);
                    return (
                      <button
                        key={cat.name}
                        type="button"
                        onClick={() => router.push(`/danh-muc/${encodeURIComponent(slug)}`)}
                        className={chipClass}
                      >
                        {cat.name}
                      </button>
                    );
                  })}
                {searchStripContent.mode === 'fallback' && (
                  <>
                    <button type="button" onClick={() => setCategoryPanelOpen(true)} className={chipClass}>
                      Danh mục
                    </button>
                    <Link href="/tim-theo-anh" className={chipClass}>
                      Tìm ảnh
                    </Link>
                    <Link href="/cart" className={chipClass}>
                      Giỏ hàng
                    </Link>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </header>

      {categoryPanelOpen && (
        <>
          <button
            type="button"
            aria-label="Đóng"
            className="fixed inset-0 bg-black/40 z-40"
            onClick={() => setCategoryPanelOpen(false)}
          />
          <div className="absolute left-0 right-0 top-full z-50 max-h-[70vh] overflow-y-auto bg-white shadow-xl rounded-b-lg border-t border-gray-200 transition-all duration-200">
            <nav className="py-2" aria-label="Danh mục sản phẩm">
              {list.map((cat) => {
                const slug1 = cat.slug || slugOf(cat.name);
                const hasChildren = cat.children && cat.children.length > 0;
                const isOpen = openL1.has(cat.name);

                return (
                  <div key={cat.name} className="border-b border-gray-100">
                    <div className="flex items-center w-full py-3 px-4 text-gray-900 font-medium text-sm active:bg-gray-50">
                      <button
                        type="button"
                        onClick={() => closePanelAndGo(`/danh-muc/${encodeURIComponent(slug1)}`)}
                        className="flex-1 text-left min-w-0 uppercase hover:text-[#ea580c] transition-colors"
                      >
                        {cat.name}
                      </button>
                      {hasChildren ? (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.preventDefault();
                            toggleL1(cat.name);
                          }}
                          className="flex-shrink-0 p-1 -m-1 text-[#ea580c]"
                          aria-label={isOpen ? 'Thu gọn' : 'Mở rộng'}
                        >
                          <svg className={`w-5 h-5 transition-transform ${isOpen ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                          </svg>
                        </button>
                      ) : null}
                    </div>
                    {hasChildren && isOpen && cat.children && (
                      <div className="bg-gray-50 border-t border-gray-100 grid grid-cols-2 gap-2 px-3 py-3">
                        {(cat.children as CategoryLevel2[]).map((c2) => {
                          const slug2 = c2.slug || slugOf(c2.name);
                          const hasL3 = c2.children && c2.children.length > 0;
                          const keyL2 = `${slug1}/${slug2}`;
                          const isOpenL2 = openL2.has(keyL2);

                          return (
                            <div key={c2.name} className="border border-gray-200 rounded-lg bg-white overflow-hidden">
                              <div className="flex items-center w-full py-2.5 px-3 text-gray-800 font-medium text-sm min-h-[44px]">
                                <button
                                  type="button"
                                  onClick={() =>
                                    closePanelAndGo(`/danh-muc/${encodeURIComponent(slug1)}/${encodeURIComponent(slug2)}`)
                                  }
                                  className="flex-1 text-left min-w-0 line-clamp-2 hover:text-[#ea580c] transition-colors"
                                >
                                  {capitalizeFirst(c2.name)}
                                </button>
                                {hasL3 ? (
                                  <button
                                    type="button"
                                    onClick={(e) => {
                                      e.preventDefault();
                                      toggleL2(keyL2);
                                    }}
                                    className="flex-shrink-0 p-1 -m-1 text-[#ea580c]"
                                    aria-label={isOpenL2 ? 'Thu gọn' : 'Mở rộng'}
                                  >
                                    <svg className={`w-5 h-5 transition-transform ${isOpenL2 ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                                    </svg>
                                  </button>
                                ) : null}
                              </div>
                              {hasL3 && isOpenL2 && c2.children && (
                                <div className="bg-gray-100/80 border-t border-gray-100">
                                  {(c2.children as CategoryLevel3[]).map((c3) => {
                                    const slug3 = c3.slug || slugOf(c3.name);
                                    return (
                                      <button
                                        key={c3.name}
                                        type="button"
                                        onClick={() =>
                                          closePanelAndGo(
                                            `/danh-muc/${encodeURIComponent(slug1)}/${encodeURIComponent(slug2)}/${encodeURIComponent(slug3)}`
                                          )
                                        }
                                        className="flex items-center w-full py-2 px-3 text-gray-500 font-medium text-xs active:bg-gray-200 border-b border-gray-100 last:border-b-0 text-left hover:text-[#ea580c] transition-colors"
                                      >
                                        {capitalizeFirst(c3.name)}
                                      </button>
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
                );
              })}
            </nav>
          </div>
        </>
      )}
    </div>
  );
}
