/**
 * Hiển thị ngay khi chuyển route /danh-muc/... (perceived performance).
 * Không thay metadata/JSON-LD: chúng vẫn do layout + generateMetadata SSR.
 */
export default function DanhMucLoading() {
  return (
    <main
      className="max-w-7xl mx-auto px-4 pt-4 pb-6 md:py-6"
      aria-busy="true"
      aria-label="Đang tải danh mục"
    >
      <div className="flex flex-wrap gap-2 mb-4">
        <div className="h-4 w-14 rounded bg-gray-200 animate-pulse" />
        <div className="h-4 w-4 rounded bg-gray-100" />
        <div className="h-4 w-24 rounded bg-gray-200 animate-pulse" />
        <div className="h-4 w-4 rounded bg-gray-100" />
        <div className="h-4 w-32 rounded bg-gray-200 animate-pulse" />
      </div>
      <div className="h-9 max-w-2xl rounded-lg bg-gray-200 animate-pulse mb-4" />
      <div className="h-6 w-48 rounded bg-gray-100 animate-pulse mb-6" />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-4">
        {Array.from({ length: 12 }).map((_, i) => (
          <div key={i} className="rounded-xl border border-gray-100 overflow-hidden bg-white shadow-sm">
            <div className="aspect-[3/4] bg-gray-100 animate-pulse" />
            <div className="p-2 space-y-2">
              <div className="h-3 w-full bg-gray-100 rounded animate-pulse" />
              <div className="h-3 w-2/3 bg-gray-100 rounded animate-pulse" />
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
