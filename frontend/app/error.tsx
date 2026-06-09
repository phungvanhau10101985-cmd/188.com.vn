'use client';

import Button from '@/components/ui/Button';

export default function RootError({ reset }: { reset: () => void }) {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-6">
      <div className="bg-white border border-gray-200 rounded-2xl p-8 max-w-lg w-full text-center">
        <h2 className="text-xl font-bold text-gray-900 mb-2">Có lỗi xảy ra</h2>
        <p className="text-sm text-gray-600 mb-6">
          Vui lòng thử tải lại trang. Nếu lỗi vẫn tiếp tục, hãy thử lại sau.
        </p>
        <Button type="button" variant="primary" onClick={() => reset()}>
          Thử lại
        </Button>
      </div>
    </div>
  );
}
