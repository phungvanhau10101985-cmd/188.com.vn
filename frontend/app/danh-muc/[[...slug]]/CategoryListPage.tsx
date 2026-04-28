'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter, usePathname } from 'next/navigation';
import type { CategoryLevel1, CategoryLevel2, CategoryLevel3 } from '@/types/api';

interface CategoryListPageProps {
  categoryTree: CategoryLevel1[];
}

/** Danh sách danh mục cấp 1 + link đặc biệt (SALE SỐC) */
const EXTRA_LINKS = [
  { label: 'SALE SỐC', href: '/deals', showArrow: true },
];

function slugOf(s: string | undefined): string {
  return (s || '').trim().toLowerCase().replace(/\s+/g, '-');
}

/** Chỉ viết hoa chữ cái đầu cho danh mục cấp 2 */
function capitalizeFirst(s: string): string {
  if (!s || !s.length) return s;
  return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
}

const ArrowRight = ({ open }: { open?: boolean }) => (
  <svg
    className={`w-5 h-5 text-[#ea580c] flex-shrink-0 transition-transform ${open ? 'rotate-90' : ''}`}
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
  </svg>
);

export default function CategoryListPage({ categoryTree }: CategoryListPageProps) {
  const router = useRouter();
  const pathname = usePathname();
  const list = categoryTree || [];
  const [openL1, setOpenL1] = useState<Set<string>>(new Set());
  const [openL2, setOpenL2] = useState<Set<string>>(new Set());

  // Mobile: không dùng trang danh mục riêng, chuyển về trang chủ (danh mục mở từ nút 3 gạch trên header)
  useEffect(() => {
    if (typeof window !== 'undefined' && pathname === '/danh-muc' && window.innerWidth < 768) {
      router.replace('/');
    }
  }, [pathname, router]);

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

  return (
    <>
      {/* Mobile: header cam + list danh mục, mũi tên sổ cấp 2/3, bấm chữ mới vào trang */}
      <div className="md:hidden min-h-screen bg-white pb-16">
        {/* Header cam: back + "Danh mục sản phẩm" */}
        <header className="bg-[#ea580c] text-white sticky top-0 z-40 shadow-md">
          <div className="flex items-center h-12 px-3 gap-2">
            <button
              type="button"
              onClick={() => router.back()}
              className="flex-shrink-0 w-10 h-10 flex items-center justify-center rounded-lg bg-white/20 active:bg-white/30"
              aria-label="Quay lại"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <h1 className="flex-1 text-center text-base font-bold pr-10">
              Danh mục sản phẩm
            </h1>
          </div>
        </header>

        {/* List danh mục: bấm mũi tên sổ cấp 2/3, bấm chữ mới vào trang */}
        <nav className="bg-white" aria-label="Danh mục sản phẩm">
          {list.map((cat) => {
            const slug1 = cat.slug || slugOf(cat.name);
            const hasChildren = cat.children && cat.children.length > 0;
            const isOpen = openL1.has(cat.name);

            return (
              <div key={cat.name} className="border-b border-gray-200">
                <div className="flex items-center w-full py-4 px-4 text-gray-900 font-medium text-sm active:bg-gray-50">
                  <Link
                    href={`/danh-muc/${encodeURIComponent(slug1)}`}
                    className="flex-1 min-w-0 uppercase hover:text-[#ea580c] transition-colors"
                  >
                    {cat.name}
                  </Link>
                  {hasChildren ? (
                    <button
                      type="button"
                      onClick={(e) => { e.preventDefault(); toggleL1(cat.name); }}
                      className="flex-shrink-0 p-1 -m-1"
                      aria-label={isOpen ? 'Thu gọn' : 'Mở rộng'}
                    >
                      <ArrowRight open={isOpen} />
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
                            <Link
                              href={`/danh-muc/${encodeURIComponent(slug1)}/${encodeURIComponent(slug2)}`}
                              className="flex-1 min-w-0 line-clamp-2 hover:text-[#ea580c] transition-colors"
                            >
                              {capitalizeFirst(c2.name)}
                            </Link>
                            {hasL3 ? (
                              <button
                                type="button"
                                onClick={(e) => { e.preventDefault(); toggleL2(keyL2); }}
                                className="flex-shrink-0 p-1 -m-1"
                                aria-label={isOpenL2 ? 'Thu gọn' : 'Mở rộng'}
                              >
                                <ArrowRight open={isOpenL2} />
                              </button>
                            ) : null}
                          </div>
                          {hasL3 && isOpenL2 && c2.children && (
                            <div className="bg-gray-100/80 border-t border-gray-100">
                              {(c2.children as CategoryLevel3[]).map((c3) => {
                                const slug3 = c3.slug || slugOf(c3.name);
                                return (
                                  <Link
                                    key={c3.name}
                                    href={`/danh-muc/${encodeURIComponent(slug1)}/${encodeURIComponent(slug2)}/${encodeURIComponent(slug3)}`}
                                    className="flex items-center w-full py-2 px-3 text-gray-500 font-medium text-xs active:bg-gray-200 border-b border-gray-100 last:border-b-0 hover:text-[#ea580c] transition-colors"
                                  >
                                    {capitalizeFirst(c3.name)}
                                  </Link>
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
          {EXTRA_LINKS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="flex items-center justify-between w-full py-4 px-4 border-b border-gray-200 text-gray-900 font-medium text-sm active:bg-gray-50"
            >
              <span className="uppercase">{item.label}</span>
              {item.showArrow && (
                <svg className="w-5 h-5 text-[#ea580c] flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              )}
            </Link>
          ))}
        </nav>
      </div>

      {/* Desktop: giữ nội dung cũ */}
      <div className="hidden md:block max-w-7xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">Danh mục sản phẩm</h1>
        <p className="text-gray-600 mb-6">
          Chọn danh mục từ thanh điều hướng hoặc{' '}
          <Link href="/" className="text-[#ea580c] hover:underline">
            về trang chủ
          </Link>{' '}
          để xem sản phẩm.
        </p>
        <div className="flex flex-wrap gap-2 mb-6">
          {list.map((cat) => {
            const slug = cat.slug || slugOf(cat.name);
            return (
              <Link
                key={cat.name}
                href={`/danh-muc/${encodeURIComponent(slug)}`}
                className="px-4 py-2 rounded-lg bg-gray-100 text-gray-800 hover:bg-[#ea580c] hover:text-white font-medium transition-colors"
              >
                {cat.name}
              </Link>
            );
          })}
        </div>
        <Link
          href="/"
          className="inline-flex gap-2 px-4 py-2 rounded-lg bg-[#ea580c] text-white font-medium hover:bg-orange-600"
        >
          ← Về trang chủ
        </Link>
      </div>
    </>
  );
}
