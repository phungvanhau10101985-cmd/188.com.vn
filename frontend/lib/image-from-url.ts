/** Kiểm tra chuỗi có phải URL http(s) có vẻ hợp lệ (dùng cho dán link ảnh). */
export function looksLikeHttpUrl(text: string): boolean {
  return /^https?:\/\/.+/i.test(text.trim());
}

/** Tải ảnh qua fetch (CORS phụ thuộc máy chủ nguồn). */
export async function imageUrlToFile(url: string): Promise<File> {
  const u = new URL(url.trim());
  if (u.protocol !== 'http:' && u.protocol !== 'https:') {
    throw new Error('Chỉ hỗ trợ link http hoặc https.');
  }
  const res = await fetch(url.trim(), { mode: 'cors' });
  if (!res.ok) throw new Error(`Máy chủ ảnh trả lỗi (${res.status}).`);
  const blob = await res.blob();
  if (!blob.type.startsWith('image/')) {
    throw new Error('Link không trỏ tới file ảnh (JPEG, PNG, …).');
  }
  const sub = blob.type.split('/')[1]?.replace(/[^a-z0-9]/gi, '') || 'jpg';
  const ext = sub === 'jpeg' ? 'jpg' : sub;
  return new File([blob], `anh-tu-link.${ext}`, { type: blob.type });
}
