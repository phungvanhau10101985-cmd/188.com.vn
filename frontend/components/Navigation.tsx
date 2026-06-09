// frontend/components/Navigation.tsx - Danh mục 3 cấp từ sản phẩm (AB, AC, AD)
'use client';

import { useState, useEffect, useLayoutEffect, useRef, useMemo, useCallback } from 'react';
import Link from 'next/link';
import LoadingLink from '@/components/ui/LoadingLink';
import Image from 'next/image';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { apiClient } from '@/lib/api-client';
import { navigateProductTextSearch } from '@/lib/navigate-product-text-search';
import LazyDesktopImageSearchPopover from '@/components/LazyDesktopImageSearchPopover';
import SearchHistoryPanel from '@/components/search/SearchHistoryPanel';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { useFavorites } from '@/features/favorites/hooks/useFavorites';
import { useCart } from '@/features/cart/hooks/useCart';
import type { CategoryLevel1, CategoryLevel2 } from '@/types/api';
import { categorySegmentForUrl } from '@/lib/category-url';
import {
  isKhoSaleMenuCategory,
  KHO_SALE_HREF,
  KHO_SALE_MENU_NAME,
  level1CategoryHref,
} from '@/lib/kho-sale-menu-category';
import { useLoginRedirectHref } from '@/lib/use-login-redirect-href';
import { useClientMounted } from '@/lib/use-client-mounted';
import {
  isNavCategoryTreeCacheStale,
  readNavCategoryTreeCache,
  writeNavCategoryTreeCache,
} from '@/lib/nav-category-tree-cache';

export interface CategoryFilter {
  category?: string;
  subcategory?: string;
  sub_subcategory?: string;
}

interface NavigationProps {
  selectedFilter: CategoryFilter;
  onCategoryChange: (category: string, subcategory?: string, sub_subcategory?: string) => void;
  /** Cây danh mục từ server (layout) — hiển thị ngay, không phụ thuộc fetch client/CORS */
  initialCategoryTree?: CategoryLevel1[];
  /** Header có đang hiển thị không (để canh top/ẩn sticky bar) */
  headerVisible?: boolean;
  /** Tắt thanh sticky (VD: trang chi tiết sản phẩm) */
  disableStickyBar?: boolean;
  /** Đặt trong khối sticky chung với Header (AppShell) — bỏ sticky riêng của nav để head + danh mục luôn dính cùng nhau */
  embedInStickyChrome?: boolean;
  /** Trang listing desktop: khi cuộn, ẩn hàng pill — chỉ giữ thanh cam mỏng (đồng bộ AppShell). */
  collapseListingCategoryBar?: boolean;
  /** Gửi chiều cao thanh cam mỏng (fixed) → AppShell đặt `--listing-chrome-height` khớp, tránh khe với bộ lọc. */
  onDesktopThinChromeHeight?: (heightPx: number) => void;
}

function slugNorm(s: string | undefined): string {
  return (s || '').trim().toLowerCase();
}

/** Key React cho link cấp 3: trùng tên cấp 3 khác cấp 2 hoặc trùng trong cùng cột không bị gộp nhầm. */
function level3ReactKey(slug2: string | undefined, slug3: string | undefined, name3: string): string {
  return `${slugNorm(slug2)}::${slugNorm(slug3 ?? name3)}`;
}

/** Key React cho cột cấp 2 (tránh trùng tên hiển thị giữa các nhánh). */
function level2ReactKey(slug1: string | undefined, slug2: string | undefined, name2: string): string {
  return `${slugNorm(slug1)}::${slugNorm(slug2 ?? name2)}`;
}

function triggerDropdownPos(el: HTMLDivElement | null): { top: number; left: number } | null {
  if (!el || typeof window === 'undefined') return null;
  const r = el.getBoundingClientRect();
  return { top: r.bottom, left: r.left };
}

export default function Navigation({
  selectedFilter,
  onCategoryChange,
  initialCategoryTree = [],
  headerVisible = true,
  disableStickyBar = false,
  embedInStickyChrome = false,
  collapseListingCategoryBar = false,
  onDesktopThinChromeHeight,
}: NavigationProps) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [tree, setTree] = useState<CategoryLevel1[]>(() => {
    if ((initialCategoryTree?.length ?? 0) > 0) return initialCategoryTree ?? [];
    return readNavCategoryTreeCache();
  });
  const [loading, setLoading] = useState(
    () => (initialCategoryTree?.length ?? 0) === 0 && readNavCategoryTreeCache().length === 0,
  );
  const [isScrolled, setIsScrolled] = useState(false);
  const [openLevel1, setOpenLevel1] = useState<string | null>(null);
  const [stickySearchTerm, setStickySearchTerm] = useState('');
  const [stickySearchHistoryOpen, setStickySearchHistoryOpen] = useState(false);
  const [stickyMenuOpen, setStickyMenuOpen] = useState(false);
  const [catalogMenuOpen, setCatalogMenuOpen] = useState(false);
  const clientMounted = useClientMounted();
  const stickyMenuCloseTimerRef = useRef<number | null>(null);
  const catalogMenuCloseTimerRef = useRef<number | null>(null);
  const { isAuthenticated, isLoading, user } = useAuth();
  const authReady = clientMounted && !isLoading;
  const showAuthenticatedActions = authReady && isAuthenticated;
  const loginHref = useLoginRedirectHref();
  const { favoriteCount } = useFavorites();
  const { getCartItemCount } = useCart();
  const displayCartCount = getCartItemCount();
  const dropdownRef = useRef<HTMLElement | null>(null);
  const stickySearchRef = useRef<HTMLFormElement | null>(null);
  const thinBarOuterRef = useRef<HTMLDivElement | null>(null);
  const prefetchedCategoryHrefsRef = useRef<Set<string>>(new Set());
  /** Căn mega-menu theo đúng pill cấp 1 — container và từng pill (không ép full-width trái). */
  const categoryBarWrapRef = useRef<HTMLDivElement>(null);
  const pillsScrollRef = useRef<HTMLDivElement>(null);
  const catalogTriggerWrapRef = useRef<HTMLDivElement>(null);
  const stickyCatalogTriggerWrapRef = useRef<HTMLDivElement>(null);
  const catalogDropdownRef = useRef<HTMLDivElement>(null);
  const stickyCatalogDropdownRef = useRef<HTMLDivElement>(null);
  const level1WrapRefs = useRef<Map<string, HTMLDivElement | null>>(new Map());
  const [megaPlacement, setMegaPlacement] = useState<{ left: number; width: number } | null>(null);
  const [catalogDropdownPos, setCatalogDropdownPos] = useState<{ top: number; left: number } | null>(null);
  const [stickyCatalogDropdownPos, setStickyCatalogDropdownPos] = useState<{ top: number; left: number } | null>(
    null,
  );

  // Khi đang ở /danh-muc/... thì highlight theo slug (resolve từ tree)
  const effectiveFilter = useMemo(() => {
    if (!pathname?.startsWith('/danh-muc/') || !tree.length) return selectedFilter;
    const parts = pathname.replace(/^\/danh-muc\/?/, '').split('/').filter(Boolean);
    if (parts.length === 0) return selectedFilter;
    const [s1, s2, s3] = parts;
    for (const c1 of tree) {
      if (slugNorm(c1.slug || c1.name) !== slugNorm(s1)) continue;
      if (!s2) return { category: c1.name };
      for (const c2 of c1.children || []) {
        if (slugNorm(c2.slug || c2.name) !== slugNorm(s2)) continue;
        if (!s3) return { category: c1.name, subcategory: c2.name };
        for (const c3 of c2.children || []) {
          const n3 = typeof c3 === 'object' && c3 !== null && 'name' in c3 ? (c3 as { name: string }).name : String(c3);
          const sl3 = typeof c3 === 'object' && c3 !== null && 'slug' in c3 ? (c3 as { slug?: string }).slug : n3;
          if (slugNorm(sl3) === slugNorm(s3)) return { category: c1.name, subcategory: c2.name, sub_subcategory: n3 };
        }
        return { category: c1.name, subcategory: c2.name };
      }
      return { category: c1.name };
    }
    return selectedFilter;
  }, [pathname, tree, selectedFilter]);

  useEffect(() => {
    const next = initialCategoryTree ?? [];
    if (next.length > 0) {
      setTree(next);
      setLoading(false);
      writeNavCategoryTreeCache(next);
    }
  }, [initialCategoryTree]);

  useEffect(() => {
    let cancelled = false;

    const applyTree = (next: CategoryLevel1[]) => {
      if (cancelled || next.length === 0) return;
      setTree(next);
      setLoading(false);
      writeNavCategoryTreeCache(next);
    };

    const cached = readNavCategoryTreeCache();
    if ((initialCategoryTree?.length ?? 0) === 0 && cached.length > 0) {
      setTree((prev) => (prev.length > 0 ? prev : cached));
      setLoading(false);
    }

    const needsFetch = (initialCategoryTree?.length ?? 0) === 0 && cached.length === 0;
    const needsBackgroundRefresh =
      (initialCategoryTree?.length ?? 0) === 0 &&
      cached.length > 0 &&
      isNavCategoryTreeCacheStale();

    if (!needsFetch && !needsBackgroundRefresh) return;

    if (needsFetch) setLoading(true);

    (async () => {
      try {
        const data = await apiClient.getCategoryTreeFromProducts();
        if (cancelled) return;
        const next = Array.isArray(data) ? data : [];
        if (next.length > 0) applyTree(next);
        else if (needsFetch && !cancelled) setTree([]);
      } catch (error) {
        console.error('Error fetching category tree:', error);
        if (!cancelled && needsFetch && cached.length === 0) setTree([]);
      } finally {
        if (!cancelled && needsFetch) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [initialCategoryTree]);

  useEffect(() => {
    if (pathname === '/') {
      setStickySearchTerm(searchParams.get('q') ?? '');
    }
  }, [pathname, searchParams]);

  useEffect(() => {
    const getScrollY = () => {
      if (typeof window === 'undefined') return 0;
      const scrollingElement = document.scrollingElement || document.documentElement;
      return window.scrollY || scrollingElement.scrollTop || document.body.scrollTop || 0;
    };

    const handleScroll = () => {
      const y = getScrollY();
      setIsScrolled((prev) => (prev ? y > 0 : y > 20));
    };

    handleScroll();
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, [pathname]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      const target = e.target as Node;
      const inNav = dropdownRef.current?.contains(target);
      const inThinBar = thinBarOuterRef.current?.contains(target);
      const inCatalogDrop = catalogDropdownRef.current?.contains(target);
      const inStickyCatalogDrop = stickyCatalogDropdownRef.current?.contains(target);
      if (inNav || inThinBar || inCatalogDrop || inStickyCatalogDrop) return;
      setOpenLevel1(null);
      setStickyMenuOpen(false);
      setCatalogMenuOpen(false);
    }
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, []);

  const updateCatalogDropdownPos = useCallback(() => {
    if (typeof window === 'undefined') return;
    if (catalogMenuOpen && catalogTriggerWrapRef.current) {
      const r = catalogTriggerWrapRef.current.getBoundingClientRect();
      setCatalogDropdownPos({ top: r.bottom, left: r.left });
    } else {
      setCatalogDropdownPos(null);
    }
    if (stickyMenuOpen && stickyCatalogTriggerWrapRef.current) {
      const r = stickyCatalogTriggerWrapRef.current.getBoundingClientRect();
      setStickyCatalogDropdownPos({ top: r.bottom, left: r.left });
    } else {
      setStickyCatalogDropdownPos(null);
    }
  }, [catalogMenuOpen, stickyMenuOpen]);

  useLayoutEffect(() => {
    updateCatalogDropdownPos();
  }, [updateCatalogDropdownPos]);

  useEffect(() => {
    if (!catalogMenuOpen && !stickyMenuOpen) return;
    const onSync = () => updateCatalogDropdownPos();
    window.addEventListener('resize', onSync);
    window.addEventListener('scroll', onSync, { passive: true });
    pillsScrollRef.current?.addEventListener('scroll', onSync, { passive: true });
    return () => {
      window.removeEventListener('resize', onSync);
      window.removeEventListener('scroll', onSync);
      pillsScrollRef.current?.removeEventListener('scroll', onSync);
    };
  }, [catalogMenuOpen, stickyMenuOpen, updateCatalogDropdownPos]);

  const updateMegaPlacement = useCallback(() => {
    if (!openLevel1 || catalogMenuOpen || typeof window === 'undefined') {
      setMegaPlacement(null);
      return;
    }
    const wrap = categoryBarWrapRef.current;
    const pill = level1WrapRefs.current.get(openLevel1);
    if (!wrap || !pill) {
      setMegaPlacement(null);
      return;
    }
    const wr = wrap.getBoundingClientRect();
    const pr = pill.getBoundingClientRect();
    const gutter = 8;
    const innerW = wr.width;
    const maxPanel = 720;
    const desiredW = Math.min(maxPanel, Math.max(280, innerW - gutter * 2));
    let left = pr.left - wr.left;
    left = Math.max(gutter, Math.min(left, innerW - desiredW - gutter));
    setMegaPlacement({ left, width: desiredW });
  }, [openLevel1, catalogMenuOpen]);

  useLayoutEffect(() => {
    updateMegaPlacement();
  }, [updateMegaPlacement, tree]);

  useEffect(() => {
    if (!openLevel1) return;
    const el = pillsScrollRef.current;
    const onSync = () => updateMegaPlacement();
    el?.addEventListener('scroll', onSync, { passive: true });
    window.addEventListener('resize', onSync);
    window.addEventListener('scroll', onSync, { passive: true });
    return () => {
      el?.removeEventListener('scroll', onSync);
      window.removeEventListener('resize', onSync);
      window.removeEventListener('scroll', onSync);
    };
  }, [openLevel1, updateMegaPlacement]);

  const handleStickySearch = (e: React.FormEvent) => {
    e.preventDefault();
    setStickySearchHistoryOpen(false);
    const raw = stickySearchTerm.trim();
    if (!raw) {
      router.push('/');
      return;
    }
    navigateProductTextSearch(router, raw, tree);
  };

  const handleStickyHistorySelect = (query: string) => {
    setStickySearchTerm(query);
    setStickySearchHistoryOpen(false);
    navigateProductTextSearch(router, query, tree);
  };

  const prefetchCategoryHref = useCallback(
    (href: string) => {
      if (!href.startsWith('/danh-muc/')) return;
      const seen = prefetchedCategoryHrefsRef.current;
      if (seen.has(href)) return;
      seen.add(href);
      router.prefetch(href);
    },
    [router],
  );

  const basePill =
    'inline-flex items-center gap-1 px-2 py-1 rounded-full text-[11px] font-medium whitespace-nowrap transition-all duration-200 flex-shrink-0';
  const activePill = 'bg-white/20 text-white shadow-sm';
  const inactivePill = 'bg-white/20 text-white hover:bg-white/30 shadow-sm';

  /**
   * Trang listing ghim trong AppShell (embed): ô cam mỏng bật đúng theo `collapseListingCategoryBar`
   * (khớp pinnedListingCompact). Dùng thêm listener `isScrolled` ở đây dễ lệch pha/ngưỡng → nhấp nháy khi đổi head.
   */
  const showStickyBar = disableStickyBar
    ? false
    : embedInStickyChrome && collapseListingCategoryBar
      ? true
      : isScrolled && !headerVisible;
  const navLayoutClass = embedInStickyChrome
    ? 'relative'
    : showStickyBar
      ? 'relative'
      : headerVisible
        ? 'sticky top-20'
        : 'sticky top-0';
  const stickyBarTopClass = 'top-0';

  const hideListingCategoryPills = clientMounted && embedInStickyChrome && collapseListingCategoryBar;

  useLayoutEffect(() => {
    if (!embedInStickyChrome || !onDesktopThinChromeHeight || !showStickyBar) return;
    const el = thinBarOuterRef.current;
    if (!el) return;
    const report = () => {
      const r = el.getBoundingClientRect();
      const fromBox = Math.ceil(r.bottom - r.top);
      const h = Math.max(el.offsetHeight, fromBox);
      if (h > 0) onDesktopThinChromeHeight(h);
    };
    report();
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(report);
    ro.observe(el);
    return () => ro.disconnect();
  }, [embedInStickyChrome, onDesktopThinChromeHeight, showStickyBar]);

  const isKhoSaleActive = pathname === KHO_SALE_HREF || pathname?.startsWith(`${KHO_SALE_HREF}/`);
  const openCategory = tree.find((c) => c.name === openLevel1);

  const openCatalogMenu = useCallback(() => {
    if (catalogMenuCloseTimerRef.current) {
      window.clearTimeout(catalogMenuCloseTimerRef.current);
      catalogMenuCloseTimerRef.current = null;
    }
    const pos = triggerDropdownPos(catalogTriggerWrapRef.current);
    if (pos) setCatalogDropdownPos(pos);
    setCatalogMenuOpen(true);
    setOpenLevel1((prev) => prev ?? (tree.length ? tree[0].name : null));
  }, [tree]);

  const handleCatalogMenuEnter = openCatalogMenu;

  const handleCatalogMenuLeave = () => {
    if (catalogMenuCloseTimerRef.current) window.clearTimeout(catalogMenuCloseTimerRef.current);
    catalogMenuCloseTimerRef.current = window.setTimeout(() => setCatalogMenuOpen(false), 150);
  };

  const openStickyCatalogMenu = useCallback(() => {
    if (stickyMenuCloseTimerRef.current) {
      window.clearTimeout(stickyMenuCloseTimerRef.current);
      stickyMenuCloseTimerRef.current = null;
    }
    const pos = triggerDropdownPos(stickyCatalogTriggerWrapRef.current);
    if (pos) setStickyCatalogDropdownPos(pos);
    setStickyMenuOpen(true);
    setOpenLevel1((prev) => prev ?? (tree.length ? tree[0].name : null));
  }, [tree]);

  const handleStickyMenuEnter = openStickyCatalogMenu;

  const handleStickyMenuLeave = () => {
    if (stickyMenuCloseTimerRef.current) window.clearTimeout(stickyMenuCloseTimerRef.current);
    stickyMenuCloseTimerRef.current = window.setTimeout(() => setStickyMenuOpen(false), 150);
  };

  const renderCatalogDropdownPanel = (
    pos: { top: number; left: number },
    panelRef: React.Ref<HTMLDivElement>,
    onEnter: () => void,
    onLeave: () => void,
  ) => (
    <div
      ref={panelRef}
      className="fixed w-[min(720px,calc(100vw-1.5rem))] bg-white border border-gray-200 shadow-xl rounded-xl overflow-hidden z-[85] py-2"
      style={{ top: pos.top, left: pos.left }}
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
    >
      {loading && tree.length === 0 ? (
        <div className="grid grid-cols-[220px_1fr] animate-pulse">
          <div className="space-y-2 border-r border-gray-100 bg-gray-50/80 p-3">
            {[...Array(8)].map((_, i) => (
              <div key={i} className="h-8 rounded-md bg-gray-200" />
            ))}
          </div>
          <div className="space-y-3 p-3">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-4 rounded bg-gray-200" />
            ))}
          </div>
        </div>
      ) : (
      <div className="grid grid-cols-[220px_1fr]">
        <div className="bg-gray-50/80 border-r border-gray-100 p-3 max-h-[min(70vh,420px)] overflow-y-auto">
          <div className="grid grid-cols-1 gap-1">
            {tree.length === 0 && !loading && (
              <div className="text-xs text-gray-500">Chưa có danh mục.</div>
            )}
            {tree.map((level1) => {
              const isActive = openLevel1 === level1.name;
              const l1Active = isActive || (isKhoSaleMenuCategory(level1) && isKhoSaleActive);
              const href = level1CategoryHref(level1);
              return (
                <LoadingLink
                  key={level1.name}
                  href={href}
                  onMouseEnter={() => {
                    setOpenLevel1(level1.name);
                    prefetchCategoryHref(href);
                  }}
                  onFocus={() => prefetchCategoryHref(href)}
                  className={`px-2.5 py-2 rounded-md text-xs font-medium truncate ${
                    l1Active ? 'bg-orange-50 text-orange-700' : 'text-gray-700 hover:bg-white'
                  }`}
                >
                  {level1.name}
                </LoadingLink>
              );
            })}
          </div>
        </div>
        <div className="p-3 max-h-[min(70vh,420px)] overflow-y-auto">
          {!openCategory && (
            <div className="text-xs text-gray-500">Di chuột vào danh mục để xem cấp 2, cấp 3.</div>
          )}
          {openCategory && isKhoSaleMenuCategory(openCategory) && (
            <div className="text-xs text-gray-600 leading-relaxed">
              <p className="font-semibold text-gray-800 mb-1">{KHO_SALE_MENU_NAME}</p>
              <p>Hàng hoàn và tồn thanh lý — giá ưu đãi, số lượng có hạn.</p>
              <LoadingLink href={KHO_SALE_HREF} className="inline-block mt-2 text-[#ea580c] font-medium hover:underline">
                Xem tất cả →
              </LoadingLink>
            </div>
          )}
          {openCategory && !isKhoSaleMenuCategory(openCategory) && openCategory.children.length > 0 && (
            <div className="grid grid-cols-2 gap-3">
              {openCategory.children.map((level2) => {
                const slug1 = categorySegmentForUrl(openCategory.slug) || categorySegmentForUrl(openCategory.name);
                const slug2 = categorySegmentForUrl(level2.slug) || categorySegmentForUrl(level2.name);
                return (
                  <div key={level2ReactKey(slug1, slug2, level2.name)} className="min-w-0">
                    <LoadingLink
                      href={`/danh-muc/${encodeURIComponent(slug1)}/${encodeURIComponent(slug2)}`}
                      onMouseEnter={(e) => prefetchCategoryHref(e.currentTarget.pathname)}
                      onFocus={(e) => prefetchCategoryHref(e.currentTarget.pathname)}
                      className="block text-xs font-semibold text-gray-800 hover:text-[#ea580c]"
                    >
                      {level2.name}
                    </LoadingLink>
                    {level2.children && level2.children.length > 0 && (
                      <div className="mt-1 flex flex-col gap-1">
                        {level2.children.map((level3) => {
                          const name3 =
                            typeof level3 === 'object' && level3 !== null && 'name' in level3
                              ? (level3 as { name: string }).name
                              : String(level3);
                          const slug3 =
                            (typeof level3 === 'object' && level3 !== null && 'slug' in level3
                              ? categorySegmentForUrl((level3 as { slug?: string }).slug)
                              : '') || categorySegmentForUrl(name3);
                          return (
                            <LoadingLink
                              key={level3ReactKey(slug2, slug3 || undefined, name3)}
                              href={`/danh-muc/${encodeURIComponent(slug1)}/${encodeURIComponent(slug2)}/${encodeURIComponent(slug3)}`}
                              onMouseEnter={(e) => prefetchCategoryHref(e.currentTarget.pathname)}
                              onFocus={(e) => prefetchCategoryHref(e.currentTarget.pathname)}
                              className="text-[11px] text-gray-600 hover:text-[#ea580c] truncate"
                            >
                              {name3}
                            </LoadingLink>
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
      )}
    </div>
  );

  return (
    <>
      <div
        ref={(el) => {
          thinBarOuterRef.current = el;
          if (hideListingCategoryPills) {
            (dropdownRef as React.MutableRefObject<HTMLElement | null>).current = el;
          }
        }}
        className={`fixed ${stickyBarTopClass} left-0 right-0 z-[62] bg-[#ea580c] transition-all duration-300 ease-out ${
          hideListingCategoryPills ? 'border-b-0' : 'border-b border-gray-100'
        } ${
          showStickyBar ? 'translate-y-0 opacity-100' : '-translate-y-full opacity-0 pointer-events-none'
        }`}
        aria-hidden={!showStickyBar}
        inert={!showStickyBar ? true : undefined}
      >
        <div className="max-w-7xl mx-auto px-3">
          <div className="grid grid-cols-[auto_1fr_224px] items-center gap-3 py-1.5">
            <div className="flex min-w-0 items-center gap-2">
              <Link
                href="/"
                className="flex shrink-0 items-center rounded-md py-0.5 hover:bg-white/10 transition-colors"
                aria-label="Về trang chủ 188.com.vn"
              >
                <Image
                  src="https://188comvn.b-cdn.net/logo%20head%20188.png"
                  data-allow-png
                  alt="188.com.vn"
                  width={140}
                  height={35}
                  className="h-7 w-auto max-w-[7rem] sm:max-w-[8.5rem] object-contain object-left"
                />
              </Link>
              <div
                ref={stickyCatalogTriggerWrapRef}
                className="relative"
                onMouseEnter={handleStickyMenuEnter}
                onMouseLeave={handleStickyMenuLeave}
              >
              <button
                type="button"
                className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-[11px] font-medium bg-white/20 text-white hover:bg-white/30 shadow-sm whitespace-nowrap"
                aria-expanded={stickyMenuOpen}
                aria-haspopup="true"
                onClick={openStickyCatalogMenu}
              >
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
                Danh mục
              </button>
              </div>
            </div>
            <form
              ref={stickySearchRef}
              onSubmit={handleStickySearch}
              className="relative z-[105] w-full max-w-md justify-self-center"
            >
              <input
                type="text"
                value={stickySearchTerm}
                onChange={(e) => setStickySearchTerm(e.target.value)}
                onFocus={() => setStickySearchHistoryOpen(true)}
                placeholder="Tìm kiếm..."
                autoComplete="off"
                aria-expanded={stickySearchHistoryOpen}
                aria-haspopup="listbox"
                className="w-full pl-4 pr-24 py-2 text-xs rounded-lg border-0 bg-white focus:outline-none focus:ring-2 focus:ring-orange-200"
              />
              <SearchHistoryPanel
                open={stickySearchHistoryOpen}
                onClose={() => setStickySearchHistoryOpen(false)}
                onSelect={handleStickyHistorySelect}
                zClass="z-[115]"
                ignoreRefs={[stickySearchRef]}
              />
              <LazyDesktopImageSearchPopover panelZClass="z-[110]" />
              <button
                type="submit"
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-[#ea580c]"
                aria-label="Tìm kiếm"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </button>
            </form>
            <div className="justify-self-end">
              <div className="flex items-center gap-6 px-3 h-[32px]">
                <Link href="/da-xem" className="flex items-center text-white/90 hover:text-white transition-colors group">
                  <div className="w-7 h-7 bg-white/20 rounded-full flex items-center justify-center group-hover:bg-white/30 transition-colors">
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  </div>
                </Link>

                {showAuthenticatedActions ? (
                  <Link href="/account" className="flex items-center text-white/90 hover:text-white transition-colors group">
                    <div className="w-7 h-7 bg-white/20 rounded-full flex items-center justify-center group-hover:bg-white/30 transition-colors">
                      <span className="text-white font-semibold text-sm">
                        {user?.full_name?.charAt(0) || 'U'}
                      </span>
                    </div>
                  </Link>
                ) : (
                  <Link href={loginHref} className="flex items-center text-white/90 hover:text-white transition-colors group">
                    <div className="w-7 h-7 bg-white/20 rounded-full flex items-center justify-center group-hover:bg-white/30 transition-colors">
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                      </svg>
                    </div>
                  </Link>
                )}

                <Link href="/favorites" className="flex items-center text-white/90 hover:text-white transition-colors group relative">
                  <div className="w-7 h-7 bg-white/20 rounded-full flex items-center justify-center group-hover:bg-white/30 transition-colors relative">
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
                  <div className="w-7 h-7 bg-white/20 rounded-full flex items-center justify-center group-hover:bg-white/30 transition-colors relative">
                    <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
      {!hideListingCategoryPills && (
      <nav
        ref={dropdownRef}
        className={`${navLayoutClass} ${catalogMenuOpen || openLevel1 ? 'z-[68]' : 'z-40'} transition-all duration-300 ${
          isScrolled ? 'bg-[#ea580c]/95 backdrop-blur-md shadow-md border-b border-orange-600' : 'bg-[#ea580c] border-b border-orange-600 shadow-sm'
        }`}
      >
        <div ref={categoryBarWrapRef} className="relative max-w-7xl mx-auto px-3">
          <div
            ref={pillsScrollRef}
            className="flex items-center gap-1.5 py-1.5 overflow-x-auto overflow-y-visible scroll-smooth hide-scrollbar"
          >
            <div
              ref={catalogTriggerWrapRef}
              className="relative flex-shrink-0"
              onMouseEnter={handleCatalogMenuEnter}
              onMouseLeave={handleCatalogMenuLeave}
            >
              <button
                type="button"
                className={`${basePill} ${
                  catalogMenuOpen ? 'bg-white text-[#ea580c] shadow-sm' : 'bg-white/25 text-white hover:bg-white/35 shadow-sm'
                }`}
                aria-expanded={catalogMenuOpen}
                aria-haspopup="true"
                onClick={openCatalogMenu}
              >
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
                <span>Danh mục</span>
              </button>
            </div>
            {loading && tree.length === 0
              ? [...Array(5)].map((_, i) => (
                  <div key={`cat-skel-${i}`} className={`${basePill} bg-white/15 animate-pulse w-20`} aria-hidden />
                ))
              : null}
            {tree.map((level1) => {
              const slug1 =
                categorySegmentForUrl(level1.slug) || categorySegmentForUrl(level1.name);
              const href = level1CategoryHref(level1);
              const isL1Active =
                effectiveFilter.category === level1.name ||
                (isKhoSaleMenuCategory(level1) && isKhoSaleActive);
              const isOpen = openLevel1 === level1.name;
              const hasChildren = level1.children && level1.children.length > 0;

              return (
                <div
                  key={level1.name}
                  ref={(el) => {
                    const m = level1WrapRefs.current;
                    if (el) m.set(level1.name, el);
                    else m.delete(level1.name);
                  }}
                  className="relative flex-shrink-0 inline-flex"
                  onMouseEnter={hasChildren ? () => setOpenLevel1(level1.name) : undefined}
                >
                  <div
                    className={`${basePill} ${isL1Active ? activePill : inactivePill} pr-0 gap-0`}
                  >
                    <LoadingLink
                      href={href}
                      className={`flex-1 min-w-0 text-left px-2 py-1 -my-1 max-w-[6.5rem] truncate ${hasChildren ? 'rounded-l-full' : 'rounded-full'}`}
                      onMouseEnter={() => prefetchCategoryHref(href)}
                      onFocus={() => prefetchCategoryHref(href)}
                      onClick={() => setOpenLevel1(null)}
                    >
                      {level1.name}
                    </LoadingLink>
                    {hasChildren ? (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setOpenLevel1(isOpen ? null : level1.name);
                        }}
                        className="p-1 rounded-r-full hover:bg-black/10 hover:bg-white/20 transition-colors flex-shrink-0"
                        aria-label={isOpen ? 'Đóng danh mục con' : 'Mở danh mục con'}
                      >
                        <svg
                          className={`w-3 h-3 transition-transform ${isOpen ? 'rotate-180' : ''}`}
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                      </button>
                    ) : null}
                  </div>
                </div>
              );
            })}

            <Link
              href="/deals"
              className={`${basePill} bg-white/20 text-white hover:bg-white/30 shadow-sm transition-all`}
            >
              <span aria-hidden className="text-[10px]">🔥</span>
              <span>Deal sốc</span>
            </Link>
            <Link
              href="/new"
              className={`${basePill} bg-white/20 text-white hover:bg-white/30 shadow-sm transition-all`}
            >
              <span aria-hidden className="text-[10px]">🆕</span>
              <span>Hàng mới</span>
            </Link>
          </div>


        {/* Panel danh mục cấp 2 & 3 - hiển thị dưới thanh, không bị overflow cắt */}
        {openCategory && megaPlacement && !catalogMenuOpen && openCategory.children && openCategory.children.length > 0 && (
          <div
            className="absolute z-[100] -mt-1.5 pt-1.5 border-t border-gray-100 bg-gray-50/90 py-2.5 shadow-lg rounded-b-xl"
            style={{
              left: megaPlacement.left,
              top: '100%',
              width: megaPlacement.width,
            }}
            onMouseLeave={() => setOpenLevel1(null)}
          >
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-1.5">
              {openCategory.children.map((level2: CategoryLevel2) => {
                const slug2 =
                  categorySegmentForUrl(level2.slug) || categorySegmentForUrl(level2.name);
                const slug1 =
                  categorySegmentForUrl(openCategory.slug) || categorySegmentForUrl(openCategory.name);
                const isL2Active =
                  effectiveFilter.subcategory === level2.name &&
                  effectiveFilter.category === openCategory.name;
                const hasL3 = level2.children && level2.children.length > 0;

                return (
                  <div
                    key={level2ReactKey(slug1, slug2, level2.name)}
                    className="rounded-md bg-white border border-gray-100 shadow-sm overflow-hidden"
                  >
                    <LoadingLink
                      href={`/danh-muc/${encodeURIComponent(slug1)}/${encodeURIComponent(slug2)}`}
                      onMouseEnter={(e) => prefetchCategoryHref(e.currentTarget.pathname)}
                      onFocus={(e) => prefetchCategoryHref(e.currentTarget.pathname)}
                      onClick={() => setOpenLevel1(null)}
                      className={`block w-full text-left px-3 py-2 text-xs font-medium flex items-center justify-between gap-1.5 ${
                        isL2Active ? 'bg-orange-50 text-orange-700' : 'text-gray-700 hover:bg-gray-50 hover:text-[#ea580c]'
                      }`}
                    >
                      <span className="truncate">{level2.name}</span>
                      {hasL3 && (
                        <svg className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                      )}
                    </LoadingLink>
                    {hasL3 && (
                      <div className="px-3 pb-2 pt-0 flex flex-wrap gap-1">
                        {level2.children!.map((level3) => {
                          const name3 = typeof level3 === 'object' && level3 !== null && 'name' in level3 ? (level3 as { name: string }).name : String(level3);
                          const slug3 =
                            (typeof level3 === 'object' && level3 !== null && 'slug' in level3
                              ? categorySegmentForUrl((level3 as { slug?: string }).slug)
                              : '') || categorySegmentForUrl(name3);
                          const isL3Active =
                            effectiveFilter.sub_subcategory === name3 &&
                            effectiveFilter.subcategory === level2.name &&
                            effectiveFilter.category === openCategory.name;
                          return (
                            <LoadingLink
                              key={level3ReactKey(slug2, slug3 || undefined, name3)}
                              href={`/danh-muc/${encodeURIComponent(slug1)}/${encodeURIComponent(slug2)}/${encodeURIComponent(slug3)}`}
                              onMouseEnter={(e) => prefetchCategoryHref(e.currentTarget.pathname)}
                              onFocus={(e) => prefetchCategoryHref(e.currentTarget.pathname)}
                              onClick={() => setOpenLevel1(null)}
                              className={`inline-block text-[11px] px-2 py-1 rounded ${
                                isL3Active
                                  ? 'bg-orange-100 text-orange-700 font-medium'
                                  : 'text-gray-600 hover:bg-gray-100 hover:text-[#ea580c]'
                              }`}
                            >
                              {name3}
                            </LoadingLink>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
        </div>
      </nav>
      )}
      {catalogMenuOpen
        ? renderCatalogDropdownPanel(
            catalogDropdownPos ??
              triggerDropdownPos(catalogTriggerWrapRef.current) ?? { top: 0, left: 0 },
            catalogDropdownRef,
            handleCatalogMenuEnter,
            handleCatalogMenuLeave,
          )
        : null}
      {showStickyBar && stickyMenuOpen
        ? renderCatalogDropdownPanel(
            stickyCatalogDropdownPos ??
              triggerDropdownPos(stickyCatalogTriggerWrapRef.current) ?? { top: 0, left: 0 },
            stickyCatalogDropdownRef,
            handleStickyMenuEnter,
            handleStickyMenuLeave,
          )
        : null}
    </>
  );
}
