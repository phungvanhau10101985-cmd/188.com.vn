'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { INFO_PAGES } from '@/app/info/info-pages.config';

interface InfoPageLayoutProps {
  children: React.ReactNode;
  title: string;
}

export default function InfoPageLayout({ children, title }: InfoPageLayoutProps) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen bg-zinc-50">
      <div className="max-w-6xl mx-auto px-4 py-8 md:py-10">
        <div className="flex flex-col lg:flex-row gap-6 lg:gap-8">
          <aside className="lg:w-72 flex-shrink-0">
            <nav
              className="bg-white rounded-2xl border border-zinc-200/90 shadow-sm overflow-hidden lg:sticky lg:top-24"
              aria-label="Thông tin và chính sách"
            >
              <div className="px-4 py-3 border-b border-zinc-100 bg-gradient-to-r from-orange-50 to-white">
                <h2 className="text-xs font-semibold text-orange-800 uppercase tracking-wider">
                  Thông tin & Chính sách
                </h2>
              </div>
              <ul className="p-2 max-h-[min(70vh,28rem)] overflow-y-auto overscroll-contain lg:max-h-none">
                {INFO_PAGES.map(({ slug, title: t }) => {
                  const href = `/info/${slug}`;
                  const isActive = pathname === href;
                  return (
                    <li key={slug}>
                      <Link
                        href={href}
                        className={`block px-3 py-2.5 rounded-xl text-sm font-medium transition-colors ${
                          isActive
                            ? 'bg-orange-50 text-orange-800 ring-1 ring-orange-200/80'
                            : 'text-zinc-700 hover:bg-zinc-50'
                        }`}
                      >
                        {t}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </nav>
          </aside>

          <main className="flex-1 min-w-0">
            <article className="bg-white rounded-2xl border border-zinc-200/90 shadow-sm overflow-hidden">
              <header className="border-b border-zinc-100 px-6 py-5 md:px-8 bg-gradient-to-r from-orange-50/90 to-white">
                <h1 className="text-xl md:text-2xl font-bold text-zinc-900 leading-snug">{title}</h1>
              </header>
              <div className="p-6 md:p-8 prose prose-zinc max-w-none prose-headings:font-semibold prose-headings:text-zinc-900 prose-p:text-zinc-600 prose-li:text-zinc-600 prose-a:text-orange-600 hover:prose-a:text-orange-700 prose-strong:text-zinc-900">
                {children}
              </div>
            </article>

            <div className="mt-6">
              <Link
                href="/info"
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl border border-zinc-200 bg-white text-zinc-700 text-sm font-medium hover:bg-zinc-50 transition-colors shadow-sm"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
                Về trang thông tin
              </Link>
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
