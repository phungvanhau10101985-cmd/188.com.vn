/**
 * Middleware: redirect 301 cho danh mục trùng ý định tìm kiếm (SEO).
 * Gọi API backend để kiểm tra path có cần redirect về trang canonical không.
 * Google/bot nhận 301 ngay từ server → không index URL trùng.
 */
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export async function middleware(request: NextRequest) {
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
  matcher: ["/danh-muc/:path*"],
};
