import type { NextRequest } from 'next/server';
import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

const HOP_BY_HOP = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailers',
  'transfer-encoding',
  'upgrade',
  'host',
]);

function backendBase(): string {
  return (process.env.API_INTERNAL_ORIGIN || 'http://127.0.0.1:8001').replace(/\/$/, '');
}

function targetUrl(req: NextRequest, segments: string[]): string {
  // Bỏ phần rỗng (URL dạng /api/v1/products/ → 308 ở FastAPI khi lặp proxy)
  const segs = segments.filter((s) => s && s.length > 0);
  const path = segs.length ? segs.join('/') : '';
  const suffix = path ? `/api/v1/${path}` : '/api/v1';
  const u = new URL(suffix + req.nextUrl.search, backendBase());
  return u.toString();
}

function forwardRequestHeaders(req: NextRequest, opts?: { omitContentLength?: boolean }): Headers {
  const out = new Headers();
  req.headers.forEach((value, key) => {
    const lk = key.toLowerCase();
    if (HOP_BY_HOP.has(lk)) return;
    if (opts?.omitContentLength && lk === 'content-length') return;
    out.set(key, value);
  });
  // Starlette/FastAPI dựng Location redirect từ Host. Nếu giữ Host ngrok/public, Location trỏ ra tunnel;
  // fetch(..., redirect: 'follow') trên Node đi vòng qua ngrok → lỗi / 502. Luôn dùng host backend nội bộ.
  try {
    const internal = new URL(backendBase());
    out.set('Host', internal.host);
  } catch {
    /* giữ Host đã forward */
  }
  const publicHost = req.headers.get('x-forwarded-host') ?? req.headers.get('host');
  if (publicHost) {
    out.set('X-Forwarded-Host', publicHost);
  }
  return out;
}

function applyResponseHeaders(from: Response, to: NextResponse, extraSkip?: Set<string>): void {
  const skip = new Set(['transfer-encoding', 'connection', ...(extraSkip ?? [])]);
  from.headers.forEach((value, key) => {
    const lk = key.toLowerCase();
    if (skip.has(lk) || lk === 'set-cookie') return;
    to.headers.set(key, value);
  });
  const cookies =
    typeof from.headers.getSetCookie === 'function' ? from.headers.getSetCookie() : [];
  for (const c of cookies) {
    to.headers.append('Set-Cookie', c);
  }
}

async function proxy(req: NextRequest, segments: string[]): Promise<NextResponse> {
  try {
    const url = targetUrl(req, segments);
    const hasBody = req.method !== 'GET' && req.method !== 'HEAD';
    const headers = forwardRequestHeaders(req, { omitContentLength: hasBody });
  // Phải xử lý redirect nội bộ: nếu upstream trả Location `http://127.0.0.1:8001/...`
  // được chuyển nguyên xuống trình duyệt (ngrok/mobile) → client nhảy tới 127.0.0.1 → lỗi & banner "offline".
  // Không follow tại Node (undici hay 502 khi Host bị override trước redirect):
  // Thay vào đó, ta tự rewrite Location về cùng path /api/v1 để client follow.
  const init: RequestInit = {
    method: req.method,
    headers,
    redirect: 'manual',
  };

  if (hasBody) {
    init.body = await req.arrayBuffer();
  }

  // Import Excel ~24MB: Next đệm body rồi forward; undici cần đủ thời gian (mạng chậm / VPS tải cao).
  const contentLen = parseInt(req.headers.get('content-length') || '0', 10);
  const pathSuffix = req.nextUrl.pathname;
  const heavyUpload =
    contentLen > 2 * 1024 * 1024 ||
    (pathSuffix.includes('/import-export/import/excel') && req.method === 'POST');
  const timeoutMs = heavyUpload ? 900_000 : 120_000;

  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), timeoutMs);
  let upstream: Response;
  try {
    upstream = await fetch(url, { ...init, signal: ac.signal });
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'fetch failed';
    return NextResponse.json(
      { detail: `Không kết nối được backend (${backendBase()}): ${msg}. Đảm bảo FastAPI/uvicorn đang chạy tại URL này.` },
      { status: 502 }
    );
  } finally {
    clearTimeout(t);
  }

  // Đệm toàn bộ phản hồi: truyền thẳng upstream.body vào NextResponse dễ gây
  // ReadableStream already closed / disturbed trong Next 14 + Node undici (đặc biệt Fast Refresh).
  const bodyBuf = await upstream.arrayBuffer();
  const upstreamCt = (upstream.headers.get('content-type') || '').toLowerCase();
  const upstreamLooksJson =
    upstreamCt.includes('application/json') ||
    upstreamCt.includes('application/problem+json') ||
    upstreamCt.includes('+json');

  // FastAPI/uvicorn đôi khi trả 500 dạng text "Internal Server Error" → admin parse JSON lỗi.
  if (upstream.status >= 400 && !upstreamLooksJson) {
    const text =
      bodyBuf.byteLength > 0
        ? new TextDecoder('utf-8', { fatal: false }).decode(new Uint8Array(bodyBuf)).trim()
        : '';
    const res = NextResponse.json(
      {
        detail:
          text ||
          `HTTP ${upstream.status} từ backend (${backendBase()}), body rỗng hoặc không phải JSON. Kiểm tra log FastAPI.`,
      },
      { status: upstream.status },
    );
    applyResponseHeaders(upstream, res, new Set(['content-type', 'content-length']));
    res.headers.set('content-type', 'application/json; charset=utf-8');
    return res;
  }

  const res = new NextResponse(bodyBuf, {
    status: upstream.status,
    statusText: upstream.statusText,
  });
  applyResponseHeaders(upstream, res);

  if (upstream.status >= 300 && upstream.status < 400) {
    const loc = upstream.headers.get('location');
    if (loc) {
      try {
        const u = new URL(loc, backendBase());
        // Giữ lại path/query trên cùng origin (không trả ra http://127.0.0.1)
        const rewritten = `${u.pathname}${u.search}`;
        res.headers.set('location', rewritten);
      } catch {
        /* nếu URL không hợp lệ thì giữ nguyên */
      }
    }
  }

  return res;
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json(
      {
        detail: `Lỗi proxy Next.js → backend (${backendBase()}): ${msg}`,
      },
      { status: 502 },
    );
  }
}

type Ctx = { params: Promise<{ path?: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  const params = await ctx.params;
  return proxy(req, params.path ?? []);
}
export async function POST(req: NextRequest, ctx: Ctx) {
  const params = await ctx.params;
  return proxy(req, params.path ?? []);
}
export async function PUT(req: NextRequest, ctx: Ctx) {
  const params = await ctx.params;
  return proxy(req, params.path ?? []);
}
export async function PATCH(req: NextRequest, ctx: Ctx) {
  const params = await ctx.params;
  return proxy(req, params.path ?? []);
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  const params = await ctx.params;
  return proxy(req, params.path ?? []);
}
export async function HEAD(req: NextRequest, ctx: Ctx) {
  const params = await ctx.params;
  return proxy(req, params.path ?? []);
}
export async function OPTIONS(req: NextRequest, ctx: Ctx) {
  const params = await ctx.params;
  return proxy(req, params.path ?? []);
}
