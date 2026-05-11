import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

function backendBase(): string {
  return (process.env.API_INTERNAL_ORIGIN || 'http://127.0.0.1:8001').replace(/\/$/, '');
}

/**
 * PDP: nhận { productId, url } từ browser sau onError Next/Image,
 * gọi FastAPI purge khi có BROKEN_MEDIA_PURGE_SECRET (trùng backend).
 */
export async function POST(req: Request): Promise<NextResponse> {
  const secret = process.env.BROKEN_MEDIA_PURGE_SECRET?.trim();
  if (!secret) {
    return NextResponse.json({ ok: false, error: 'purge_disabled' }, { status: 503 });
  }
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false }, { status: 400 });
  }
  const b = body as { productId?: unknown; url?: unknown };
  const pidRaw = b.productId;
  const pid =
    typeof pidRaw === 'number' && Number.isFinite(pidRaw)
      ? pidRaw
      : typeof pidRaw === 'string'
        ? parseInt(pidRaw, 10)
        : NaN;
  const url = typeof b.url === 'string' ? b.url.trim() : '';
  if (!Number.isFinite(pid) || pid < 1 || url.length < 8 || url.length > 2048) {
    return NextResponse.json({ ok: false }, { status: 400 });
  }
  if (!/^https?:\/\//i.test(url)) {
    return NextResponse.json({ ok: false }, { status: 400 });
  }
  const upstream = await fetch(`${backendBase()}/api/v1/products/by-id/${pid}/purge-dead-media-url`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      'X-Broken-Media-Purge-Key': secret,
    },
    body: JSON.stringify({ url }),
  });
  const text = await upstream.text();
  let json: unknown;
  try {
    json = text ? JSON.parse(text) : {};
  } catch {
    json = { raw: text };
  }
  return NextResponse.json(json, { status: upstream.status });
}
