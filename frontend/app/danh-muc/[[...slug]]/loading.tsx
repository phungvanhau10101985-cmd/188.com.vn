/**
 * Hiển thị ngay khi chuyển route /danh-muc (perceived performance).
 */
export default function DanhMucLoading() {
  return (
    <div
      className="min-h-screen w-full bg-white pb-16 md:pb-8"
      aria-busy="true"
      aria-label="Đang tải danh mục"
    >
      <h1 className="sr-only">Tất cả danh mục</h1>
      <div className="relative left-1/2 h-[min(72vh,640px)] w-screen max-w-[100vw] -translate-x-1/2 overflow-hidden bg-gradient-to-br from-orange-100 to-amber-50 md:left-0 md:h-[min(78vh,720px)] md:w-full md:max-w-7xl md:translate-x-0 md:mx-auto">
        <div className="absolute inset-0 animate-pulse bg-gradient-to-br from-orange-200/40 via-orange-100/30 to-amber-100/40" />
      </div>
    </div>
  );
}
