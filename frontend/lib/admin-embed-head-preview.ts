/**
 * Xem trước đoạn HTML head mà backend d expansion từ «chỉ mã» — khớp site_embed_templates (ga4 / ads / gtm).
 * Chỉ dùng admin; không chạy trên public.
 */

export type AdminEmbedRowLike = {
  platform?: string;
  category?: string;
  content?: string;
};

function normAwId(raw: string): string | null {
  const u = raw.trim().toUpperCase().replace(/\s/g, '');
  return /^AW-\d+$/.test(u) ? u : null;
}

function normGa4Id(raw: string): string | null {
  const compact = raw.trim().toUpperCase().replace(/\s+/g, '');
  if (/^G-[A-Z0-9]{4,}$/.test(compact)) return compact;
  const m = compact.match(/\b(G-[A-Z0-9]{4,})\b/);
  return m?.[1] ?? null;
}

function normGtmId(raw: string): string | null {
  const u = raw.trim().toUpperCase();
  return /^GTM-[A-Z0-9]+$/.test(u) ? u : null;
}

/** Trích AW-… nếu admin dán thừa chữ (khớp ý normalize conversion). */
function extractAwToken(content: string): string | null {
  const trimmed = content.trim();
  const direct = normAwId(trimmed);
  if (direct) return direct;
  const m = trimmed.match(/\bAW-\d+\b/i);
  return m ? m[0].toUpperCase() : null;
}

function gtagSnippet(id: string): string {
  return `<script async src="https://www.googletagmanager.com/gtag/js?id=${id}"></script>
<script>
window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('js', new Date());
gtag('config', '${id}');
</script>`;
}

function normalizeGoogleCategory(raw: string): string {
  const x = raw.toLowerCase();
  if (['ga-4', 'google_analytics_4', 'google-analytics-4', 'google_analytics4', 'g-analytics'].includes(x)) return 'ga4';
  return x;
}

/**
 * Trả text xem trước hoặc null nếu không có mã hợp lệ / không dựng từ preset.
 */
export function getAdminEmbedHeadPreview(row: AdminEmbedRowLike): string | null {
  const p = (row.platform || '').toLowerCase();
  const c = normalizeGoogleCategory(row.category || '');
  const content = (row.content || '').trim();
  if (!content || p !== 'google') return null;

  if (c === 'ads') {
    const id = extractAwToken(content);
    if (!id) return null;
    return gtagSnippet(id);
  }

  if (c === 'ga4') {
    const id = normGa4Id(content);
    if (!id) return null;
    return gtagSnippet(id);
  }

  if (c === 'gtm') {
    const id = normGtmId(content);
    if (!id) return null;
    return `/* Head — khởi chạy GTM */
<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':
new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],
j=d.createElement(s),dl=l!="dataLayer"?"&l="+l:"";j.async=true;j.src=
"https://www.googletagmanager.com/gtm.js?id="+i+dl;f.parentNode.insertBefore(j,f);
})(window,document,'script','dataLayer','${id}');</script>

/* Đầu body — noscript iframe (tự chèn theo vị trí body_open) */
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=${id}" height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>`;
  }

  return null;
}
