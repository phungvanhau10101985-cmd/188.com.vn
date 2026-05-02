'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { useFavorites } from '@/features/favorites/hooks/useFavorites';
import { apiClient } from '@/lib/api-client';
import { useToast } from '@/components/ToastProvider';
import { trackEvent } from '@/lib/analytics';
import {
  openNanoAiTryOnEmbed,
  NANO_AI_TRY_ON_HOME_CTX,
  NANO_AI_CTX_SOURCE_SHOP_HOME,
} from '@/lib/nanoai-hosted-chat';

interface MobileBottomNavProps {
  notificationCount?: number;
}

function pathNorm(p: string | null): string {
  if (p == null) return '';
  return p.replace(/\/$/, '') || '/';
}

/** Đồng bộ với trang chủ: cam khi active / nhấn mạnh, xám khi không chọn. */
const NAV_ACTIVE = 'text-[#ea580c]';
const NAV_INACTIVE = 'text-gray-600 hover:text-gray-900';

type NavIcon = 'home' | 'bell' | 'heart' | 'profile';

const linkNavItems: Array<{
  href: string;
  label: string;
  icon: NavIcon;
  badgeKey?: 'notification' | 'favorite';
}> = [
  { href: '/', label: 'Trang chủ', icon: 'home' },
  { href: '/account/notifications', label: 'Thông báo', icon: 'bell', badgeKey: 'notification' },
  { href: '/favorites', label: 'Yêu thích', icon: 'heart', badgeKey: 'favorite' },
  { href: '/account', label: 'Cá nhân', icon: 'profile' },
];

export default function MobileBottomNav({ notificationCount: initialNotifCount = 0 }: MobileBottomNavProps) {
  const pathname = usePathname();
  const pathKey = pathNorm(pathname);
  const { pushToast } = useToast();
  const { isAuthenticated } = useAuth();
  const { favoriteCount } = useFavorites();
  const [unreadNotifCount, setUnreadNotifCount] = useState(initialNotifCount);

  const handleBottomNavTryOn = useCallback(async () => {
    const result = await openNanoAiTryOnEmbed(NANO_AI_TRY_ON_HOME_CTX, NANO_AI_CTX_SOURCE_SHOP_HOME);
    if (!result.ok) {
      if (result.reason === 'no_chat_config') {
        pushToast({
          title: 'Chưa mở được thử đồ',
          description:
            'Kiểm tra mã nhúng NanoAI (data-chat-url trên script) hoặc biến NEXT_PUBLIC_NANOAI_CHAT_URL trong frontend.',
          variant: 'info',
          durationMs: 4200,
        });
      } else {
        pushToast({
          title: 'Chưa mở được khung chat',
          description: 'Bấm biểu tượng chat NanoAI góc màn hình — có thể mở thử đồ từ đó.',
          variant: 'info',
          durationMs: 4200,
        });
      }
      return;
    }
    trackEvent('nanoai_try_on_open', { source: 'mobile_bottom_nav_try_on', mode: result.mode });
  }, [pushToast]);

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

  const getBadgeCount = (item: (typeof linkNavItems)[number]) => {
    if (item.badgeKey === 'notification') return unreadNotifCount;
    if (item.badgeKey === 'favorite') return favoriteCount;
    return 0;
  };

  const renderLinkItem = (item: (typeof linkNavItems)[number]) => {
    const isActive =
      item.href === '/'
        ? pathKey === '/'
        : pathKey === pathNorm(item.href) || pathKey.startsWith(`${pathNorm(item.href)}/`);
    const badgeCount = item.badgeKey ? getBadgeCount(item) : 0;
    const showBadge = badgeCount > 0;

    const className = `flex flex-col items-center justify-center flex-1 h-full min-w-0 gap-1 transition-colors ${
      isActive ? NAV_ACTIVE : NAV_INACTIVE
    }`;

    return (
      <Link key={item.href} href={item.href} className={className}>
        <span className="relative inline-flex items-center justify-center">
          {item.icon === 'home' && (
            <svg className="w-6 h-6" fill={isActive ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
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
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"
                />
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
  };

  const [homeItem, ...restLinks] = linkNavItems;

  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-white border-t border-gray-200 safe-area-pb shadow-[0_-2px_10px_rgba(0,0,0,0.05)]">
      <div className="flex items-center justify-around h-[60px] px-1">
        {renderLinkItem(homeItem)}
        <button
          type="button"
          onClick={() => void handleBottomNavTryOn()}
          className={`flex flex-col items-center justify-center flex-1 h-full min-w-0 gap-1 transition-colors ${NAV_ACTIVE} active:opacity-80`}
          aria-label="Thử đồ với NanoAI"
        >
          <span className="relative inline-flex items-center justify-center">
            <svg className="w-6 h-6 shrink-0" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24" aria-hidden>
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"
              />
            </svg>
          </span>
          <span className="text-[10px] font-medium truncate w-full text-center leading-none">Thử đồ</span>
        </button>
        {restLinks.map(renderLinkItem)}
      </div>
    </nav>
  );
}
