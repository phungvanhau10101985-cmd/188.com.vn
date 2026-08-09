import Link from 'next/link';
import type { LadipageRelatedItem } from '@/lib/ladipage-public';

interface RelatedLadipagesStripProps {
  items: LadipageRelatedItem[];
  heading?: string;
}

/** Link chéo: danh mục/cluster → các ladipage bộ sưu tập (USP chất liệu). */
export default function RelatedLadipagesStrip({
  items,
  heading = 'Bộ sưu tập theo chất liệu',
}: RelatedLadipagesStripProps) {
  if (!items.length) return null;

  return (
    <section className="mb-6 rounded-xl border border-orange-100 bg-gradient-to-br from-orange-50/80 to-white p-4" aria-label={heading}>
      <h2 className="text-sm font-semibold text-gray-900">{heading}</h2>
      <p className="mt-0.5 text-xs text-gray-500">
        Landing bổ sung (góc chất liệu / bộ sưu tập) — trang danh mục vẫn là trang SEO chính.
      </p>
      <ul className="mt-3 flex flex-wrap gap-2">
        {items.map((item) => (
          <li key={item.id}>
            <Link
              href={item.path}
              className="inline-flex items-center rounded-full border border-orange-200 bg-white px-3 py-1.5 text-xs font-medium text-orange-800 shadow-sm hover:border-orange-400 hover:bg-orange-50"
            >
              {item.material_filter ? `${item.material_filter} · ` : ''}
              <span className="line-clamp-1 max-w-[14rem]">{item.title}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
