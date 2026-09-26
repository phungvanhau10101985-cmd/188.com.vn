import NotFoundHomeLink from '@/components/NotFoundHomeLink';

/**
 * Phải là Server Component đồng bộ, không gọi headers()/cookies().
 * notFound() nằm trong Suspense của root layout — nếu file này suspend,
 * Next đã gửi HTTP 200 rồi mới gắn UI 404 (soft 404 với Google).
 */
export default function NotFound() {
  return (
    <div className="min-h-[60vh] bg-gray-50 flex flex-col items-center justify-center px-4 text-center">
      <p className="text-6xl font-bold text-[#ea580c] mb-2 tabular-nums">404</p>
      <h1 className="text-gray-800 font-medium mb-1">Không tìm thấy trang</h1>
      <p className="text-sm text-gray-500 mb-6">Đường dẫn không tồn tại hoặc đã được gỡ.</p>
      <NotFoundHomeLink />
    </div>
  );
}
