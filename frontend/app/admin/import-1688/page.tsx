'use client';

import Link from 'next/link';

/** Route cũ «Cookie / Import 1688» — tính năng 1688 + nhập cookie đã gỡ; import chỉ còn Hibox trên trang Sản phẩm. */
export default function AdminImport1688LegacyPage() {
  return (
    <div className="mx-auto max-w-lg p-6">
      <h1 className="text-xl font-semibold text-gray-900">Trang đã được gỡ</h1>
      <p className="mt-3 text-sm leading-relaxed text-gray-600">
        Cấu hình cookie 1688 và import trực tiếp từ 1688 không còn dùng. Lấy dữ liệu sản phẩm chỉ qua{' '}
        <strong className="font-medium text-gray-800">Hibox</strong> (không cần cookie 1688) trên trang quản trị sản phẩm.
      </p>
      <Link
        href="/admin/products#import-hibox"
        className="mt-6 inline-flex rounded-lg bg-orange-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-orange-700"
      >
        Mở Import Hibox
      </Link>
    </div>
  );
}
