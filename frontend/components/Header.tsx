// components/Header.tsx - ĐÃ TÍCH HỢP CART SYSTEM
'use client';

import { useState, useRef, useEffect } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { usePathname, useSearchParams } from 'next/navigation';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { useCart } from '@/features/cart/hooks/useCart';
import { apiClient } from '@/lib/api-client';
import DesktopImageSearchPopover from '@/components/DesktopImageSearchPopover';
import { useLoginRedirectHref } from '@/lib/use-login-redirect-href';

interface HeaderProps {
  onSearch?: (searchTerm: string) => void;
  cartItemsCount: number;
  favoriteItemsCount: number;
  initialSearchTerm?: string;
}

export default function Header({ onSearch = () => {}, cartItemsCount, favoriteItemsCount, initialSearchTerm }: HeaderProps) {
  const searchParams = useSearchParams();
  const qFromUrl = searchParams.get('q') ?? '';
  const [searchTerm, setSearchTerm] = useState(initialSearchTerm ?? qFromUrl);
  const [isSearchFocused, setIsSearchFocused] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [unreadNotifications, setUnreadNotifications] = useState(0);
  const accountRef = useRef<HTMLDivElement>(null);
  const pathname = usePathname();
  const loginHref = useLoginRedirectHref();
  const { user, isAuthenticated, logout } = useAuth();
  const isProductDetailPage = Boolean(pathname?.match(/^\/products\/[^/]+$/));

  useEffect(() => {
    if (isAuthenticated) {
      apiClient.getUnreadNotificationCount()
        .then(setUnreadNotifications)
        .catch(() => setUnreadNotifications(0));
      
      const interval = setInterval(() => {
        apiClient.getUnreadNotificationCount()
          .then(setUnreadNotifications)
          .catch(() => {});
      }, 60000);
      
      return () => clearInterval(interval);
    } else {
      setUnreadNotifications(0);
    }
  }, [isAuthenticated]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (accountRef.current && !accountRef.current.contains(e.target as Node)) setAccountOpen(false);
    }
    if (accountOpen) document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [accountOpen]);

  useEffect(() => {
    const q = initialSearchTerm ?? qFromUrl;
    setSearchTerm(q);
  }, [initialSearchTerm, qFromUrl]);

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
  const { getCartItemCount } = useCart();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    onSearch(searchTerm);
  };

  const handleSuggestionClick = (term: string) => {
    setSearchTerm(term);
    onSearch(term);
  };

  const handleLogout = () => {
    logout();
  };

  // Sử dụng cartItemsCount từ props hoặc từ cart hook
  const displayCartCount = cartItemsCount || getCartItemCount();

  const searchBar = (
    <>
      <form onSubmit={handleSearch} className="relative">
        <div className={`relative transition-all duration-200 ${isSearchFocused ? 'ring-2 ring-white/50 rounded-xl shadow-lg shadow-black/10' : 'rounded-xl shadow-sm'}`}>
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            onFocus={() => setIsSearchFocused(true)}
            onBlur={() => setIsSearchFocused(false)}
            placeholder="Tìm kiếm sản phẩm, thương hiệu..."
            className="w-full pl-4 pr-24 py-3 bg-white border-0 rounded-xl focus:outline-none text-gray-800 placeholder-gray-500 text-sm"
          />
          <DesktopImageSearchPopover />
          <button
            type="submit"
            className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-500 hover:text-[#ea580c]"
            aria-label="Tìm kiếm"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </button>
        </div>
      </form>
      {suggestions.length > 0 && (
        <div className="flex items-center gap-2 mt-0.5 overflow-hidden whitespace-nowrap">
          {suggestions.map((term) => (
            <button
              key={term}
              type="button"
              onClick={() => handleSuggestionClick(term)}
              className="text-xs text-orange-100 hover:text-white transition-colors px-1.5 py-0.5 flex-shrink-0"
            >
              {term}
            </button>
          ))}
        </div>
      )}
    </>
  );

  return (
    <header className="bg-[#ea580c] shadow-md border-b border-orange-700/20 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4">
        <div className="flex items-center justify-between h-20">
          {/* Logo */}
          <Link href="/" className="flex items-center h-full group">
            <Image
              src="https://188comvn.b-cdn.net/logo%20head%20188.png"
              alt="188.com.vn - XEM LÀ THÍCH"
              width={320}
              height={80}
              className="h-full max-h-20 w-auto object-contain transform group-hover:scale-[1.02] transition-transform duration-200"
            />
          </Link>

          {/* Search Bar */}
          <div className="flex-1 max-w-2xl mx-6 lg:mx-8">
            {searchBar}
          </div>

          {/* User Actions */}
          <div className="flex items-center space-x-4 md:space-x-6">
            {/* Sản phẩm đã xem — vòng tròn nhỏ, icon to hơn */}
            <Link href="/da-xem" className="flex flex-col items-center space-y-0.5 text-white/90 hover:text-white transition-colors group">
              <div className="w-8 h-8 bg-white/20 rounded-full flex items-center justify-center group-hover:bg-white/30 transition-colors">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
              </div>
              <span className="text-[11px] font-medium">Đã xem</span>
            </Link>

            {/* Notifications */}
            {isAuthenticated && (
              <Link href="/account/notifications" className="flex flex-col items-center space-y-0.5 text-white/90 hover:text-white transition-colors group relative">
                <div className="w-8 h-8 bg-white/20 rounded-full flex items-center justify-center group-hover:bg-white/30 transition-colors relative">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                  </svg>
                  {unreadNotifications > 0 && (
                    <span className="absolute -top-1 -right-1 bg-red-500 text-white rounded-full min-w-[16px] h-4 text-[10px] flex items-center justify-center font-bold leading-none px-1 border border-white">
                      {unreadNotifications > 99 ? '99+' : unreadNotifications}
                    </span>
                  )}
                </div>
                <span className="text-[11px] font-medium">Thông báo</span>
              </Link>
            )}

            {/* Account */}
            {isAuthenticated ? (
              <Link href="/account" className="flex flex-col items-center space-y-1 text-white/90 hover:text-white transition-colors group">
                <div className="w-10 h-10 bg-white/20 rounded-full flex items-center justify-center group-hover:bg-white/30 transition-colors">
                  <span className="text-white font-semibold text-sm">
                    {user?.full_name?.charAt(0) || 'U'}
                  </span>
                </div>
                <span className="text-xs font-medium">Tài khoản</span>
              </Link>
            ) : (
              <Link href={loginHref} className="flex flex-col items-center space-y-1 text-white/90 hover:text-white transition-colors group">
                <div className="w-10 h-10 bg-white/20 rounded-full flex items-center justify-center group-hover:bg-white/30 transition-colors">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                  </svg>
                </div>
                <span className="text-xs font-medium">Đăng nhập</span>
              </Link>
            )}

            {/* Favorites — vòng tròn nhỏ, icon to, số yêu thích nhỏ */}
            <Link href="/favorites" className="flex flex-col items-center space-y-0.5 text-white/90 hover:text-white transition-colors group relative">
              <div className="w-8 h-8 bg-white/20 rounded-full flex items-center justify-center group-hover:bg-white/30 transition-colors relative">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
                </svg>
                {favoriteItemsCount > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 bg-white text-[#ea580c] rounded-full min-w-[16px] h-4 text-[10px] flex items-center justify-center font-bold leading-none">
                    {favoriteItemsCount}
                  </span>
                )}
              </div>
              <span className="text-[11px] font-medium">Yêu thích</span>
            </Link>

            {/* Cart — vòng tròn nhỏ, icon to, số giỏ nhỏ */}
            <Link href="/cart" className="flex flex-col items-center space-y-0.5 text-white/90 hover:text-white transition-colors group relative">
              <div className="w-8 h-8 bg-white/20 rounded-full flex items-center justify-center group-hover:bg-white/30 transition-colors relative">
                <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
                </svg>
                {displayCartCount > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 bg-white text-[#ea580c] rounded-full min-w-[16px] h-4 text-[10px] flex items-center justify-center font-bold leading-none">
                    {displayCartCount}
                  </span>
                )}
              </div>
              <span className="text-[11px] font-medium">Giỏ hàng</span>
            </Link>
          </div>
        </div>
      </div>
    </header>
  );
}
