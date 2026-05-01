'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState, ReactNode } from 'react';

const ADMIN_LINKS = [
  { href: '/admin/orders', label: 'Quản lý đơn hàng' },
  { href: '/admin/products', label: 'Quản lý sản phẩm' },
  { href: '/admin/product-questions', label: 'Câu hỏi Câu trả lời sản phẩm' },
  { href: '/admin/product-reviews', label: 'Đánh giá sản phẩm' },
  { href: '/admin/danh-muc-seo', label: 'Tổng hợp danh mục SEO' },
  { href: '/admin/taxonomy', label: 'Cây danh mục (taxonomy)' },
  { href: '/admin/search-mappings', label: 'Từ khóa mapping' },
  { href: '/admin/search-cache', label: 'Cache & thống kê tìm kiếm' },
  { href: '/admin/members', label: 'Quản lý thành viên' },
  { href: '/admin/loyalty', label: 'Cấu hình thành viên' },
  { href: '/admin/bank-accounts', label: 'Cấu hình nạp tiền' },
  { href: '/admin/chat-embeds', label: 'Nhúng chat: NanoAI, Zalo, Facebook' },
  { href: '/admin/embed-codes', label: 'Mã nhúng (GA, FB, TikTok…)' },
  { href: '/admin/notifications', label: 'Quản lý thông báo' },
];

export default function AdminLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [clearingCache, setClearingCache] = useState(false);
  const [cacheMessage, setCacheMessage] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const token = localStorage.getItem('admin_token');
    if (!token && pathname !== '/admin/login') {
      router.replace('/admin/login');
    }
  }, [pathname, router]);

  if (pathname === '/admin/login') {
    return <>{children}</>;
  }

  const handleLogout = () => {
    localStorage.removeItem('admin_token');
    router.push('/admin/login');
  };
  const handleClearCache = async () => {
    setClearingCache(true);
    setCacheMessage(null);
    try {
      const res = await fetch('/admin/clear-cache', { method: 'POST' });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.ok) {
        setCacheMessage('Đã xóa sạch cache.');
      } else {
        setCacheMessage(data?.message || 'Lỗi xóa cache.');
      }
    } catch {
      setCacheMessage('Lỗi kết nối.');
    } finally {
      setClearingCache(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 flex">
      <aside className="w-56 bg-slate-800 text-white flex flex-col">
        <div className="p-4 border-b border-slate-700">
          <Link href="/admin/orders" className="text-lg font-bold text-white">
            188 Admin
          </Link>
        </div>
        <nav className="flex-1 p-2">
          {ADMIN_LINKS.map(({ href, label }) => {
            const active = pathname === href || pathname.startsWith(`${href}/`);
            return (
            <Link
              key={href}
              href={href}
              className={`block px-3 py-2 rounded-lg mb-1 transition-colors ${
                active ? 'bg-slate-600 text-white' : 'text-slate-300 hover:bg-slate-700 hover:text-white'
              }`}
            >
              {label}
            </Link>
            );
          })}
        </nav>
        <div className="p-2 border-t border-slate-700">
          <button
            onClick={handleLogout}
            className="w-full text-left px-3 py-2 rounded-lg text-slate-300 hover:bg-slate-700 hover:text-white"
          >
            Đăng xuất
          </button>
        </div>
      </aside>
      <main className="flex-1 flex flex-col overflow-auto">
        <header className="shrink-0 flex justify-end items-center gap-2 pl-6 pr-10 py-2 bg-white border-b border-gray-200">
          <button
            type="button"
            onClick={handleClearCache}
            disabled={clearingCache}
            className="px-3 py-2 text-sm font-medium rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            title="Xóa cache danh mục/sản phẩm để thấy thay đổi ngay trên site"
          >
            {clearingCache ? 'Đang xóa...' : '🔄 Xóa sạch cache'}
          </button>
          {cacheMessage && (
            <span className="text-sm text-slate-600">{cacheMessage}</span>
          )}
        </header>
        <div className="flex-1 overflow-auto">
          {children}
        </div>
      </main>
    </div>
  );
}
