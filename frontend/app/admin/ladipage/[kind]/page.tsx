import { notFound } from 'next/navigation';
import { Suspense } from 'react';
import AdminLadipageListPanel from '@/components/ladipage/AdminLadipageListPanel';
import { ladipageTabFromSlug } from '@/components/ladipage/ladipage-admin-kinds';

function ListFallback() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="h-16 animate-pulse rounded-xl bg-gray-100" />
      ))}
    </div>
  );
}

export default async function AdminLadipageKindPage({
  params,
}: {
  params: Promise<{ kind: string }>;
}) {
  const { kind: kindSlug } = await params;
  const tab = ladipageTabFromSlug(kindSlug);
  if (!tab) notFound();

  const emptyHints: Record<string, string> = {
    '1-san-pham': 'Chưa có ladipage 1 SP. Tạo thủ công hoặc đợi khách xem PDP để hệ thống tự sinh.',
    'danh-muc': 'Chưa có ladipage theo danh mục.',
    'nhieu-san-pham': 'Chưa có ladipage nhiều sản phẩm.',
  };

  return (
    <Suspense fallback={<ListFallback />}>
      <AdminLadipageListPanel
        kind={tab.kind}
        kindLabel={tab.label}
        kindDescription={tab.description}
        emptyHint={emptyHints[tab.slug] || 'Chưa có ladipage loại này.'}
        newHref={
          tab.kind === 'category'
            ? '/admin/ladipage/new?mode=category'
            : tab.kind === 'product_single'
              ? '/admin/ladipage/new?mode=product_single'
              : '/admin/ladipage/new?mode=products_multi'
        }
      />
    </Suspense>
  );
}
