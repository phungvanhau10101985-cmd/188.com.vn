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

/**
 * Trích lần lượt mọi &lt;script&gt;…&lt;/script&gt; và phần HTML còn lại (meta, link, …).
 */
function splitOneFragment(fragment: string): { scripts: SsrHeadScriptSpec[]; rest: string } {
  const scripts: SsrHeadScriptSpec[] = [];
  let rest = '';
  let pos = fragment.trim();

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

  for (const raw of fragments) {
    const { scripts, rest } = splitOneFragment(raw);
    ssrScripts.push(...scripts);
    if (rest) headClientRemainders.push(rest);
  }

  return { ssrScripts, headClientRemainders };
}
