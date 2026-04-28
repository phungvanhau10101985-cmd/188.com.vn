'use client';

export default function AccountError({ reset }: { reset: () => void }) {
  return (
    <div className="min-h-[60vh] flex items-center justify-center px-6">
      <div className="bg-white border border-gray-200 rounded-2xl p-8 max-w-lg w-full text-center">
        <h2 className="text-xl font-bold text-gray-900 mb-2">Không thể tải tài khoản</h2>
        <p className="text-sm text-gray-600 mb-6">Vui lòng thử lại sau.</p>
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
