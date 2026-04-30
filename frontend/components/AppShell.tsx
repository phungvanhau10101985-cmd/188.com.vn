// components/AppShell.tsx - Header + Navigation + Footer xuyên suốt tất cả các trang
'use client';

import { useState, useEffect, useMemo, useRef, useLayoutEffect } from 'react';
import dynamic from 'next/dynamic';
import { usePathname, useSearchParams, useRouter } from 'next/navigation';
import Header from '@/components/Header';
import Footer from '@/components/Footer';
import Navigation from '@/components/Navigation';
import MobileHeader from '@/components/mobile/MobileHeader';
import MobileBottomNav from '@/components/mobile/MobileBottomNav';
import BackToTopButton from '@/components/BackToTopButton';

const CartAddedPopup = dynamic(() => import('@/components/CartAddedPopup'), { ssr: false });
const BirthGenderSalePromptModal = dynamic(
  () => import('@/components/BirthGenderSalePromptModal'),
  { ssr: false }
);
import { useAuth } from '@/features/auth/hooks/useAuth';
import { useCart } from '@/features/cart/hooks/useCart';
import { useFavorites } from '@/features/favorites/hooks/useFavorites';
import { apiClient } from '@/lib/api-client';
import { generateSlug } from '@/lib/utils';
import type { CategoryLevel1 } from '@/types/api';

interface AppShellProps {
  children: React.ReactNode;
  /** Cây danh mục từ server (layout) để thanh danh mục hiển thị ngay, không phụ thuộc fetch client */
  initialCategoryTree?: CategoryLevel1[];
}

export default function AppShell({ children, initialCategoryTree }: AppShellProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const { getCartItemCount } = useCart();
  const { favoriteCount } = useFavorites();
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [headerVisible, setHeaderVisible] = useState(true);

  const qFromUrl = searchParams.get('q') ?? '';
  const isAuthPage = pathname?.startsWith('/auth/');
  const isProductDetailPage = pathname?.match(/^\/products\/[^/]+$/);

  /** Trang chủ có query lọc/tìm, hoặc trang /info/* — cố định header + nav desktop khi cuộn */
  const keepDesktopHeaderPinned = useMemo(() => {
    if (pathname?.startsWith('/info')) return true;
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
    if (t('min_price')) return true;
    if (t('max_price')) return true;
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

  /** Chiều cao khối chrome cố định — spacer đẩy main, tránh nội dung chui dưới fixed bar */
  const listingChromeRef = useRef<HTMLDivElement>(null);
  const [listingChromeHeight, setListingChromeHeight] = useState(168);

  useLayoutEffect(() => {
    if (!keepDesktopHeaderPinned) return;
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
  }, [keepDesktopHeaderPinned]);

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
    const target = generateSlug(raw);
    const tree = initialCategoryTree || [];
    for (const c1 of tree) {
      const slug1 = generateSlug(c1.slug || c1.name);
      if (target === slug1) {
        router.push(`/danh-muc/${encodeURIComponent(slug1)}`);
        return;
      }
      for (const c2 of (c1.children || [])) {
        const slug2 = generateSlug(c2.slug || c2.name);
        if (target === slug2) {
          router.push(`/danh-muc/${encodeURIComponent(slug1)}/${encodeURIComponent(slug2)}`);
          return;
        }
        for (const c3 of (c2.children || [])) {
          const name3 = (c3 as any)?.name ?? String(c3);
          const slug3 = generateSlug((c3 as any)?.slug ?? name3);
          if (target === slug3) {
            router.push(`/danh-muc/${encodeURIComponent(slug1)}/${encodeURIComponent(slug2)}/${encodeURIComponent(slug3)}`);
            return;
          }
        }
      }
    }
    router.push(`/?q=${encodeURIComponent(raw)}`);
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
    router.push('/?' + params.toString());
  };

  const showMobileBottomNav = !isAuthPage && !isProductDetailPage;

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      {/* Desktop: Header + Navigation */}
      <div className="hidden md:block">
      {keepDesktopHeaderPinned ? (
        <>
          {/* fixed: sticky trong flex column hay gãy — luôn ghim hai thanh theo viewport */}
          <div
            ref={listingChromeRef}
            className="fixed top-0 left-0 right-0 z-[60] bg-gray-50 shadow-md"
          >
            <Header
              onSearch={handleSuggestionClick}
              cartItemsCount={getCartItemCount()}
              favoriteItemsCount={favoriteCount}
            />
            <Navigation
              selectedFilter={selectedFilter}
              onCategoryChange={handleCategoryChange}
              initialCategoryTree={initialCategoryTree}
              headerVisible={true}
              embedInStickyChrome
              disableStickyBar={Boolean(isProductDetailPage)}
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
      {/* Mobile: header site — ẩn trang /auth/* (đồng bộ bottom nav, form đăng nhập đỡ chật) */}
      {!isAuthPage && (
        <MobileHeader
          cartItemsCount={getCartItemCount()}
          favoriteItemsCount={favoriteCount}
          suggestions={suggestions}
          onSuggestionClick={handleSuggestionClick}
          initialCategoryTree={initialCategoryTree}
        />
      )}

      <main className={`flex-1 md:pb-0 ${showMobileBottomNav ? 'pb-16' : ''}`}>{children}</main>

      {/* Footer: hiển thị cả mobile và desktop */}
      <Footer />
      <BackToTopButton />
      <CartAddedPopup />
      {/* Mobile: Bottom nav - ẩn trên trang auth để dropdown chọn tháng không bị che, kéo được tháng 12 */}
      {showMobileBottomNav && <MobileBottomNav notificationCount={0} favoriteCount={favoriteCount} />}
      {!isAuthPage && <BirthGenderSalePromptModal />}
    </div>
  );
}
