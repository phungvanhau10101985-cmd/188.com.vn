import { isInAppBrowser } from '@/lib/in-app-browser';

export type SaveImageResult = 'download' | 'share' | 'manual';

/** Thử share file (mobile) hoặc download — trả `manual` nếu cần nhấn giữ ảnh. */
export async function saveImageBlob(
  blob: Blob,
  filename: string,
  opts?: { shareTitle?: string },
): Promise<SaveImageResult> {
  const type = blob.type || 'image/png';
  const title = opts?.shareTitle || 'Mã QR chuyển khoản';

  if (typeof navigator !== 'undefined' && typeof File !== 'undefined' && navigator.share) {
    try {
      const file = new File([blob], filename, { type });
      const payload = { files: [file], title };
      if (!navigator.canShare || navigator.canShare(payload)) {
        await navigator.share(payload);
        return 'share';
      }
    } catch (e) {
      if ((e as Error)?.name === 'AbortError') throw e;
    }
  }

  if (!isInAppBrowser() && typeof document !== 'undefined') {
    const objectUrl = URL.createObjectURL(blob);
    try {
      const a = document.createElement('a');
      a.href = objectUrl;
      a.download = filename;
      a.rel = 'noopener';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      return 'download';
    } finally {
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1500);
    }
  }

  return 'manual';
}
