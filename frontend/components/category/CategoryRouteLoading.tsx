/**
 * Màn chờ thống nhất khi vào /danh-muc — spinner + skeleton rõ ràng, tránh màn vàng/cam
 * đứng im khiến khách không biết trang có đang tải hay không.
 */
export default function CategoryRouteLoading({
  message = 'Đang tải danh mục…',
  compactHero = false,
}: {
  message?: string;
  /** Trang lưới danh mục tổng — hero cao hơn. */
  compactHero?: boolean;
}) {
  return (
    <div
      className="min-h-[60vh] w-full bg-white pb-16 md:pb-8"
      aria-busy="true"
      aria-live="polite"
      aria-label={message}
    >
      <div className="max-w-7xl mx-auto px-4 pt-4 pb-6 md:py-6 animate-pulse">
        <div className="flex items-center gap-2 mb-4">
          <div className="h-3 bg-gray-200 rounded w-16" />
          <div className="h-3 bg-gray-200 rounded w-4" />
          <div className="h-3 bg-gray-200 rounded w-24" />
        </div>
        <div className="h-7 sm:h-8 bg-gray-200 rounded w-full max-w-xl mb-4" />
        {!compactHero ? (
          <div className="h-10 bg-gray-100 rounded-lg w-full mb-6 border border-gray-100" />
        ) : null}
      </div>

      <div
        className={`relative flex flex-col items-center justify-center gap-4 px-6 ${
          compactHero
            ? 'h-[min(52vh,480px)] bg-gradient-to-br from-orange-50 via-amber-50/80 to-orange-100/60'
            : 'h-[min(40vh,320px)] bg-gray-50/80 border-y border-gray-100'
        }`}
      >
        <div
          className="h-11 w-11 rounded-full border-[3px] border-orange-200 border-t-[#ea580c] animate-spin"
          role="status"
          aria-hidden
        />
        <p className="text-sm font-medium text-gray-700 text-center">{message}</p>
        <p className="text-xs text-gray-500 text-center max-w-sm">
          Vui lòng đợi trong giây lát — danh mục lớn có thể mất vài giây.
        </p>
      </div>

      <div className="max-w-7xl mx-auto px-4 pt-6 animate-pulse">
        <div className="h-5 bg-gray-200 rounded w-48 mb-4" />
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-5">
          {[...Array(10)].map((_, i) => (
            <div
              key={i}
              className="bg-white rounded-xl border border-gray-100 overflow-hidden shadow-sm"
            >
              <div className="aspect-square bg-gray-100" />
              <div className="p-3 space-y-2">
                <div className="h-3 bg-gray-100 rounded w-3/4" />
                <div className="h-3 bg-gray-100 rounded w-full" />
                <div className="h-4 bg-gray-100 rounded w-2/5" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
