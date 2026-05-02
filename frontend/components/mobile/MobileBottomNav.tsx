'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState, useEffect, useMemo } from 'react';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { apiClient } from '@/lib/api-client';
import { SHOP_VIDEO_FEED_PATH, shopVideoFeedHrefFromPathname } from '@/lib/shop-video-feed';

interface MobileBottomNavProps {
  notificationCount?: number;
}

function pathNorm(p: string | null): string {
  if (p == null) return '';
  return p.replace(/\/$/, '') || '/';
}

const navItems = [
  { href: '/', label: 'Trang chủ', icon: 'home' as const },
  /** Hành vi xem lại SP trong phiên — trang được dùng nhiều trên TMĐT */
  { href: '/da-xem', label: 'Đã xem', icon: 'recent' as const },
  { href: '/account/notifications', label: 'Thông báo', icon: 'bell' as const, badgeKey: 'notification' as const },
  {
    href: SHOP_VIDEO_FEED_PATH,
    label: 'Lướt xem',
    labelBottom: 'video',
    icon: 'video' as const,
  },
  { href: '/account', label: 'Cá nhân', icon: 'profile' as const },
];

export default function MobileBottomNav({ notificationCount: initialNotifCount = 0 }: MobileBottomNavProps) {
  const pathname = usePathname();
  const pathKey = pathNorm(pathname);
  const shopVideoFeedHref = useMemo(() => shopVideoFeedHrefFromPathname(pathname), [pathname]);
  const { isAuthenticated } = useAuth();
  const [unreadNotifCount, setUnreadNotifCount] = useState(initialNotifCount);

  useEffect(() => {
    if (isAuthenticated) {
      apiClient
        .getUnreadNotificationCount()
        .then(setUnreadNotifCount)
        .catch(() => setUnreadNotifCount(0));

      const interval = setInterval(() => {
        apiClient.getUnreadNotificationCount().then(setUnreadNotifCount).catch(() => {});
      }, 60000);

      return () => clearInterval(interval);
    }
    setUnreadNotifCount(0);
    return undefined;
  }, [isAuthenticated]);

  useEffect(() => {
    const onRefresh = () => {
      if (!isAuthenticated) return;
      apiClient.getUnreadNotificationCount().then(setUnreadNotifCount).catch(() => {});
    };
    window.addEventListener('188-notifications-refresh', onRefresh);
    return () => window.removeEventListener('188-notifications-refresh', onRefresh);
  }, [isAuthenticated]);

  const getBadgeCount = (item: (typeof navItems)[number]) => {
    if (item.badgeKey === 'notification') return unreadNotifCount;
    return 0;
  };

  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-white border-t border-gray-200 safe-area-pb shadow-[0_-2px_10px_rgba(0,0,0,0.05)]">
      <div className="flex items-center justify-around h-[60px] px-1">
        {navItems.map((item) => {
          const resolvedHref = item.icon === 'video' ? shopVideoFeedHref : item.href;
          const isActive =
            item.href === '/'
              ? pathKey === '/'
              : item.icon === 'video'
                ? pathKey === SHOP_VIDEO_FEED_PATH
                : pathKey === pathNorm(item.href) || pathKey.startsWith(`${pathNorm(item.href)}/`);
          const badgeCount = item.badgeKey ? getBadgeCount(item) : 0;
          const showBadge = badgeCount > 0;

          const className = `flex flex-col items-center justify-center flex-1 h-full min-w-0 gap-1 transition-colors ${
            isActive ? 'text-[#ea580c]' : 'text-gray-500 hover:text-gray-900'
          }`;

          return (
            <Link key={item.href} href={resolvedHref} className={className}>
              <span className="relative inline-flex items-center justify-center">
                {item.icon === 'home' && (
                  <svg className="w-6 h-6" fill={isActive ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
                  </svg>
                )}
                {item.icon === 'recent' && (
                  <svg className="w-6 h-6" fill={isActive ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
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
                {item.icon === 'video' && (
                  <svg className="w-6 h-6" fill={isActive ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={1.5}
                      d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.348a1.125 1.125 0 010 1.971l-11.54 6.347a1.125 1.125 0 01-1.667-.985V5.653z"
                    />
                  </svg>
                )}
                {item.icon === 'profile' && (
                  <svg className="w-6 h-6" fill={isActive ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                  </svg>
                )}
              </span>
              {'labelBottom' in item && item.labelBottom ? (
                <span className="text-[9px] font-medium w-full text-center leading-tight">
                  <span className="block">{item.label}</span>
                  <span className="block">{item.labelBottom}</span>
                </span>
              ) : (
                <span className="text-[10px] font-medium truncate w-full text-center leading-none">{item.label}</span>
              )}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
