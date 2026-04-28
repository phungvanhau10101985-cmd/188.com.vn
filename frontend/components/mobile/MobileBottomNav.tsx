'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState, useEffect } from 'react';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { apiClient } from '@/lib/api-client';

interface MobileBottomNavProps {
  notificationCount?: number;
  favoriteCount?: number;
}

const navItems = [
  { href: '/', label: 'Trang chủ', icon: 'home' },
  { href: '/info/lien-he', label: 'Liên hệ', icon: 'contact' },
  { href: '/account/notifications', label: 'Thông báo', icon: 'bell', badgeKey: 'notification' },
  { href: '/favorites', label: 'Yêu thích', icon: 'heart', badgeKey: 'favorite' },
  { href: '/account', label: 'Cá nhân', icon: 'profile' },
];

export default function MobileBottomNav({ notificationCount: initialNotifCount = 0, favoriteCount = 0 }: MobileBottomNavProps) {
  const pathname = usePathname();
  const { isAuthenticated } = useAuth();
  const [unreadNotifCount, setUnreadNotifCount] = useState(initialNotifCount);

  useEffect(() => {
    if (isAuthenticated) {
      // Fetch immediately
      apiClient.getUnreadNotificationCount()
        .then(setUnreadNotifCount)
        .catch(() => setUnreadNotifCount(0));
        
      // Poll every minute
      const interval = setInterval(() => {
        apiClient.getUnreadNotificationCount()
          .then(setUnreadNotifCount)
          .catch(() => {});
      }, 60000);
      
      return () => clearInterval(interval);
    } else {
      setUnreadNotifCount(0);
    }
  }, [isAuthenticated]);

  const getBadgeCount = (item: (typeof navItems)[number]) => {
    if (item.badgeKey === 'notification') return unreadNotifCount;
    if (item.badgeKey === 'favorite') return favoriteCount;
    return 0;
  };

  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-white border-t border-gray-200 safe-area-pb shadow-[0_-2px_10px_rgba(0,0,0,0.05)]">
      <div className="flex items-center justify-around h-[60px] px-1">
        {navItems.map((item) => {
          const isActive = item.href === '/' ? pathname === '/' : pathname?.startsWith(item.href);
          const badgeCount = item.badgeKey ? getBadgeCount(item) : 0;
          const showBadge = badgeCount > 0;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex flex-col items-center justify-center flex-1 h-full min-w-0 gap-1 transition-colors ${
                isActive ? 'text-[#ea580c]' : 'text-gray-500 hover:text-gray-900'
              }`}
            >
              <span className="relative inline-flex items-center justify-center">
                {item.icon === 'home' && (
                  <svg className="w-6 h-6" fill={isActive ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
                  </svg>
                )}
                {item.icon === 'contact' && (
                  <svg className="w-6 h-6" fill={isActive ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                )}
                {item.icon === 'bell' && (
                  <>
                    <svg className="w-6 h-6" fill={isActive ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                    </svg>
                    {showBadge && (
                      <span className="absolute -top-1 -right-1 min-w-[16px] h-4 flex items-center justify-center bg-red-500 text-white text-[10px] font-bold rounded-full px-0.5 border-2 border-white">
                        {badgeCount > 99 ? '99+' : badgeCount}
                      </span>
                    )}
                  </>
                )}
                {item.icon === 'heart' && (
                  <>
                    <svg className="w-6 h-6" fill={isActive ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
                    </svg>
                    {showBadge && (
                      <span className="absolute -top-1 -right-1 min-w-[16px] h-4 flex items-center justify-center bg-red-500 text-white text-[10px] font-bold rounded-full px-0.5 border-2 border-white">
                        {badgeCount > 99 ? '99+' : badgeCount}
                      </span>
                    )}
                  </>
                )}
                {item.icon === 'profile' && (
                  <svg className="w-6 h-6" fill={isActive ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                  </svg>
                )}
              </span>
              <span className="text-[10px] font-medium truncate w-full text-center leading-none">{item.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
