'use client';

import Link from 'next/link';

export default function MobilePromoBanner() {
  return (
    <div className="md:hidden mx-4 mb-4 rounded-xl overflow-hidden shadow-lg">
      <Link
        href="/?category=deal"
        className="block bg-[#dc2626] text-white p-4 relative min-h-[100px] flex flex-col justify-between"
      >
        <div className="flex items-start justify-between gap-2">
          <div>
            <span className="text-3xl font-bold leading-tight block">60%</span>
            <span className="text-sm font-medium text-white/95">Xả kho hàng lẻ size</span>
          </div>
          <span className="text-[10px] font-semibold text-white/80 uppercase tracking-wider">
            188.COM.VN
          </span>
        </div>
        <div className="mt-3 text-center">
          <span className="inline-block bg-white/20 hover:bg-white/30 text-white text-xs font-semibold px-4 py-2 rounded-lg transition-colors">
            &gt;&gt; Click xem ngay &lt;&lt;
          </span>
        </div>
      </Link>
    </div>
  );
}
