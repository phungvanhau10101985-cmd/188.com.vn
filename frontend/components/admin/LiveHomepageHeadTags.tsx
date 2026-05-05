'use client';

import { useEffect, useState } from 'react';

function homepageBaseUrl(): string {
  if (typeof window === 'undefined') return '';
  const fromEnv = process.env.NEXT_PUBLIC_SITE_URL?.trim().replace(/\/$/, '');
  if (fromEnv && /^https?:\/\//i.test(fromEnv)) return fromEnv;
  return window.location.origin;
}

/**
 * Đọc HTML trang chủ (SSR) và trích &lt;script&gt; trong &lt;head&gt; có gtag / AW- / GTM để admin đối chiếu với «Xem nguồn».
 * Hữu ích khi DB admin báo «Chưa nhập» nhưng thẻ vẫn có (GTM, cache, môi trường khác).
 */
export function LiveHomepageHeadTags() {
  const [ok, setOk] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  /** Mặc định ẩn khối &lt;script&gt; dài; mở khi cần đối chiếu «Xem nguồn». */
  const [showScripts, setShowScripts] = useState(false);

  useEffect(() => {
    const base = homepageBaseUrl();
    if (!base) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    fetch(`${base}/`, {
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { Accept: 'text/html' },
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.text();
      })
      .then((html) => {
        if (cancelled) return;
        const headM = html.match(/<head[^>]*>([\s\S]*?)<\/head>/i);
        const head = headM?.[1] ?? '';
        const scriptRe = /<script\b[^>]*>[\s\S]*?<\/script>/gi;
        const parts: string[] = [];
        let m: RegExpExecArray | null;
        while ((m = scriptRe.exec(head)) !== null) {
          const block = m[0].trim();
          if (
            /AW-\d+|gtag\s*\(|googletagmanager\.com\/gtag|google_tags_first_party|\/pded\/|GTM-[A-Z0-9]+|G-[A-Z0-9]{4,}/i.test(
              block,
            )
          ) {
            parts.push(block);
          }
        }
        setOk(parts.length ? parts.join('\n\n') : null);
        setErr(null);
      })
      .catch(() => {
        if (!cancelled) {
          setOk(null);
          setErr(
            'Không đọc được HTML trang chủ. Kiểm tra NEXT_PUBLIC_SITE_URL nếu admin và shop khác domain; hoặc mạng chặn.',
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <p className="text-xs text-gray-500 mb-3" aria-live="polite">
        Đang đọc &lt;head&gt; trang chủ ({homepageBaseUrl() || '…'})…
      </p>
    );
  }

  if (err) {
    return (
      <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900" role="status">
        {err}
      </div>
    );
  }

  if (!ok) {
    return (
      <p className="text-xs text-gray-500 mb-3">
        Không thấy script gtag / AW- / GTM trong &lt;head&gt; trang chủ tại{' '}
        <span className="font-mono">{homepageBaseUrl()}</span>.
      </p>
    );
  }

  return (
    <div className="mb-4 rounded-lg border border-emerald-200 bg-white overflow-hidden shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 bg-emerald-50 text-emerald-950 border-b border-emerald-100">
        <p className="text-xs font-medium">
          Thẻ trong &lt;head&gt; trang chủ (đọc tự động từ{' '}
          <span className="font-mono">{homepageBaseUrl()}/</span>
          ) — đối chiếu khi «Xem nguồn trang»
        </p>
        <button
          type="button"
          onClick={() => setShowScripts((v) => !v)}
          className="text-xs text-emerald-800 hover:underline font-medium shrink-0"
          aria-expanded={showScripts}
        >
          {showScripts ? 'Ẩn mã script' : 'Hiện mã script'}
        </button>
      </div>
      {showScripts ? (
        <pre className="text-[11px] px-3 py-2 overflow-x-auto whitespace-pre-wrap font-mono text-slate-800 max-h-96 overflow-y-auto bg-slate-950 text-slate-100">
          {ok}
        </pre>
      ) : (
        <p className="text-[11px] px-3 py-2 text-slate-600 bg-white">
          Đã phát hiện script liên quan trong &lt;head&gt;. Nhấn «Hiện mã script» để xem nội dung đầy đủ.
        </p>
      )}
    </div>
  );
}
