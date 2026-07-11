/**
 * Tách script trong head embed để SSR bằng next/script (beforeInteractive) —
 * HTML từ API/gtag khớp «Xem nguồn» giữa local và server; phần không phải script vẫn chèn trên client.
 */

export type SsrHeadScriptSpec = {
  src?: string;
  async: boolean;
  defer: boolean;
  /** Nội dung inline khi không có src */
  inline?: string;
};

function parseScriptOpenAttrs(attrRaw: string): {
  src?: string;
  async: boolean;
  defer: boolean;
} {
  const attr = (attrRaw || '').trim();
  const srcM = /\bsrc\s*=\s*["']([^"']+)["']/i.exec(attr);
  const async = /\basync\b/i.test(attr);
  const defer = /\bdefer\b/i.test(attr);
  return { src: srcM?.[1], async, defer };
}

function looksLikeInlineJavascript(fragment: string): boolean {
  return /\b(window\.dataLayer|function\s+gtag\s*\(|gtag\s*\(|fbq\s*\(|!function\s*\()/i.test(fragment);
}

function collectGtagConfigIds(fragment: string): string[] {
  const ids: string[] = [];
  const re = /gtag\s*\(\s*['"]config['"]\s*,\s*['"]((?:G|AW)-[A-Z0-9]+)['"]/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(fragment)) !== null) {
    const id = m[1]?.toUpperCase();
    if (id && !ids.includes(id)) ids.push(id);
  }
  return ids;
}

function gtagLoaderId(src: string): string | null {
  const m = /googletagmanager\.com\/gtag\/js\?[^"']*\bid=((?:G|AW)-[A-Z0-9]+)/i.exec(src);
  return m?.[1]?.toUpperCase() ?? null;
}

function normalizeInlineJs(s: string): string {
  return (s || '').replace(/\s+/g, ' ').trim();
}

function extractFbPixelIdFromInline(s: string): string | null {
  const m = /fbq\s*\(\s*['"]init['"]\s*,\s*['"]?(\d{8,})['"]?/i.exec(s || '');
  return m?.[1] ?? null;
}

function scriptDedupeKey(s: SsrHeadScriptSpec): string {
  if (s.src) return `src:${s.src.toLowerCase()}`;
  const inline = normalizeInlineJs(s.inline || '');
  const pixelId = extractFbPixelIdFromInline(inline);
  if (pixelId) return `fbq-init:${pixelId}`;
  return `inline:${inline}`;
}

/**
 * Trích lần lượt mọi &lt;script&gt;…&lt;/script&gt; và phần HTML còn lại (meta, link, …).
 */
function splitOneFragment(fragment: string): { scripts: SsrHeadScriptSpec[]; rest: string } {
  const scripts: SsrHeadScriptSpec[] = [];
  let rest = '';
  let pos = fragment.trim();

  if (pos && !/<[a-z][\s\S]*>/i.test(pos) && looksLikeInlineJavascript(pos)) {
    return { scripts: [{ async: false, defer: false, inline: pos }], rest: '' };
  }

  while (pos.length) {
    const m = pos.match(/^<script(\s[^>]*)?>([\s\S]*?)<\/script>/i);
    if (m) {
      const attrPart = (m[1] || '').trim();
      const body = m[2] ?? '';
      const { src, async, defer } = parseScriptOpenAttrs(attrPart);
      if (src) {
        scripts.push({ src, async, defer });
      } else if (body.trim()) {
        scripts.push({ async, defer, inline: body });
      }
      pos = pos.slice(m[0].length).trimStart();
      continue;
    }
    const idx = pos.search(/<script\b/i);
    if (idx === -1) {
      rest += pos;
      break;
    }
    rest += pos.slice(0, idx);
    pos = pos.slice(idx).trimStart();
  }

  return { scripts, rest: rest.trim() };
}

export type PartitionedHeadEmbeds = {
  ssrScripts: SsrHeadScriptSpec[];
  /** Theo thứ tự: chỉ những đoạn còn lại sau khi gỡ script (meta, link, …) — chèn trên client */
  headClientRemainders: string[];
};

export function partitionHeadEmbedsForSsr(fragments: string[]): PartitionedHeadEmbeds {
  const ssrScripts: SsrHeadScriptSpec[] = [];
  const headClientRemainders: string[] = [];
  const gtagConfigIds: string[] = [];
  const seenScriptKeys = new Set<string>();

  for (const raw of fragments) {
    const { scripts, rest } = splitOneFragment(raw);
    for (const script of scripts) {
      const key = scriptDedupeKey(script);
      if (!seenScriptKeys.has(key)) {
        ssrScripts.push(script);
        seenScriptKeys.add(key);
      }
      if (script.inline) {
        for (const id of collectGtagConfigIds(script.inline)) {
          if (!gtagConfigIds.includes(id)) gtagConfigIds.push(id);
        }
      }
    }
    if (rest) headClientRemainders.push(rest);
  }

  const loadedGtagIds = new Set(
    ssrScripts
      .map((s) => (s.src ? gtagLoaderId(s.src) : null))
      .filter((id): id is string => Boolean(id))
  );
  const missingGtagLoaders = gtagConfigIds
    .filter((id) => !loadedGtagIds.has(id))
    .map((id) => ({
      src: `https://www.googletagmanager.com/gtag/js?id=${id}`,
      async: true,
      defer: false,
    }));
  if (missingGtagLoaders.length) {
    const prepend: SsrHeadScriptSpec[] = [];
    for (const s of missingGtagLoaders) {
      const key = scriptDedupeKey(s);
      if (seenScriptKeys.has(key)) continue;
      prepend.push(s);
      seenScriptKeys.add(key);
    }
    if (prepend.length) ssrScripts.unshift(...prepend);
  }

  return { ssrScripts, headClientRemainders };
}
