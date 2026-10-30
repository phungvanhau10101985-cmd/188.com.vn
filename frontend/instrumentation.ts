let cachedSecret: string | null = null;

/** Edge/proxy không có `fs`. Chỉ Node đọc file .env; import tĩnh làm hỏng bundle edge. */
function readTextFile(file: string): string | null {
  if (process.env.NEXT_RUNTIME === 'edge') return null;
  try {
    const nodeRequire = (0, eval)('require') as (id: string) => {
      readFileSync: (p: string, enc: 'utf8') => string;
      resolve: (...parts: string[]) => string;
    };
    const fs = nodeRequire('fs');
    const path = nodeRequire('path');
    const resolved = path.resolve(file);
    return fs.readFileSync(resolved, 'utf8');
  } catch {
    return null;
  }
}

function ingestSecret(): string {
  if (cachedSecret !== null) return cachedSecret;
  const fromEnv = (process.env.SITE_ERROR_INGEST_SECRET || process.env.CRON_SECRET || '').trim();
  if (fromEnv) {
    cachedSecret = fromEnv;
    return cachedSecret;
  }
  const candidates = ['../backend/.env', 'backend/.env'];
  for (const file of candidates) {
    const text = readTextFile(file);
    if (!text) continue;
    const match = text.match(/^CRON_SECRET=(.*)$/m);
    if (!match) continue;
    cachedSecret = match[1].trim().replace(/^['"]|['"]$/g, '').replace(/\r$/, '');
    return cachedSecret;
  }
  cachedSecret = '';
  return '';
}

type RequestError = { message?: string; stack?: string; digest?: string };
type RequestInfo = { path?: string; method?: string };

/** Lỗi server Next.js — ghi vào Quản lý lỗi và gửi email admin (tối đa 1 lần/ngày/lỗi). */
export async function onRequestError(err: RequestError, request: RequestInfo) {
  try {
    const reqPath = String(request?.path || '');
    if (reqPath.includes('/site-errors/report')) return;
    const origin = (process.env.API_INTERNAL_ORIGIN || 'http://127.0.0.1:8001').replace(/\/$/, '');
    const secret = ingestSecret();
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (secret) headers['X-Site-Error-Token'] = secret;
    const message = (err?.message || 'Next server error').slice(0, 2000);
    await fetch(`${origin}/api/v1/site-errors/report`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        message,
        stack: (err?.stack || '').slice(0, 8000),
        path: reqPath.slice(0, 500),
        digest: (err?.digest || '').slice(0, 80),
        kind: secret ? 'web_server' : 'web',
      }),
    });
  } catch {
    /* không chặn response lỗi của Next */
  }
}
