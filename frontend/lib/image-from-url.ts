import { getApiBaseUrl, ngrokFetchHeaders } from '@/lib/api-base';

/** Kiểm tra chuỗi có phải URL http(s) có vẻ hợp lệ (dùng cho dán link ảnh). */
export function looksLikeHttpUrl(text: string): boolean {
  return /^https?:\/\/.+/i.test(text.trim());
}

/** Tải ảnh qua backend (tránh CORS khi dán link CDN bên ngoài). */
export async function imageUrlToFile(url: string): Promise<File> {
  const trimmed = url.trim();
  const u = new URL(trimmed);
  if (u.protocol !== 'http:' && u.protocol !== 'https:') {
    throw new Error('Chỉ hỗ trợ link http hoặc https.');
  }

  const res = await fetch(`${getApiBaseUrl()}/nanoai/fetch-image`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...ngrokFetchHeaders(),
    },
    body: JSON.stringify({ url: trimmed }),
    credentials: 'include',
  });

  if (!res.ok) {
    let msg = 'Không tải được ảnh từ link.';
    try {
      const data = (await res.json()) as { detail?: unknown; error?: string };
      const detail = data.detail;
      if (typeof detail === 'string' && detail.trim()) msg = detail;
      else if (typeof data.error === 'string' && data.error.trim()) msg = data.error;
    } catch {
      /* giữ msg mặc định */
    }
    throw new Error(msg);
  }

  const blob = await res.blob();
  if (!blob.type.startsWith('image/')) {
    throw new Error('Link không trỏ tới file ảnh (JPEG, PNG, …).');
  }
  const sub = blob.type.split('/')[1]?.replace(/[^a-z0-9]/gi, '') || 'jpg';
  const ext = sub === 'jpeg' ? 'jpg' : sub;
  return new File([blob], `anh-tu-link.${ext}`, { type: blob.type });
}
