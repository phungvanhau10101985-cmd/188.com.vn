// components/AppShell.tsx - Header + Navigation + Footer xuyên suốt tất cả các trang
'use client';

import { useState, useEffect, useMemo, useRef, useLayoutEffect, useCallback, type CSSProperties } from 'react';
import dynamic from 'next/dynamic';
import { usePathname, useSearchParams, useRouter } from 'next/navigation';
import Header from '@/components/Header';
import Footer from '@/components/Footer';
import Navigation from '@/components/Navigation';
import MobileHeader from '@/components/mobile/MobileHeader';
import MobileBottomNav from '@/components/mobile/MobileBottomNav';
import BackToTopButton from '@/components/BackToTopButton';
import FloatingShopVideoFeedButton from '@/components/FloatingShopVideoFeedButton';
import PwaInstallPrompt from '@/components/PwaInstallPrompt';

const CartAddedPopup = dynamic(() => import('@/components/CartAddedPopup'), { ssr: false });
const BirthGenderSalePromptModal = dynamic(
  () => import('@/components/BirthGenderSalePromptModal'),
  { ssr: false }
);
const BirthdayPromoWelcomeModal = dynamic(
  () => import('@/components/BirthdayPromoWelcomeModal'),
  { ssr: false }
);
import { useAuth } from '@/features/auth/hooks/useAuth';
import { useCart } from '@/features/cart/hooks/useCart';
import { useFavorites } from '@/features/favorites/hooks/useFavorites';
import { apiClient } from '@/lib/api-client';
import { navigateProductTextSearch } from '@/lib/navigate-product-text-search';
import { searchParamsToEncodedQueryString } from '@/lib/product-related-tabs';
import type { CategoryLevel1 } from '@/types/api';
import { usePersonalizedCategoryTree } from '@/lib/use-personalized-category-tree';
import {
  captureReferralFromUrl,
  clearReferralAfterAttribute,
  getStoredReferralCode,
  markReferralAttributed,
  shouldTryAttributeReferral,
} from '@/lib/affiliate-ref';

/** Chiều cao thanh cam mỏng (logo + tìm + icon) khi trang listing ghim header đã thu gọn — khớp offset sticky bộ lọc. */
const DESKTOP_LISTING_THIN_CHROME_PX = 54;

interface AppShellProps {
  children: React.ReactNode;
  /** Cây danh mục từ server (layout) để thanh danh mục hiển thị ngay, không phụ thuộc fetch client */
  initialCategoryTree?: CategoryLevel1[];
}

export default function AppShell({ children, initialCategoryTree }: AppShellProps) {
  const categoryTree = usePersonalizedCategoryTree(initialCategoryTree);
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const { getCartItemCount } = useCart();
  const { favoriteCount } = useFavorites();
  const [viewedProductsCount, setViewedProductsCount] = useState(0);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [headerVisible, setHeaderVisible] = useState(true);

  const qFromUrl = searchParams.get('q') ?? '';
  const isAuthPage = pathname?.startsWith('/auth/');
  const isProductDetailPage = pathname?.match(/^\/products\/[^/]+$/);
  const pathNorm = pathname != null ? pathname.replace(/\/$/, '') || '/' : '/';
  const isShopVideoFeedPage = pathNorm === '/luot-video-cung-shop';

  /** Quay về trang chủ từ route khác: luôn cuộn đầu trang (tránh BF cache / khôi phục scroll cũ xuống cuối). */
  const prevPathnameForHomeScrollRef = useRef<string | null>(null);
  const pathSegIsHome = (p: string | null | undefined) => {
    if (p == null || p === '') return false;
    return (p.replace(/\/$/, '') || '/') === '/';
  };
  useLayoutEffect(() => {
    const prev = prevPathnameForHomeScrollRef.current;
    prevPathnameForHomeScrollRef.current = pathname ?? '';

    const nowHome = pathSegIsHome(pathname ?? null);
    const wasHome = pathSegIsHome(prev);

    if (nowHome && prev != null && !wasHome) {
      window.scrollTo(0, 0);
      const root = document.scrollingElement;
      if (root) root.scrollTop = 0;
      requestAnimationFrame(() => {
        window.scrollTo(0, 0);
        const r = document.scrollingElement;
        if (r) r.scrollTop = 0;
      });
    }
  }, [pathname]);

  /**
   * Cố định khối desktop: header cam + thanh danh mục — `--listing-chrome-height` (spacer) và
   * `--listing-filter-sticky-top` (vị trí sticky bộ lọc, có bù khi head mỏng).
   */
  const keepDesktopHeaderPinned = useMemo(() => {
    if (pathname?.startsWith('/info')) return true;
    if (pathname?.startsWith('/danh-muc')) return true;
    if (pathname?.startsWith('/c/')) return true;
    const home =
      pathname === '/' ||
      pathname === '' ||
      (pathname != null && pathname.replace(/\/$/, '') === '');
    if (!home) return false;
    const t = (k: string) => (searchParams.get(k) ?? '').trim();
    if (t('q')) return true;
    if (t('shop_id')) return true;
    if (t('shop_name')) return true;
    if (t('pro_lower_price')) return true;
    if (t('pro_high_price')) return true;
    if (t('shop_name_chinese')) return true;
    if (t('sxc')) return true;
    if (t('chinese_name')) return true;
    if (t('style')) return true;
    if (t('min_price')) return true;
    if (t('max_price')) return true;
    if (t('size')) return true;
    if (t('color')) return true;
    if (t('sort')) return true;
    if (t('category')) return true;
    if (t('subcategory')) return true;
    if (t('sub_subcategory')) return true;
    const page = searchParams.get('page');
    if (page != null && page.trim() !== '') {
      const n = Number(page);
      if (Number.isFinite(n) && n > 1) return true;
    }
    return false;
  }, [pathname, searchParams]);

  /** Trang /info: luôn full chrome; /danh-muc, /c/, tr chủ lọc: cuộn xuống → header mỏng + ẩn pill. */
  const useListingThinOnScroll =
    keepDesktopHeaderPinned && pathname != null && !pathname.startsWith('/info');

  const [pinnedListingCompact, setPinnedListingCompact] = useState(false);

  /** Ngưỡng co kéo có độ trễ: spacer đổi cao có thể kéo `scrollY` lùi về dưới ngưỡng → bật/tắt nhanh (nhấp nháy). */
  const LISTING_COMPACT_ENTER_Y = 100;
  const LISTING_COMPACT_EXIT_Y = 48;

  const applyPinnedListingCompact = useCallback(
    (y: number, prevCompact: boolean) =>
      prevCompact ? y >= LISTING_COMPACT_EXIT_Y : y >= LISTING_COMPACT_ENTER_Y,
    [],
  );

  useEffect(() => {
    if (!useListingThinOnScroll || typeof window === 'undefined') return;
    const onScroll = () => {
      setPinnedListingCompact((prev) =>
        applyPinnedListingCompact(window.scrollY, prev),
      );
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, [useListingThinOnScroll, applyPinnedListingCompact]);

  useLayoutEffect(() => {
    if (!useListingThinOnScroll) {
      setPinnedListingCompact(false);
      return;
    }
    if (typeof window === 'undefined') return;
    setPinnedListingCompact((prev) =>
      applyPinnedListingCompact(window.scrollY, prev),
    );
  }, [pathname, searchParams, useListingThinOnScroll, applyPinnedListingCompact]);

  /** Chiều cao khối chrome cố định — spacer đẩy main, tránh nội dung chui dưới fixed bar */
  const listingChromeRef = useRef<HTMLDivElement>(null);
  const [listingChromeHeight, setListingChromeHeight] = useState(168);
  const [measuredThinChromePx, setMeasuredThinChromePx] = useState(0);

  const reportDesktopThinChromeHeight = useCallback((px: number) => {
    const rounded = Math.max(0, Math.ceil(px));
    setMeasuredThinChromePx((prev) => (prev === rounded ? prev : rounded));
  }, []);

  useLayoutEffect(() => {
    if (!keepDesktopHeaderPinned) return;
    if (useListingThinOnScroll && pinnedListingCompact) {
      const h =
        measuredThinChromePx > 0 ? measuredThinChromePx : DESKTOP_LISTING_THIN_CHROME_PX;
      setListingChromeHeight(h);
      return;
    }
    const el = listingChromeRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const apply = () => {
      const h = el.offsetHeight;
      if (h > 0) setListingChromeHeight(h);
    };
    apply();
    const ro = new ResizeObserver(apply);
    ro.observe(el);
    return () => ro.disconnect();
  }, [keepDesktopHeaderPinned, useListingThinOnScroll, pinnedListingCompact, measuredThinChromePx]);

  useEffect(() => {
    if (isAuthenticated) {
      apiClient.getSearchSuggestions(12)
        .then((r) => setSuggestions(r.suggestions || []))
        .catch(() => setSuggestions([]));
      return;
    }
    if (typeof window === 'undefined') return;
    try {
      const raw = localStorage.getItem('latest_search_suggestions');
      const parsed = raw ? JSON.parse(raw) : null;
      setSuggestions(Array.isArray(parsed?.suggestions) ? parsed.suggestions : []);
    } catch {
      setSuggestions([]);
    }
  }, [isAuthenticated, qFromUrl]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    captureReferralFromUrl(window.location.search || `?${searchParams.toString()}`);
  }, [searchParams]);

  useEffect(() => {
    if (!isAuthenticated || !shouldTryAttributeReferral()) return;
    const code = getStoredReferralCode();
    if (!code) return;
    apiClient
      .attributeAffiliateReferral(code)
      .then(() => {
        markReferralAttributed();
        clearReferralAfterAttribute();
      })
      .catch(() => {
        markReferralAttributed();
      });
  }, [isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated) {
      setViewedProductsCount(0);
      return;
    }
    let cancelled = false;
    apiClient
      .getViewedProducts(99)
      .then((list) => {
        if (!cancelled) setViewedProductsCount(Array.isArray(list) ? list.length : 0);
      })
      .catch(() => {
        if (!cancelled) setViewedProductsCount(0);
      });
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, pathname]);

  /** Đăng nhập/đăng xuất qua event: refetch vì `user` trong LS đổi trước khi React cập nhật isAuthenticated (vd. logout). */
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onAuthSession = () => {
      const authed = !!localStorage.getItem('user');
      if (!authed) {
        setViewedProductsCount(0);
        try {
          const raw = localStorage.getItem('latest_search_suggestions');
          const parsed = raw ? JSON.parse(raw) : null;
          setSuggestions(Array.isArray(parsed?.suggestions) ? parsed.suggestions : []);
        } catch {
          setSuggestions([]);
        }
        return;
      }
      apiClient
        .getSearchSuggestions(12)
        .then((r) => setSuggestions(r.suggestions || []))
        .catch(() => setSuggestions([]));
      apiClient
        .getViewedProducts(99)
        .then((list) => setViewedProductsCount(Array.isArray(list) ? list.length : 0))
        .catch(() => setViewedProductsCount(0));
    };
    window.addEventListener('188-auth-session-changed', onAuthSession);
    return () => window.removeEventListener('188-auth-session-changed', onAuthSession);
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (isProductDetailPage || keepDesktopHeaderPinned) {
      setHeaderVisible(true);
      return;
    }

    const headerRevealY = 80;
    const onScroll = () => {
      const y = window.scrollY;
      setHeaderVisible(y <= headerRevealY);
    };

    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, [pathname, isProductDetailPage, keepDesktopHeaderPinned]);

  const handleSuggestionClick = (term: string) => {
    const raw = term.trim();
    if (!raw) {
      router.push('/');
      return;
    }
    navigateProductTextSearch(router, raw, categoryTree);
  };

  // Danh mục: đọc từ URL khi ở trang chủ, để highlight đúng nút
  const selectedFilter =
    pathname === '/'
      ? {
          category: searchParams.get('category') ?? undefined,
          subcategory: searchParams.get('subcategory') ?? undefined,
          sub_subcategory: searchParams.get('sub_subcategory') ?? undefined,
        }
      : {};

  const handleCategoryChange = (
    category: string,
    subcategory?: string,
    sub_subcategory?: string
  ) => {
    const params = new URLSearchParams();
    if (category) params.set('category', category);
    if (subcategory) params.set('subcategory', subcategory);
    if (sub_subcategory) params.set('sub_subcategory', sub_subcategory);
    router.push('/?' + searchParamsToEncodedQueryString(params));
  };

  const showMobileBottomNav = !isProductDetailPage && !isShopVideoFeedPage;

  return (
    <div
      className="min-h-screen flex flex-col bg-gray-50"
      style={
        {
          '--listing-chrome-height': keepDesktopHeaderPinned ? `${listingChromeHeight}px` : '0px',
          /** Offset sticky bộ lọc: khi head mỏng trừ vài px để bù subpixel + viền mờ (backdrop), tránh khe. */
          '--listing-filter-sticky-top': !keepDesktopHeaderPinned
            ? '0px'
            : useListingThinOnScroll && pinnedListingCompact
              ? `max(0px, calc(${listingChromeHeight}px - 3px))`
              : `${listingChromeHeight}px`,
        } as CSSProperties
      }
    >
      {!isShopVideoFeedPage && (
      <div className="hidden md:block">
      {keepDesktopHeaderPinned ? (
        <>
          {/* fixed: sticky trong flex column hay gãy — luôn ghim hai thanh theo viewport */}
          <div
            ref={listingChromeRef}
            className={`fixed top-0 left-0 right-0 z-[60] bg-gray-50 ${
              useListingThinOnScroll && pinnedListingCompact ? 'shadow-none' : 'shadow-md'
            }`}
          >
            <div className={useListingThinOnScroll && pinnedListingCompact ? 'hidden' : ''}>
            <Header
              onSearch={handleSuggestionClick}
              cartItemsCount={getCartItemCount()}
              favoriteItemsCount={favoriteCount}
            />
            </div>
            <Navigation
              selectedFilter={selectedFilter}
              onCategoryChange={handleCategoryChange}
              initialCategoryTree={categoryTree}
              headerVisible={useListingThinOnScroll ? !pinnedListingCompact : true}
              embedInStickyChrome
              collapseListingCategoryBar={useListingThinOnScroll && pinnedListingCompact}
              disableStickyBar={Boolean(isProductDetailPage)}
              onDesktopThinChromeHeight={useListingThinOnScroll ? reportDesktopThinChromeHeight : undefined}
            />
          </div>
          <div
            className="shrink-0 w-full"
            style={{ height: listingChromeHeight }}
            aria-hidden
          />
        </>
      ) : (
        <>
          <div
            className={`sticky top-0 z-50 shrink-0 self-start w-full transition-transform duration-300 ease-out ${
              headerVisible ? 'translate-y-0' : '-translate-y-full'
            }`}
          >
            <Header
              onSearch={handleSuggestionClick}
              cartItemsCount={getCartItemCount()}
              favoriteItemsCount={favoriteCount}
            />
          </div>
          <div className="shrink-0 self-start w-full">
            <Navigation
              selectedFilter={selectedFilter}
              onCategoryChange={handleCategoryChange}
              initialCategoryTree={initialCategoryTree}
              headerVisible={headerVisible}
              embedInStickyChrome={false}
              disableStickyBar={Boolean(isProductDetailPage)}
            />
          </div>
        </>
      )}
      </div>
      )}
      {/* Mobile: header site — gồm /auth/* để đồng bộ với bottom nav */}
      {!isShopVideoFeedPage && (
        <MobileHeader
          cartItemsCount={getCartItemCount()}
          viewedProductsCount={viewedProductsCount}
          suggestions={suggestions}
          onSuggestionClick={handleSuggestionClick}
          initialCategoryTree={categoryTree}
        />
      )}

      <main
        className={`flex-1 md:pb-0 ${showMobileBottomNav ? 'pb-16' : ''} ${isShopVideoFeedPage ? 'bg-black' : ''}`}
      >
        {children}
      </main>

      {/* Footer: hiển thị cả mobile và desktop */}
      {!isShopVideoFeedPage && <Footer />}
      {!isShopVideoFeedPage && <BackToTopButton />}
      {/* Mobile: Bottom nav — hiển thị trên /auth/* để điều hướng giống các trang khác */}
      {showMobileBottomNav && <MobileBottomNav notificationCount={0} />}
      {!isAuthPage && !isShopVideoFeedPage && !pathname?.startsWith('/admin') && (
        <FloatingShopVideoFeedButton />
      )}
      <PwaInstallPrompt />
      <CartAddedPopup />
      {!isAuthPage && <BirthGenderSalePromptModal />}
      {!isAuthPage && !pathname?.startsWith('/admin') && <BirthdayPromoWelcomeModal />}
    </div>
  );
}
