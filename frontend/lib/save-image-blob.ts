import { isInAppBrowser, isLikelyMobile } from '@/lib/in-app-browser';

export type SaveImageResult = 'download' | 'share' | 'manual';

function isIOSDevice(): boolean {
  if (typeof navigator === 'undefined') return false;
  return /iPhone|iPad|iPod/i.test(navigator.userAgent || '');
}

/** Blob kiểu octet-stream — trình duyệt ít mở preview, ưu tiên tải file. */
export function blobForFileDownload(source: Blob): Blob {
  if (source.type === 'application/octet-stream') return source;
  return new Blob([source], { type: 'application/octet-stream' });
}

/** Hộp thoại «Lưu thành» trên Chrome/Edge desktop — chắc chắn lưu file, không mở ảnh. */
export async function trySaveFilePicker(blob: Blob, filename: string): Promise<boolean> {
  if (typeof window === 'undefined' || !('showSaveFilePicker' in window)) return false;

  try {
    const picker = window as Window &
      typeof globalThis & {
        showSaveFilePicker: (options: {
          suggestedName?: string;
          types?: Array<{ description?: string; accept: Record<string, string[]> }>;
        }) => Promise<FileSystemFileHandle>;
      };

    const handle = await picker.showSaveFilePicker({
      suggestedName: filename,
      types: [{ description: 'PNG', accept: { 'image/png': ['.png'] } }],
    });
    const writable = await handle.createWritable();
    await writable.write(blob);
    await writable.close();
    return true;
  } catch (e) {
    if ((e as Error)?.name === 'AbortError') throw e;
    return false;
  }
}

/** Tải blob ngay trong user gesture — desktop / Android (không iOS in-app). */
export function trySyncBlobDownload(blob: Blob, filename: string): boolean {
  if (typeof document === 'undefined') return false;
  if (isInAppBrowser()) return false;
  if (isIOSDevice()) return false;

  const legacyNav = navigator as Navigator & { msSaveOrOpenBlob?: (b: Blob, name: string) => void };
  const fileBlob = blobForFileDownload(blob);
  if (typeof legacyNav.msSaveOrOpenBlob === 'function') {
    legacyNav.msSaveOrOpenBlob(fileBlob, filename);
    return true;
  }

  const objectUrl = URL.createObjectURL(fileBlob);
  try {
    const a = document.createElement('a');
    a.href = objectUrl;
    a.download = filename;
    a.setAttribute('download', filename);
    a.rel = 'noopener';
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 120_000);
    return true;
  } catch {
    URL.revokeObjectURL(objectUrl);
    return false;
  }
}

async function tryShareImageFile(
  blob: Blob,
  filename: string,
  shareTitle?: string,
): Promise<'share' | null> {
  if (typeof navigator === 'undefined' || typeof File === 'undefined' || !navigator.share) {
    return null;
  }

  const type = blob.type || 'image/png';
  const file = new File([blob], filename, { type });
  const payload: ShareData = { files: [file], title: shareTitle || 'Mã QR chuyển khoản' };

  try {
    if (navigator.canShare && !navigator.canShare(payload)) return null;
    await navigator.share(payload);
    return 'share';
  } catch (e) {
    if ((e as Error)?.name === 'AbortError') throw e;
    return null;
  }
}

/** Chỉ fallback iOS / in-app — desktop/Android xử lý ở caller. */
export async function saveImageBlob(
  blob: Blob,
  filename: string,
  opts?: { shareTitle?: string; preferShareOnMobile?: boolean },
): Promise<SaveImageResult> {
  const title = opts?.shareTitle || 'Mã QR chuyển khoản';

  if (isInAppBrowser()) {
    return 'manual';
  }

  const mobile = isLikelyMobile();
  const ios = isIOSDevice();

  if (trySyncBlobDownload(blob, filename)) {
    return 'download';
  }

  if (ios || (mobile && opts?.preferShareOnMobile)) {
    try {
      const shared = await tryShareImageFile(blob, filename, title);
      if (shared) return 'share';
    } catch (e) {
      if ((e as Error)?.name === 'AbortError') throw e;
    }
  }

  return 'manual';
}
