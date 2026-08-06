'use client';

const TRUST_POINTS = [
  {
    icon: '✓',
    title: 'Chọn lựa kỹ lưỡng',
    description: 'Thông tin sản phẩm được trình bày rõ ràng.',
  },
  {
    icon: '↗',
    title: 'Đặt hàng thuận tiện',
    description: 'Thao tác nhanh, dễ chọn sản phẩm phù hợp.',
  },
  {
    icon: '♡',
    title: 'Hỗ trợ khi cần',
    description: 'Đội ngũ sẵn sàng giải đáp trước khi mua.',
  },
];

/** Thanh tạo sự an tâm ngay sau hero của LadiPage public. */
export default function LadipageTrustStrip() {
  return (
    <section aria-label="Lợi ích khi mua sắm" className="my-6 rounded-2xl border border-gray-100 bg-white px-4 py-4 shadow-sm md:my-8 md:px-6">
      <div className="grid gap-4 sm:grid-cols-3 sm:gap-0">
        {TRUST_POINTS.map((point, index) => (
          <div
            key={point.title}
            className={`flex items-start gap-3 px-2 sm:px-5 ${index > 0 ? 'sm:border-l sm:border-gray-100' : ''}`}
          >
            <span aria-hidden="true" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-orange-50 text-base font-bold text-orange-600">
              {point.icon}
            </span>
            <div>
              <p className="text-sm font-bold text-gray-900">{point.title}</p>
              <p className="mt-0.5 text-xs leading-relaxed text-gray-500">{point.description}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
