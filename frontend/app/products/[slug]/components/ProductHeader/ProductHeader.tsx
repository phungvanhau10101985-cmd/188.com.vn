// frontend/app/products/[slug]/components/ProductHeader/ProductHeader.tsx
'use client';

import { Fragment } from 'react';
import Link from 'next/link';
import { Product } from '@/types/api';
import { truncateText } from '@/lib/utils';

interface ProductHeaderProps {
  product: Product;
}

export default function ProductHeader({ product }: ProductHeaderProps) {
  const toSlug = (value: string) =>
    value
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/đ/g, 'd')
      .replace(/Đ/g, 'd')
      .trim()
      .toLowerCase()
      .replace(/\s+/g, '-');
  const categoryParts = [product.category, product.subcategory, product.sub_subcategory].filter(Boolean) as string[];
  let categoryPath = '/danh-muc';
  const categoryCrumbs = categoryParts.map((name) => {
    categoryPath += `/${encodeURIComponent(toSlug(name))}`;
    return { name, href: categoryPath };
  });

  return (
    <nav className="bg-white border-b border-gray-200">
      <div className="max-w-7xl mx-auto px-4 py-2">
        <div className="flex items-center space-x-2 text-xs text-gray-600">
          <Link href="/" className="hover:text-blue-600 transition-colors">
            Trang chủ
          </Link>
          {categoryCrumbs.map((crumb) => (
            <Fragment key={crumb.href}>
              <span>/</span>
              <Link href={crumb.href} className="hover:text-blue-600 transition-colors">
                {crumb.name}
              </Link>
            </Fragment>
          ))}
          <span>/</span>
          <span className="text-gray-900 font-medium line-clamp-1">
            {truncateText(product.name, 50)}
          </span>
        </div>
      </div>
    </nav>
  );
}
