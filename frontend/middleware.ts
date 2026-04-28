/**
 * Middleware: redirect 301 cho danh mục trùng ý định tìm kiếm (SEO).
 * Gọi API backend để kiểm tra path có cần redirect về trang canonical không.
 * Google/bot nhận 301 ngay từ server → không index URL trùng.
 */
/**
 * Dùng đường cụ thể thay vì next/server vì một số phiên bản/webpack resolve
 * next/dist/server/web/exports/next-response (không có file) → Module not found.
 */
import type { NextRequest } from "next/dist/server/web/spec-extension/request";
import { NextResponse } from "next/dist/server/web/spec-extension/response";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001/api/v1";

const CANON_HOST = "188.com.vn";

export async function middleware(request: NextRequest) {
  const host = request.headers.get("host")?.split(":")[0]?.toLowerCase();
  // Một canonical (apex): tránh xen kẽ www và apex làm fetch RSC bị CORS giữa hai origin.
  if (host === "www.188.com.vn") {
    const dest = request.nextUrl.clone();
    dest.hostname = CANON_HOST;
    return NextResponse.redirect(dest, 308);
  }

  const pathname = request.nextUrl.pathname;

  // Chỉ xử lý /danh-muc/xxx (có ít nhất 1 segment)
  if (!pathname.startsWith("/danh-muc/")) return NextResponse.next();
  const rest = pathname.slice("/danh-muc/".length).trim();
  if (!rest) return NextResponse.next();

  const checkUrl = `${API_BASE}/category-seo/check-redirect?path=${encodeURIComponent(rest)}`;
  try {
    const res = await fetch(checkUrl, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      next: { revalidate: 60 },
      signal: AbortSignal.timeout(8000),
    });
    const data = res.ok
      ? (await res.json()) as { should_redirect?: boolean; redirect_to?: string | null }
      : { should_redirect: false };
    if (data?.should_redirect && data?.redirect_to) {
      const dest = new URL(data.redirect_to, request.nextUrl.origin);
      return NextResponse.redirect(dest, 301);
    }
  } catch {
    // API lỗi: không redirect, để trang load bình thường (client sẽ check lại)
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
};
