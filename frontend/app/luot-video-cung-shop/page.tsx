import { Suspense } from 'react';
import ShopVideoFeedClient from '@/components/mobile/ShopVideoFeedClient';

function FeedFallback() {
  return (
    <div className="flex min-h-[100dvh] flex-col items-center justify-center bg-black text-white/80 text-sm">
      Đang mở lướt video…
    </div>
  );
}

export default function LuotVideoCungShopPage() {
  return (
    <Suspense fallback={<FeedFallback />}>
      <ShopVideoFeedClient />
    </Suspense>
  );
}
