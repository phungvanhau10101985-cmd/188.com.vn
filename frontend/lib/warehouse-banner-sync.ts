export const WAREHOUSE_BANNER_SYNC_EVENT = '188-warehouse-banners-changed';

export function notifyWarehouseBannersChanged() {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(WAREHOUSE_BANNER_SYNC_EVENT));
}
