import type { NextRequest } from 'next/server';
import { NextResponse } from 'next/server';

/**
 * SePay gọi URL public (vd. https://<ngrok>/api/sepay-webhook).
 * Proxy thẳng tới FastAPI POST /api/v1/sepay/webhook — giữ nguyên body + header xác thực.
 */
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

function forwardRequestHeaders(req: NextRequest, opts?: { omitContentLength?: boolean }): Headers {
  const out = new Headers();
  req.headers.forEach((value, key) => {
    const lk = key.toLowerCase();
    if (HOP_BY_HOP.has(lk)) return;
    if (opts?.omitContentLength && lk === 'content-length') return;
    out.set(key, value);
  });
  return out;
}

function applyResponseHeaders(from: Response, to: NextResponse): void {
  const skip = new Set(['transfer-encoding', 'connection']);
  from.headers.forEach((value, key) => {
    const lk = key.toLowerCase();
    if (skip.has(lk) || lk === 'set-cookie') return;
    to.headers.set(key, value);
  });
}

export async function POST(req: NextRequest): Promise<NextResponse> {
  const url = `${backendBase()}/api/v1/sepay/webhook`;
  const body = await req.arrayBuffer();
  const headers = forwardRequestHeaders(req, { omitContentLength: true });

  let upstream: Response;
  try {
    upstream = await fetch(url, {
      method: 'POST',
      headers,
      body,
      redirect: 'manual',
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'fetch failed';
    return NextResponse.json(
      { success: false, message: `backend_unreachable: ${msg}` },
      { status: 502 }
    );
  }

  const bodyBuf = await upstream.arrayBuffer();
  const res = new NextResponse(bodyBuf, {
    status: upstream.status,
    statusText: upstream.statusText,
  });
  applyResponseHeaders(upstream, res);
  return res;
}
