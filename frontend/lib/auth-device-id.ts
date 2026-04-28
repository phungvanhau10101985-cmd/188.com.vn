const STORAGE_KEY = '188_auth_device_id';

let memoryFallbackId: string | null = null;

function pickId(): string {
  return typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `d-${Date.now()}-${Math.random().toString(36).slice(2, 15)}`;
}

/**
 * localStorage ghi được và đọc lại — cần cho “tin cậy thiết bị” lâu dài.
 * Safari ẩn danh / một số chế độ chặn sẽ trả false.
 */
export function canPersistTrustedDevice(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    const k = '__188_ls_trust_test__';
    localStorage.setItem(k, '1');
    const ok = localStorage.getItem(k) === '1';
    localStorage.removeItem(k);
    return ok;
  } catch {
    return false;
  }
}

/**
 * Mã thiết bị ổn định trong phiên: ưu tiên localStorage → sessionStorage → bộ nhớ tab.
 */
export function getOrCreateDeviceId(): string {
  if (typeof window === 'undefined') return '';
  try {
    let id = localStorage.getItem(STORAGE_KEY);
    if (!id || id.length < 8) {
      id = pickId();
      localStorage.setItem(STORAGE_KEY, id);
    }
    return id;
  } catch {
    try {
      let id = sessionStorage.getItem(STORAGE_KEY);
      if (!id || id.length < 8) {
        id = pickId();
        sessionStorage.setItem(STORAGE_KEY, id);
      }
      return id;
    } catch {
      if (!memoryFallbackId || memoryFallbackId.length < 8) {
        memoryFallbackId = pickId();
      }
      return memoryFallbackId;
    }
  }
}
