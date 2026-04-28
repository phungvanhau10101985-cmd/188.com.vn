/** Chuyển ảnh từ header sang trang /tim-theo-anh qua sessionStorage (tránh popup). */

export const NANOAI_PENDING_IMAGE_KEY = 'nanoai_pending_image_v1';

/** Kích hoạt khi đã lưu ảnh pending và đang đứng trên /tim-theo-anh (tránh router.push no-op). */
export const NANOAI_PENDING_IMAGE_EVENT = '188-nanoai-pending-image-ready';

function readFileAsDataURL(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(r.error);
    r.readAsDataURL(file);
  });
}

/** Giảm dung lượng để tránh vượt quota sessionStorage (~5MB). */
export async function fileToCompressedDataUrl(
  file: File,
  maxSide = 1280,
  quality = 0.82
): Promise<string> {
  if (!file.type.startsWith('image/') || file.type === 'image/gif') {
    return readFileAsDataURL(file);
  }
  try {
    const bitmap = await createImageBitmap(file);
    const { width: w, height: h } = bitmap;
    const scale = Math.min(1, maxSide / Math.max(w, h, 1));
    const cw = Math.max(1, Math.round(w * scale));
    const ch = Math.max(1, Math.round(h * scale));
    const canvas = document.createElement('canvas');
    canvas.width = cw;
    canvas.height = ch;
    const ctx = canvas.getContext('2d');
    if (!ctx) return readFileAsDataURL(file);
    ctx.drawImage(bitmap, 0, 0, cw, ch);
    bitmap.close();
    return canvas.toDataURL('image/jpeg', quality);
  } catch {
    return readFileAsDataURL(file);
  }
}

export function dataUrlToFile(dataUrl: string, filename = 'tim-theo-anh.jpg'): File {
  const comma = dataUrl.indexOf(',');
  if (comma < 0) throw new Error('invalid data url');
  const header = dataUrl.slice(0, comma);
  const b64 = dataUrl.slice(comma + 1);
  const mime = header.match(/data:(.*?);/)?.[1] || 'image/jpeg';
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new File([bytes], filename, { type: mime });
}

export async function storePendingImageAndNavigate(
  file: File,
  router: { push: (href: string) => void }
): Promise<void> {
  let dataUrl = await fileToCompressedDataUrl(file);
  try {
    sessionStorage.setItem(NANOAI_PENDING_IMAGE_KEY, dataUrl);
  } catch {
    dataUrl = await fileToCompressedDataUrl(file, 960, 0.75);
    try {
      sessionStorage.setItem(NANOAI_PENDING_IMAGE_KEY, dataUrl);
    } catch {
      dataUrl = await fileToCompressedDataUrl(file, 800, 0.72);
      sessionStorage.setItem(NANOAI_PENDING_IMAGE_KEY, dataUrl);
    }
  }
  if (typeof window !== 'undefined') {
    const p = window.location.pathname;
    if (p === '/tim-theo-anh' || p.startsWith('/tim-theo-anh/')) {
      window.dispatchEvent(new CustomEvent(NANOAI_PENDING_IMAGE_EVENT));
      return;
    }
  }
  router.push('/tim-theo-anh');
}

/** Đọc và xóa khỏi sessionStorage (một lần). */
export function consumePendingImageFile(): File | null {
  if (typeof window === 'undefined') return null;
  const raw = sessionStorage.getItem(NANOAI_PENDING_IMAGE_KEY);
  if (!raw) return null;
  sessionStorage.removeItem(NANOAI_PENDING_IMAGE_KEY);
  try {
    return dataUrlToFile(raw);
  } catch {
    return null;
  }
}
