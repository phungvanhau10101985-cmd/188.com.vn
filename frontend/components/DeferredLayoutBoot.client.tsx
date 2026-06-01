'use client';

import dynamic from 'next/dynamic';

const DraggableThirdPartyFloaters = dynamic(
  () => import('@/components/DraggableThirdPartyFloaters'),
  { ssr: false }
);
const NanoAiMobileLauncherAdjust = dynamic(
  () => import('@/components/NanoAiMobileLauncherAdjust'),
  { ssr: false }
);
const GoogleCustomerReviewsBadge = dynamic(
  () => import('@/components/GoogleCustomerReviewsBadge'),
  { ssr: false }
);

/** Widget nền — tải sau hydrate, không chặn LCP. */
export function DeferredLayoutFloaters() {
  return (
    <>
      <DraggableThirdPartyFloaters />
      <NanoAiMobileLauncherAdjust />
      <GoogleCustomerReviewsBadge />
    </>
  );
}

export const DeferredPwaPushRegister = dynamic(
  () => import('@/components/PwaPushRegister'),
  { ssr: false }
);
