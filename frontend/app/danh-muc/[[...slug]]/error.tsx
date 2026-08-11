'use client';

import { useEffect, useRef } from 'react';
import LoadingLink from '@/components/ui/LoadingLink';

export default function CategoryError({ reset }: { reset: () => void }) {
  const autoRetried = useRef(false);

  useEffect(() => {
    if (autoRetried.current) return;
    autoRetried.current = true;
    const timer = window.setTimeout(() => reset(), 2500);
    return () => window.clearTimeout(timer);
  }, [reset]);

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-6">
      <div className="bg-white border border-gray-200 rounded-2xl p-8 max-w-lg w-full text-center">
        <div
          className="mx-auto mb-4 h-10 w-10 rounded-full border-[3px] border-orange-200 border-t-[#ea580c] animate-spin"
          role="status"
          aria-label="Đang thử tải lại"
        />
        <h2 className="text-xl font-bold text-gray-900 mb-2">Không thể tải danh mục</h2>
        <p className="text-sm text-gray-600 mb-6">
          Máy chủ đang bận hoặc kết nối chậm. Hệ thống sẽ tự thử lại sau vài giây — hoặc bấm nút
          bên dưới.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <button
            type="button"
            onClick={() => reset()}
            className="w-full sm:w-auto px-5 py-2.5 bg-[#ea580c] text-white rounded-lg font-medium hover:bg-[#c2410c]"
          >
            Thử lại
          </button>
          <LoadingLink
            href="/"
            className="w-full sm:w-auto px-5 py-2.5 border border-gray-300 text-gray-800 rounded-lg font-medium hover:bg-gray-50 text-center"
          >
            Về trang chủ
          </LoadingLink>
        </div>
      </div>
    </div>
  );
}
