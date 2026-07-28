import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

/**
 * Khi URL có ?pv2= (chiết khấu tự động Google Shopping), không cache HTML
 * để crawler/khách luôn nhận bản có giá chiết khấu từ SSR.
 */
export function middleware(request: NextRequest) {
  if (!request.nextUrl.searchParams.has('pv2')) {
    return NextResponse.next();
  }
  const res = NextResponse.next();
  res.headers.set('Cache-Control', 'private, no-store');
  return res;
}

export const config = {
  matcher: '/products/:path*',
};
