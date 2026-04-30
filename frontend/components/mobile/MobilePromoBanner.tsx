'use client';

import Link from 'next/link';

export default function MobilePromoBanner() {
  return (
    <div className="md:hidden mx-4 mb-4 rounded-xl overflow-hidden shadow-lg">
      <Link
        href="/?category=deal"
        className="block bg-[#dc2626] text-white p-4 relative min-h-[104px] flex flex-col justify-between active:opacity-95"
      >
        <div className="flex items-start justify-between gap-2">
          <div>
            <span className="text-3xl font-bold leading-tight block text-white">60%</span>
            <span className="text-sm font-medium text-white">Xả kho hàng lẻ size</span>
          </div>
          <span className="text-[11px] font-semibold uppercase tracking-wider text-white">
            188.COM.VN
          </span>
        </div>
        <div className="mt-3 text-center">
          <span className="inline-flex min-h-[44px] min-w-[140px] items-center justify-center bg-white/25 text-white text-xs font-semibold px-5 py-2.5 rounded-lg transition-colors">
            &gt;&gt; Xem ngay &lt;&lt;
          </span>
        </div>
      </Link>
    </div>
  );
}
