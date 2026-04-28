export default function AccountLoading() {
  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <div className="flex items-center gap-3 text-gray-600">
        <span className="w-7 h-7 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
        <span className="text-sm">Đang tải tài khoản...</span>
      </div>
    </div>
  );
}
