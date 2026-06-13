/**
 * Chuẩn hóa lỗi từ NanoAI image-search (proxy → partner → Gemini embed).
 * Lỗi dạng "Gemini embed failed (500): ... INTERNAL" là phía Google/NanoAI, không phải bug 188.
 */
export function humanizeNanoaiImageSearchError(raw: string | null | undefined): string {
  if (!raw || !String(raw).trim()) return '';
  const t = String(raw).trim();
  if (
    /<!doctype\s+html/i.test(t) ||
    /<html[\s>]/i.test(t) ||
    /cloudflare/i.test(t) ||
    /cf-browser-verification/i.test(t)
  ) {
    return 'Dịch vụ nhận diện ảnh NanoAI tạm thời không phản hồi. Vui lòng thử lại sau vài phút, thử ảnh khác hoặc dùng Tìm theo chữ.';
  }
  if (
    /gemini embed failed/i.test(t) ||
    /internal error encountered/i.test(t) ||
    /"status"\s*:\s*"INTERNAL"/i.test(t)
  ) {
    return 'Dịch vụ nhận diện ảnh tạm báo lỗi (phía NanoAI/Google Gemini). Vui lòng thử lại sau vài giây, thử ảnh nhỏ hơn/png-jpg khác hoặc dùng Tìm theo chữ.';
  }
  return t.length > 320 ? `${t.slice(0, 320)}…` : t;
}

export function shouldRetryNanoaiGeminiTransient(error: string | null | undefined): boolean {
  if (!error || !String(error).trim()) return false;
  const s = String(error);
  return (
    /gemini embed failed/i.test(s) ||
    /internal error encountered/i.test(s) ||
    /"status"\s*:\s*"INTERNAL"/i.test(s)
  );
}
