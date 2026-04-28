// features/auth/pages/forgot-password/page.tsx
import Link from 'next/link';

export default function ForgotPasswordPage() {
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <h1 className="text-center text-3xl font-bold text-gray-900 mb-8">
          188.com.vn
        </h1>
      </div>
      <div className="sm:mx-auto sm:w-full sm:max-w-md bg-white border border-gray-200 rounded-2xl shadow-sm p-6 text-center space-y-3">
        <p className="text-gray-700">Vui lòng dùng trang khôi phục ngày sinh để nhận OTP.</p>
        <Link href="/auth/forgot-date-of-birth" className="inline-flex items-center justify-center px-4 py-2 rounded-lg bg-orange-500 text-white font-medium hover:bg-orange-600">
          Khôi phục ngày sinh
        </Link>
      </div>
    </div>
  );
}
