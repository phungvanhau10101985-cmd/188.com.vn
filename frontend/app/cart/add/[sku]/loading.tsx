export default function CartAddLoading() {
  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50">
      <div className="rounded-xl bg-white px-6 py-4 text-sm text-gray-700 shadow-lg">
        Đang mở chọn sản phẩm…
      </div>
    </div>
  );
}
