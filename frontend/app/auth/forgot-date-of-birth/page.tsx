// frontend/app/auth/forgot-date-of-birth/page.tsx
import Link from 'next/link';

export default function ForgotDateOfBirthPage() {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4 py-8">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-lg shadow-sm p-6 text-center">
          <h1 className="text-xl font-semibold text-gray-900 mb-2">Đăng nhập Gmail</h1>
          <p className="text-sm text-gray-600 mb-4">
            Chức năng lấy lại ngày sinh không còn hỗ trợ. Vui lòng đăng nhập bằng Gmail.
          </p>
          <Link
            href="/auth/login"
            className="inline-flex items-center justify-center px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700"
          >
            Đến trang đăng nhập
          </Link>
        </div>
      </div>
    </div>
  );
}