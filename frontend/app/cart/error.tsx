'use client';

import Button from '@/components/ui/Button';
import ReportRouteError from '@/components/ReportRouteError';

export default function CartError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-6">
      <ReportRouteError error={error} />
      <div className="bg-white border border-gray-200 rounded-2xl p-8 max-w-lg w-full text-center">
        <h2 className="text-xl font-bold text-gray-900 mb-2">Không thể tải giỏ hàng</h2>
        <p className="text-sm text-gray-600 mb-6">Vui lòng thử lại hoặc kiểm tra kết nối mạng.</p>
        <Button type="button" variant="primary" onClick={() => reset()}>
          Thử lại
        </Button>
      </div>
    </div>
  );
}
