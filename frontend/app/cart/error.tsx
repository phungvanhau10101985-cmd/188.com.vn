'use client';

export default function CartError({ reset }: { reset: () => void }) {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-6">
      <div className="bg-white border border-gray-200 rounded-2xl p-8 max-w-lg w-full text-center">
        <h2 className="text-xl font-bold text-gray-900 mb-2">Không thể tải giỏ hàng</h2>
        <p className="text-sm text-gray-600 mb-6">Vui lòng thử lại hoặc kiểm tra kết nối mạng.</p>
        <button
          type="button"
          onClick={() => reset()}
          className="px-5 py-2.5 bg-[#ea580c] text-white rounded-lg font-medium hover:bg-[#c2410c]"
        >
          Thử lại
        </button>
      </div>
    </div>
  );
}
