'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useMemo, useState, ReactNode } from 'react';
import {
  defaultAdminHomeFromState,
  getStoredAdminRole,
  getStoredAdminModules,
  getEffectiveNavPrefixesFor,
  isAdminPathAllowedForState,
  isPrivilegedAdminRole,
} from '@/lib/admin-role';
import { ADMIN_NAV_GROUPS, type AdminNavGroup } from '@/lib/admin-nav-config';

export default function AdminLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [clearingCache, setClearingCache] = useState(false);
  const [cacheMessage, setCacheMessage] = useState<string | null>(null);
  const [adminRole, setAdminRole] = useState<string | null>(() =>
    typeof window !== 'undefined' ? getStoredAdminRole() : null,
  );
  const [adminModules, setAdminModules] = useState<string[] | null>(() =>
    typeof window !== 'undefined' ? getStoredAdminModules() : null,
  );

  useEffect(() => {
    if (typeof window === 'undefined') return;
    setAdminRole(getStoredAdminRole());
    setAdminModules(getStoredAdminModules());
  }, [pathname]);

  useEffect(() => {
    setSidebarOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!sidebarOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [sidebarOpen]);

  const visibleGroups = useMemo(() => {
    const filterItem = (l: AdminNavGroup['items'][number]) => {
      if (l.privilegedOnly && !isPrivilegedAdminRole(adminRole)) return false;
      const prefixes = getEffectiveNavPrefixesFor(adminRole, adminModules);
      if (!prefixes) return true;
      return prefixes.some((p) => l.href === p || l.href.startsWith(`${p}/`));
    };

    return ADMIN_NAV_GROUPS.map((g) => ({
      ...g,
      items: g.items.filter(filterItem),
    })).filter((g) => g.items.length > 0);
  }, [adminRole, adminModules]);

  const adminHomeHref = useMemo(
    () => defaultAdminHomeFromState((adminRole || '').trim() || null, adminModules),
    [adminRole, adminModules],
  );

  const showClearCacheButton = adminRole === null || isPrivilegedAdminRole(adminRole);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const token = localStorage.getItem('admin_token');
    if (!token && pathname !== '/admin/login') {
      router.replace('/admin/login');
    }
  }, [pathname, router]);

  useEffect(() => {
    if (pathname === '/admin/login') return;
    const role = getStoredAdminRole();
    const mods = getStoredAdminModules();
    if (!isAdminPathAllowedForState(pathname, role, mods)) {
      const prefixes = getEffectiveNavPrefixesFor(role, mods);
      const fallback = prefixes && prefixes.length > 0 ? prefixes[0] : '/admin/orders';
      router.replace(fallback);
    }
  }, [pathname, router]);

  const handleLogout = () => {
    localStorage.removeItem('admin_token');
    localStorage.removeItem('admin_role');
    localStorage.removeItem('admin_modules');
    router.push('/admin/login');
  };

  const handleClearCache = async () => {
    setClearingCache(true);
    setCacheMessage(null);
    try {
      const res = await fetch('/admin/clear-cache', { method: 'POST' });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.ok) {
        setCacheMessage('Đã xóa cache.');
      } else {
        setCacheMessage(data?.message || 'Lỗi xóa cache.');
      }
    } catch {
      setCacheMessage('Lỗi kết nối.');
    } finally {
      setClearingCache(false);
    }
  };

  const closeMobileNav = () => setSidebarOpen(false);

  const renderNavLinks = () =>
    visibleGroups.map((group) => (
      <div key={group.title} className="mb-4 last:mb-0">
        <p className="px-3 mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          {group.title}
        </p>
        <div className="space-y-0.5">
          {group.items.map(({ href, label }) => {
            const active = pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                key={href}
                href={href}
                onClick={closeMobileNav}
                className={`block rounded-lg px-3 py-2.5 text-sm transition-colors lg:py-2 ${
                  active
                    ? 'bg-slate-600 font-medium text-white'
                    : 'text-slate-300 hover:bg-slate-700 hover:text-white'
                }`}
              >
                {label}
              </Link>
            );
          })}
        </div>
      </div>
    ));

  const sidebarInner = (
    <>
      <div className="flex items-center justify-between gap-2 border-b border-slate-700 px-3 py-3 lg:px-4">
        <Link href={adminHomeHref} className="min-w-0 text-lg font-bold text-white truncate">
          188 Admin
        </Link>
        <button
          type="button"
          className="rounded-lg p-2 text-slate-300 hover:bg-slate-700 hover:text-white lg:hidden"
          aria-label="Đóng menu"
          onClick={closeMobileNav}
        >
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
      <nav className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-2 py-3 lg:py-2">
        {renderNavLinks()}
      </nav>
      <div className="border-t border-slate-700 p-2 shrink-0 pb-[max(0.5rem,env(safe-area-inset-bottom))]">
        <button
          type="button"
          onClick={() => {
            closeMobileNav();
            handleLogout();
          }}
          className="w-full rounded-lg px-3 py-2.5 text-left text-sm text-slate-300 hover:bg-slate-700 hover:text-white lg:py-2"
        >
          Đăng xuất
        </button>
      </div>
    </>
  );

  return (
    <div className="flex min-h-[100dvh] flex-col bg-slate-100 lg:flex-row">
      {sidebarOpen ? (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-black/45 backdrop-blur-[1px] lg:hidden"
          aria-label="Đóng menu điều hướng"
          onClick={closeMobileNav}
        />
      ) : null}

      <aside
        id="admin-sidebar"
        className={`fixed inset-y-0 left-0 z-50 flex w-[min(18.5rem,calc(100vw-2.5rem))] flex-col bg-slate-800 text-white shadow-xl transition-transform duration-200 ease-out lg:sticky lg:top-0 lg:z-auto lg:h-[100dvh] lg:w-56 lg:max-w-none lg:translate-x-0 lg:shadow-none xl:w-60 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
      >
        {sidebarInner}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col min-h-[100dvh] lg:min-h-0">
        <header className="sticky top-0 z-30 flex shrink-0 flex-wrap items-center gap-2 border-b border-gray-200 bg-white px-3 py-2 pt-[max(0.5rem,env(safe-area-inset-top,0px))] sm:px-4 lg:justify-end lg:px-6 lg:py-2.5">
          <div className="flex w-full items-center gap-2 lg:hidden">
            <button
              type="button"
              className="rounded-lg border border-slate-200 bg-white p-2 text-slate-700 shadow-sm hover:bg-slate-50"
              aria-expanded={sidebarOpen}
              aria-controls="admin-sidebar"
              onClick={() => setSidebarOpen(true)}
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <Link
              href={adminHomeHref}
              className="min-w-0 truncate text-base font-bold text-slate-800"
              onClick={closeMobileNav}
            >
              188 Admin
            </Link>
          </div>

          <div className="flex w-full flex-wrap items-center justify-end gap-2 sm:flex-nowrap lg:w-auto lg:ml-auto">
            {showClearCacheButton ? (
              <>
                <button
                  type="button"
                  onClick={handleClearCache}
                  disabled={clearingCache}
                  className="shrink-0 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 sm:text-sm"
                  title="Xóa cache danh mục/sản phẩm để thấy thay đổi ngay trên site"
                >
                  {clearingCache ? 'Đang xóa…' : 'Xóa cache'}
                </button>
                {cacheMessage ? (
                  <span className="max-w-[min(100%,14rem)] truncate text-xs text-slate-600 sm:max-w-xs sm:text-sm">
                    {cacheMessage}
                  </span>
                ) : null}
              </>
            ) : null}
          </div>
        </header>

        <main className="flex-1 overflow-x-auto overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
