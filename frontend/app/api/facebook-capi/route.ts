import type { NextRequest } from 'next/server';
import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

type Body = {
  event_name?: string;
  event_id?: string;
  event_time?: number;
  action_source?: string;
  event_source_url?: string;
  custom_data?: Record<string, unknown>;
  user_data?: Record<string, unknown>;
};

function backendOrigin(): string {
  return (process.env.API_INTERNAL_ORIGIN || 'http://127.0.0.1:8001').replace(/\/$/, '');
}

function firstHop(raw: string | null): string {
  if (!raw) return '';
  return raw.split(',')[0]?.trim() || '';
}

/** IPv6 thật (không tính ::ffff:x.x.x.x — đó là IPv4 ánh xạ). */
function isIpv6(ip: string): boolean {
  const t = ip.replace(/^\[|\]$/g, '');
  return t.includes(':') && !t.toLowerCase().startsWith('::ffff:');
}

/**
 * Meta chấm EMQ ViewContent thấp nếu chỉ có IPv4 trong khi khách vào bằng IPv6.
 * CF-Connecting-IP là IP khách (kể cả IPv6). X-Real-IP phía nginx thường là IPv4 của proxy.
 */
function clientIpForMeta(req: NextRequest): string {
  const strip = (ip: string) => ip.trim().replace(/^\[|\]$/g, '');
  const cf = strip(req.headers.get('cf-connecting-ip') || '');
  if (cf) return cf;
  const xff = strip(firstHop(req.headers.get('x-forwarded-for')));
  const real = strip(req.headers.get('x-real-ip') || '');
  if (isIpv6(xff)) return xff;
  if (isIpv6(real)) return real;
  return xff || real || '';
}

export async function POST(req: NextRequest) {
  const secret = (process.env.FACEBOOK_CAPI_INGEST_SECRET || '').trim();
  if (!secret) {
    if (process.env.NODE_ENV !== 'production') {
      return new NextResponse(null, { status: 204 });
    }
    return NextResponse.json(
      { ok: false, detail: 'FACEBOOK_CAPI_INGEST_SECRET chưa cấu hình trên server Next.js.' },
      { status: 503 }
    );
  }

  let body: Body;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, detail: 'JSON không hợp lệ' }, { status: 400 });
  }

  const event_name = String(body.event_name ?? '').trim();
  if (!event_name) {
    return NextResponse.json({ ok: false, detail: 'Thiếu event_name' }, { status: 400 });
  }

  const userData: Record<string, unknown> = {
    ...(body.user_data && typeof body.user_data === 'object' ? body.user_data : {}),
  };
  if (typeof userData.fbc === 'string' && !userData.fbc.trim()) {
    delete userData.fbc;
  }

  const ip = clientIpForMeta(req);
  if (ip && userData.client_ip_address == null) {
    userData.client_ip_address = ip;
  }
  const ua = req.headers.get('user-agent') || '';
  if (ua && userData.client_user_agent == null) {
    userData.client_user_agent = ua;
  }

  const payload = {
    event_name,
    event_id: body.event_id,
    event_time: body.event_time,
    action_source: (body.action_source || 'website').trim() || 'website',
    event_source_url: body.event_source_url,
    custom_data: body.custom_data,
    user_data: Object.keys(userData).length ? userData : undefined,
  };

  const url = `${backendOrigin()}/api/v1/embed-codes/facebook/capi/send-event`;
  let upstream: Response;
  const ac = new AbortController();
  const tw = setTimeout(() => ac.abort(), 25_000);
  try {
    upstream = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${secret}`,
      },
      body: JSON.stringify(payload),
      signal: ac.signal,
    });
  } catch (e) {
    return NextResponse.json(
      { ok: false, detail: `Không gọi được backend CAPI: ${e instanceof Error ? e.message : String(e)}` },
      { status: 502 }
    );
  } finally {
    clearTimeout(tw);
  }

  const text = await upstream.text();
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    data = { raw: text.slice(0, 500) };
  }

  return NextResponse.json(data, { status: upstream.status });
}
