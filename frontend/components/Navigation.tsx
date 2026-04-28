// frontend/components/Navigation.tsx - Danh mục 3 cấp từ sản phẩm (AB, AC, AD)
'use client';

import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { apiClient } from '@/lib/api-client';
import { generateSlug } from '@/lib/utils';
import DesktopImageSearchPopover from '@/components/DesktopImageSearchPopover';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { useFavorites } from '@/features/favorites/hooks/useFavorites';
import { useCart } from '@/features/cart/hooks/useCart';
import type { CategoryLevel1, CategoryLevel2 } from '@/types/api';

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
}

function slugNorm(s: string | undefined): string {
  return (s || '').trim().toLowerCase();
}

export default function Navigation({
  selectedFilter,
  onCategoryChange,
  initialCategoryTree = [],
  headerVisible = true,
  disableStickyBar = false,
}: NavigationProps) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [tree, setTree] = useState<CategoryLevel1[]>(initialCategoryTree ?? []);
  const [loading, setLoading] = useState(initialCategoryTree?.length === 0);
  const [isScrolled, setIsScrolled] = useState(false);
  const [openLevel1, setOpenLevel1] = useState<string | null>(null);
  const [stickySearchTerm, setStickySearchTerm] = useState('');
  const [stickyMenuOpen, setStickyMenuOpen] = useState(false);
  const stickyMenuCloseTimerRef = useRef<number | null>(null);
  const { isAuthenticated, user } = useAuth();
  const { favoriteCount } = useFavorites();
  const { getCartItemCount } = useCart();
  const displayCartCount = getCartItemCount();
  const dropdownRef = useRef<HTMLDivElement>(null);

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

  const fetchTree = useCallback(async () => {
    const hadData = tree.length > 0;
    if (!hadData) setLoading(true);
    try {
      const data = await apiClient.getCategoryTreeFromProducts();
      setTree(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error('Error fetching category tree:', error);
      setTree([]);
    } finally {
      setLoading(false);
    }
  }, [tree.length]);

  useEffect(() => {
    fetchTree();
  }, [fetchTree]);

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
      if (dropdownRef.current && !dropdownRef.current.contains(target)) {
        setOpenLevel1(null);
        setStickyMenuOpen(false);
      }
    }
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, []);

  const handleStickySearch = (e: React.FormEvent) => {
    e.preventDefault();
    const raw = stickySearchTerm.trim();
    if (!raw) {
      router.push('/');
      return;
    }
    const target = generateSlug(raw);
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

  const basePill =
    'inline-flex items-center gap-1 px-2 py-1 rounded-full text-[11px] font-medium whitespace-nowrap transition-all duration-200 flex-shrink-0';
  const activePill = 'bg-white/20 text-white shadow-sm';
  const inactivePill = 'bg-white/20 text-white hover:bg-white/30 shadow-sm';

  const stickyTopClass = headerVisible ? 'top-20' : 'top-0';
  const stickyBarTopClass = 'top-0';
  const showStickyBar = isScrolled && !headerVisible && !disableStickyBar;

  if (loading) {
    return (
      <nav className={`bg-white/95 backdrop-blur border-b border-gray-100 sticky ${stickyTopClass} z-40 shadow-sm`}>
        <div className="max-w-7xl mx-auto px-3">
          <div className="flex gap-1.5 overflow-hidden py-1.5">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-7 w-20 rounded-full bg-gray-200 animate-pulse flex-shrink-0" />
            ))}
          </div>
        </div>
      </nav>
    );
  }

  const openCategory = tree.find((c) => c.name === openLevel1);
  const handleStickyMenuEnter = () => {
    if (stickyMenuCloseTimerRef.current) {
      window.clearTimeout(stickyMenuCloseTimerRef.current);
      stickyMenuCloseTimerRef.current = null;
    }
    setStickyMenuOpen(true);
    if (!openLevel1 && tree.length) setOpenLevel1(tree[0].name);
  };

  const handleStickyMenuLeave = () => {
    if (stickyMenuCloseTimerRef.current) window.clearTimeout(stickyMenuCloseTimerRef.current);
    stickyMenuCloseTimerRef.current = window.setTimeout(() => setStickyMenuOpen(false), 150);
  };

  return (
    <>
      <div
        className={`fixed ${stickyBarTopClass} left-0 right-0 z-50 bg-[#ea580c] border-b border-gray-100 transition-all duration-300 ease-out ${
          showStickyBar ? 'translate-y-0 opacity-100' : '-translate-y-full opacity-0 pointer-events-none'
        }`}
        aria-hidden={!showStickyBar}
      >
        <div className="max-w-7xl mx-auto px-3">
          <div className="grid grid-cols-[224px_1fr_224px] items-center gap-3 py-1.5">
            <div className="flex items-center gap-3">
              <div
                className="relative"
                onMouseEnter={handleStickyMenuEnter}
                onMouseLeave={handleStickyMenuLeave}
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
              {showStickyBar && stickyMenuOpen && openCategory && (
                <div
                  className="absolute left-0 top-full mt-1 w-[720px] bg-white border border-gray-200 shadow-lg rounded-xl overflow-hidden z-[60] py-2"
                  onMouseEnter={handleStickyMenuEnter}
                  onMouseLeave={handleStickyMenuLeave}
                >
                  <div className="grid grid-cols-[220px_1fr]">
                    <div className="bg-gray-50/80 border-r border-gray-100 p-3">
                      <div className="grid grid-cols-1 gap-1">
                        {tree.length === 0 && (
                          <div className="text-xs text-gray-500">Chưa có danh mục.</div>
                        )}
                        {tree.map((level1) => {
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
                                      const name3 = typeof level3 === 'object' && level3 !== null && 'name' in level3 ? (level3 as { name: string }).name : String(level3);
                                      const slug3 = typeof level3 === 'object' && level3 !== null && 'slug' in level3 ? (level3 as { slug?: string }).slug : name3;
                                      return (
                                        <Link
                                          key={name3}
                                          href={`/danh-muc/${encodeURIComponent(slug1)}/${encodeURIComponent(slug2)}/${encodeURIComponent(slug3 || name3)}`}
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
            </div>
            <form onSubmit={handleStickySearch} className="relative w-full max-w-md justify-self-center">
              <input
                type="text"
                value={stickySearchTerm}
                onChange={(e) => setStickySearchTerm(e.target.value)}
                placeholder="Tìm kiếm..."
                autoComplete="off"
                className="w-full pl-4 pr-24 py-2 text-xs rounded-lg border-0 bg-white focus:outline-none focus:ring-2 focus:ring-orange-200"
              />
              <DesktopImageSearchPopover panelZClass="z-[110]" />
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

                {isAuthenticated ? (
                  <Link href="/account" className="flex items-center text-white/90 hover:text-white transition-colors group">
                    <div className="w-7 h-7 bg-white/20 rounded-full flex items-center justify-center group-hover:bg-white/30 transition-colors">
                      <span className="text-white font-semibold text-sm">
                        {user?.full_name?.charAt(0) || 'U'}
                      </span>
                    </div>
                  </Link>
                ) : (
                  <Link href="/auth/login" className="flex items-center text-white/90 hover:text-white transition-colors group">
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
                      <span className="absolute -top-0.5 -right-0.5 bg-white text-[#ea580c] rounded-full min-w-[16px] h-4 text-[10px] flex items-center justify-center font-bold leading-none">
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
                      <span className="absolute -top-0.5 -right-0.5 bg-white text-[#ea580c] rounded-full min-w-[16px] h-4 text-[10px] flex items-center justify-center font-bold leading-none">
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
      <nav
        ref={dropdownRef}
        className={`sticky ${stickyTopClass} z-40 transition-all duration-300 ${
          isScrolled ? 'bg-[#ea580c]/95 backdrop-blur-md shadow-md border-b border-orange-600' : 'bg-[#ea580c] border-b border-orange-600 shadow-sm'
        }`}
      >
        {showStickyBar && <div className="h-[44px]" />}
        <div className="max-w-7xl mx-auto px-3">
        {!showStickyBar && (
          <div className="flex items-center gap-1.5 py-1.5 overflow-x-auto overflow-y-visible scroll-smooth hide-scrollbar">
            <span className="hidden sm:inline-flex text-[11px] font-semibold text-white/80 uppercase tracking-wider mr-1 flex-shrink-0">
              Danh mục
            </span>
            {tree.map((level1) => {
              const slug1 = level1.slug || level1.name;
              const isL1Active = effectiveFilter.category === level1.name;
              const isOpen = openLevel1 === level1.name;
              const hasChildren = level1.children && level1.children.length > 0;

              return (
                <div
                  key={level1.name}
                  className="relative flex-shrink-0 inline-flex"
                  onMouseEnter={hasChildren ? () => setOpenLevel1(level1.name) : undefined}
                >
                  <div
                    className={`${basePill} ${isL1Active ? activePill : inactivePill} pr-0 gap-0`}
                  >
                    <Link
                      href={`/danh-muc/${encodeURIComponent(slug1)}`}
                      className={`flex-1 min-w-0 text-left px-2 py-1 -my-1 max-w-[6.5rem] truncate ${hasChildren ? 'rounded-l-full' : 'rounded-full'}`}
                      onClick={() => setOpenLevel1(null)}
                    >
                      {level1.name}
                    </Link>
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
        )}


        {/* Panel danh mục cấp 2 & 3 - hiển thị dưới thanh, không bị overflow cắt */}
        {openCategory && openCategory.children && openCategory.children.length > 0 && (
          <div
            className="border-t border-gray-100 bg-gray-50/80 py-2.5"
            onMouseLeave={() => setOpenLevel1(null)}
          >
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-1.5">
              {openCategory.children.map((level2: CategoryLevel2) => {
                const slug2 = level2.slug || level2.name;
                const slug1 = openCategory.slug || openCategory.name;
                const isL2Active =
                  effectiveFilter.subcategory === level2.name &&
                  effectiveFilter.category === openCategory.name;
                const hasL3 = level2.children && level2.children.length > 0;

                return (
                  <div key={level2.name} className="rounded-md bg-white border border-gray-100 shadow-sm overflow-hidden">
                    <Link
                      href={`/danh-muc/${encodeURIComponent(slug1)}/${encodeURIComponent(slug2)}`}
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
                    </Link>
                    {hasL3 && (
                      <div className="px-3 pb-2 pt-0 flex flex-wrap gap-1">
                        {level2.children!.map((level3) => {
                          const name3 = typeof level3 === 'object' && level3 !== null && 'name' in level3 ? (level3 as { name: string }).name : String(level3);
                          const slug3 = typeof level3 === 'object' && level3 !== null && 'slug' in level3 ? (level3 as { slug?: string }).slug : name3;
                          const isL3Active =
                            effectiveFilter.sub_subcategory === name3 &&
                            effectiveFilter.subcategory === level2.name &&
                            effectiveFilter.category === openCategory.name;
                          return (
                            <Link
                              key={name3}
                              href={`/danh-muc/${encodeURIComponent(slug1)}/${encodeURIComponent(slug2)}/${encodeURIComponent(slug3 || name3)}`}
                              onClick={() => setOpenLevel1(null)}
                              className={`inline-block text-[11px] px-2 py-1 rounded ${
                                isL3Active
                                  ? 'bg-orange-100 text-orange-700 font-medium'
                                  : 'text-gray-600 hover:bg-gray-100 hover:text-[#ea580c]'
                              }`}
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
          </div>
        )}
        </div>
      </nav>
    </>
  );
}
