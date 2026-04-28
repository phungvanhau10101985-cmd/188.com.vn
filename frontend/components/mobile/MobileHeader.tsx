'use client';

import { useState, useEffect, useRef, useId } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import type { CategoryLevel1, CategoryLevel2, CategoryLevel3 } from '@/types/api';
import { storePendingImageAndNavigate } from '@/lib/nanoai-pending-image';
import { useAuth } from '@/features/auth/hooks/useAuth';

const SCROLL_THRESHOLD = 50;

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

  useEffect(() => {
    if (isHome) {
      const q = searchParams.get('q') ?? '';
      setSearchTerm(q);
    }
  }, [isHome, searchParams]);

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > SCROLL_THRESHOLD);
    };
    handleScroll();
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
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

  const iconBtn =
    'flex-shrink-0 w-8 h-8 min-[390px]:w-9 min-[390px]:h-9 flex items-center justify-center text-white rounded-full bg-white/15 hover:bg-white/25 active:bg-white/30';

  return (
    <div className="md:hidden sticky top-0 z-50" ref={panelRef}>
      <header className="bg-[#ea580c] shadow-md border-b border-orange-700/20">
        <div className="px-3 pt-1.5 pb-1">
          <div
            className={`flex justify-center overflow-hidden transition-all duration-200 ${
              isScrolled ? 'max-h-0 opacity-0 mt-0 mb-0' : 'max-h-16 opacity-100 mb-0'
            }`}
          >
            <Link href="/" className="block">
              <Image
                src="https://188comvn.b-cdn.net/logo%20head%20188.png"
                alt="188.com.vn"
                width={220}
                height={44}
                className="h-11 w-auto object-contain block"
              />
            </Link>
          </div>

          {/* Danh mục + ô tìm kiếm mobile + icon nhanh */}
          <div className={`flex items-center gap-1 relative z-10 transition-all duration-200 ${isScrolled ? 'mt-0' : '-mt-1'}`}>
            {!isHome && (
              <button
                type="button"
                onClick={() => router.back()}
                className={iconBtn}
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
              className={`flex-shrink-0 flex items-center justify-center w-8 h-8 min-[390px]:w-9 min-[390px]:h-9 text-white rounded-lg transition-colors ${
                categoryPanelOpen ? 'bg-white/30' : 'bg-white/15 hover:bg-white/25'
              }`}
              aria-label="Danh mục"
              aria-expanded={categoryPanelOpen}
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>

            <form onSubmit={handleSearch} className="flex-1 min-w-0 relative">
              {/* sr-only thay vì hidden: iOS/Safari thường chặn .click() vào input display:none */}
              <input
                id={mobileImageInputId}
                type="file"
                accept="image/jpeg,image/png,image/webp,image/gif"
                className="sr-only"
                tabIndex={-1}
                onChange={onImagePick}
              />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Tìm kiếm…"
                autoComplete="off"
                className="w-full pl-3 pr-[4.25rem] py-2.5 bg-white border-0 rounded-lg text-gray-900 placeholder-gray-400 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-white/70"
              />
              <label
                htmlFor={mobileImageInputId}
                className="absolute right-9 top-1/2 -translate-y-1/2 w-8 h-8 flex items-center justify-center rounded-md text-gray-500 hover:text-[#ea580c] hover:bg-orange-50 active:bg-orange-100 cursor-pointer"
                aria-label="Tìm bằng ảnh"
                title="Tìm theo ảnh (NanoAI)"
              >
                <svg className="w-4 h-4 pointer-events-none" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </label>
              <button
                type="submit"
                className="absolute right-1 top-1/2 -translate-y-1/2 w-8 h-8 rounded-md bg-[#ea580c] text-white flex items-center justify-center hover:bg-orange-600 shadow-sm"
                aria-label="Tìm trên 188"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </button>
            </form>

            <Link href="/da-xem" className={iconBtn} aria-label="Đã xem" title="Đã xem">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              </svg>
            </Link>

            {isAuthenticated && (
              <Link href="/account/notifications" className={`${iconBtn} relative`} aria-label="Thông báo" title="Thông báo">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                </svg>
              </Link>
            )}

            <Link href="/cart" className={`${iconBtn} relative`} aria-label="Giỏ hàng" title="Giỏ hàng">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
              </svg>
              {cartItemsCount > 0 && (
                <span className="absolute -top-0.5 -right-0.5 bg-white text-[#ea580c] rounded-full min-w-[14px] h-3.5 text-[9px] flex items-center justify-center font-bold px-0.5 leading-none">
                  {cartItemsCount > 99 ? '99+' : cartItemsCount}
                </span>
              )}
            </Link>
          </div>

          {/* Gợi ý từ khóa */}
          <div className="flex items-center gap-1.5 mt-1.5 overflow-hidden min-h-[28px]">
            <div className="flex-1 min-w-0 overflow-hidden flex items-center gap-1 py-0.5 whitespace-nowrap flex-nowrap">
              {suggestions.slice(0, 8).map((term) => (
                <button
                  key={term}
                  type="button"
                  onClick={() => onSuggestionClick(term)}
                  className="flex-shrink-0 text-xs text-orange-100 hover:text-white px-2 py-0.5 rounded-full bg-white/10 hover:bg-white/20 whitespace-nowrap"
                >
                  {term}
                </button>
              ))}
            </div>
          </div>
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
