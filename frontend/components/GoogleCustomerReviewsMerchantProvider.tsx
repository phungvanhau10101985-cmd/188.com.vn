'use client';

import { createContext, useContext } from 'react';

const MerchantIdContext = createContext<number | null | undefined>(undefined);

export function GoogleCustomerReviewsMerchantProvider({
  merchantId,
  children,
}: {
  /** Từ SSR layout (`fetchPublicSiteEmbeds`) — tránh client gọi sai base URL. */
  merchantId?: number | null;
  children: React.ReactNode;
}) {
  const value =
    typeof merchantId === 'number' && Number.isFinite(merchantId) && merchantId > 0 ? merchantId : null;
  return <MerchantIdContext.Provider value={value}>{children}</MerchantIdContext.Provider>;
}

export function useGoogleCustomerReviewsMerchantIdFromLayout(): number | null | undefined {
  return useContext(MerchantIdContext);
}
