'use client';

import { useState, useEffect } from 'react';
import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { format } from 'date-fns';
import { vi } from 'date-fns/locale';
import Link from 'next/link';
import { useLoginRedirectHref } from '@/lib/use-login-redirect-href';

export default function MyNotificationsPage() {
  const loginHref = useLoginRedirectHref();
  const { user, isAuthenticated } = useAuth();
  const [notifications, setNotifications] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (isAuthenticated) {
      fetchNotifications();
    }
  }, [isAuthenticated]);

  const fetchNotifications = async () => {
    try {
      const data = await apiClient.getMyNotifications();
      setNotifications(data);
    } catch (error) {
      console.error('Failed to fetch notifications', error);
    } finally {
      setLoading(false);
    }
  };

  const handleMarkAsRead = async (id: number) => {
    try {
      await apiClient.markNotificationAsRead(id);
      setNotifications(prev => prev.map(n => n.id === id ? { ...n, is_read: true } : n));
    } catch (error) {
      console.error('Failed to mark as read', error);
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await apiClient.markAllNotificationsAsRead();
      setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
    } catch (error) {
      console.error('Failed to mark all as read', error);
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="container mx-auto px-4 py-12 text-center">
        <p className="mb-4">Vui lòng đăng nhập để xem thông báo.</p>
        <Link href={loginHref} className="text-blue-600 hover:underline">Đăng nhập ngay</Link>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-3xl">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Thông báo của tôi</h1>
        {notifications.some(n => !n.is_read) && (
          <button 
            onClick={handleMarkAllRead}
            className="text-sm text-blue-600 hover:text-blue-800 font-medium"
          >
            Đánh dấu tất cả đã đọc
          </button>
        )}
      </div>

      {loading ? (
        <div className="text-center py-8 text-gray-500">Đang tải thông báo...</div>
      ) : notifications.length === 0 ? (
        <div className="text-center py-12 bg-gray-50 rounded-lg border border-gray-100">
          <svg className="w-12 h-12 text-gray-300 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
          </svg>
          <p className="text-gray-500">Bạn chưa có thông báo nào.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {notifications.map((notif) => (
            <div 
              key={notif.id} 
              className={`p-4 rounded-xl border transition-all cursor-pointer hover:shadow-sm ${
                notif.is_read 
                  ? 'bg-white border-gray-100' 
                  : 'bg-blue-50/50 border-blue-100 shadow-sm'
              }`}
              onClick={() => !notif.is_read && handleMarkAsRead(notif.id)}
            >
              <div className="flex justify-between items-start gap-3 mb-1.5">
                <div className="flex items-center gap-2">
                  {!notif.is_read && (
                    <span className="w-2 h-2 rounded-full bg-blue-600 flex-shrink-0"></span>
                  )}
                  <h3 className={`font-semibold text-base ${notif.is_read ? 'text-gray-800' : 'text-blue-800'}`}>
                    {notif.title}
                  </h3>
                </div>
                <span className="text-xs text-gray-400 whitespace-nowrap flex-shrink-0">
                  {format(new Date(notif.created_at), 'dd/MM HH:mm', { locale: vi })}
                </span>
              </div>
              <p className={`text-sm whitespace-pre-line pl-4 ${notif.is_read ? 'text-gray-600' : 'text-gray-800'}`}>
                {notif.content}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
