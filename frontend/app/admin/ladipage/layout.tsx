'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { DEFAULT_LADIPAGE_KIND_SLUG, LADIPAGE_KIND_TABS, ladipageListHref } from '@/components/ladipage/ladipage-admin-kinds';

function activeKindSlug(pathname: string): string {
  const base = '/admin/ladipage';
  const baseSlash = `${base}/`;
  if (pathname === base || pathname === baseSlash) {
    return DEFAULT_LADIPAGE_KIND_SLUG;
  }
  for (const tab of LADIPAGE_KIND_TABS) {
    const listPath = ladipageListHref(tab.slug);
    if (pathname === listPath || pathname.startsWith(`${listPath}/`)) {
      return tab.slug;
    }
  }
  if (pathname.startsWith(`${base}/new`) || pathname.includes('/edit')) return '';
  return DEFAULT_LADIPAGE_KIND_SLUG;
}

export default function AdminLadipageLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || '';
  const activeSlug = activeKindSlug(pathname);
  const isFormPage = pathname.includes('/new') || pathname.includes('/edit');

  return (
    <div className="mx-auto max-w-6xl p-4 md:p-6">
      {!isFormPage && (
        <>
          <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-xl font-bold text-gray-900 md:text-2xl">Ladipage AI</h1>
              <p className="mt-1 text-sm text-gray-500">
                Landing page bán hàng tự động — mỗi loại một danh sách riêng.
              </p>
            </div>
            <Link
              href="/admin/ladipage/new"
              className="inline-flex items-center rounded-full bg-orange-600 px-5 py-2.5 text-sm font-semibold text-white shadow hover:bg-orange-700"
            >
              + Tạo ladipage mới
            </Link>
          </div>

          <nav
            className="mb-5 flex flex-wrap gap-2 border-b border-gray-200 pb-3"
            aria-label="Loại ladipage"
          >
            {LADIPAGE_KIND_TABS.map((tab) => {
              const active = tab.slug === activeSlug;
              return (
                <Link
                  key={tab.slug}
                  href={ladipageListHref(tab.slug)}
                  className={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                    active
                      ? 'bg-orange-600 text-white shadow-sm'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  }`}
                >
                  {tab.label}
                </Link>
              );
            })}
          </nav>
        </>
      )}

      {children}
    </div>
  );
}
