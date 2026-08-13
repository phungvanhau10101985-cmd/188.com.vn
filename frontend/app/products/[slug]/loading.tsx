/** Skeleton PDP — hiện ngay khi bấm link, trước khi SSR xong. */
export default function ProductLoading() {
  return (
    <div className="min-h-screen bg-white pb-28 md:bg-gray-50 md:pb-12" aria-busy="true" aria-label="Đang tải sản phẩm">
      {/* Mobile — khớp layout ProductDetailMobile */}
      <div className="md:hidden animate-pulse">
        <div className="w-full aspect-[3/4] max-h-[85vh] bg-gray-200" />
        <div className="px-4 py-3 space-y-3">
          <div className="h-4 bg-gray-200 rounded w-3/4" />
          <div className="h-5 bg-gray-200 rounded w-full" />
          <div className="h-5 bg-gray-200 rounded w-5/6" />
          <div className="rounded-2xl border border-orange-100 bg-orange-50/40 p-3 space-y-2">
            <div className="h-7 bg-orange-100 rounded w-2/5" />
            <div className="h-3 bg-gray-200 rounded w-1/3" />
          </div>
          <div className="flex gap-2 pt-1">
            <div className="h-16 w-16 rounded-lg bg-gray-200 shrink-0" />
            <div className="h-16 w-16 rounded-lg bg-gray-200 shrink-0" />
            <div className="h-16 w-16 rounded-lg bg-gray-200 shrink-0" />
          </div>
        </div>
        <div className="fixed bottom-0 inset-x-0 z-40 border-t border-gray-200 bg-white px-4 py-3 flex gap-2">
          <div className="h-11 flex-1 rounded-xl bg-gray-200" />
          <div className="h-11 flex-[1.2] rounded-xl bg-orange-200" />
        </div>
      </div>

      {/* Desktop */}
      <div className="hidden md:block py-8">
        <div className="max-w-6xl mx-auto px-4 animate-pulse">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div className="aspect-square bg-gray-200 rounded-xl" />
            <div className="space-y-4">
              <div className="h-6 bg-gray-200 rounded w-2/3" />
              <div className="h-4 bg-gray-200 rounded w-1/2" />
              <div className="h-10 bg-gray-200 rounded w-1/3" />
              <div className="h-32 bg-gray-200 rounded" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
