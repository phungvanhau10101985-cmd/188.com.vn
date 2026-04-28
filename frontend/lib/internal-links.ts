/**
 * Internal link map và linkify cho đoạn SEO body.
 * Dùng để chèn link nội bộ vào từ khóa danh mục (chỉ 1 lần/cụm, ưu tiên cụm dài).
 */

import type { CategoryLevel1, CategoryLevel2, CategoryLevel3 } from "@/types/api";

function getSlug(node: { slug?: string; name: string }): string {
  if (node.slug && node.slug.trim()) return node.slug.trim();
  return node.name.trim().toLowerCase().replace(/\s+/g, "-");
}

export interface InternalLinkItem {
  anchor: string;
  url: string;
}

/**
 * Xây dựng danh sách internal link (anchor → url) từ cây danh mục.
 * Chỉ lấy anh/chị em cùng cấp (siblings), bỏ trang hiện tại.
 * Sắp xếp anchor dài trước để thay "giày tây nam" trước "giày tây".
 */
export function buildInternalLinkMap(
  tree: CategoryLevel1[],
  pathSegments: string[]
): InternalLinkItem[] {
  const [level1Slug, level2Slug, level3Slug] = pathSegments;
  const out: InternalLinkItem[] = [];
  const norm = (s: string) => (s || "").trim().toLowerCase();

  if (!level1Slug || !tree.length) return out;

  const l1 = tree.find((c) => norm(getSlug(c)) === norm(level1Slug));
  if (!l1) return out;

  const base1 = `/danh-muc/${encodeURIComponent(level1Slug)}`;

  // Trang cấp 1: link tới các cấp 1 khác
  if (!level2Slug) {
    tree.forEach((c) => {
      if (norm(getSlug(c)) === norm(level1Slug)) return;
      out.push({
        anchor: c.name,
        url: `/danh-muc/${encodeURIComponent(getSlug(c))}`,
      });
    });
    return out.sort((a, b) => b.anchor.length - a.anchor.length);
  }

  const l2 = (l1.children as CategoryLevel2[]).find(
    (c) => norm(getSlug(c)) === norm(level2Slug)
  );
  if (!l2) return out;

  const base2 = `${base1}/${encodeURIComponent(level2Slug)}`;

  // Trang cấp 2: link tới các cấp 2 cùng cha (level1)
  if (!level3Slug) {
    (l1.children as CategoryLevel2[]).forEach((c) => {
      if (norm(getSlug(c)) === norm(level2Slug)) return;
      out.push({
        anchor: c.name,
        url: `${base1}/${encodeURIComponent(getSlug(c))}`,
      });
    });
    return out.sort((a, b) => b.anchor.length - a.anchor.length);
  }

  // Trang cấp 3: link tới các cấp 3 cùng cha (level2)
  const l3List = (l2.children as CategoryLevel3[]) || [];
  l3List.forEach((c) => {
    if (norm(getSlug(c)) === norm(level3Slug)) return;
    out.push({
      anchor: c.name,
      url: `${base2}/${encodeURIComponent(getSlug(c))}`,
    });
  });

  return out.sort((a, b) => b.anchor.length - a.anchor.length);
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * Tìm vị trí xuất hiện đầu tiên của anchor trong text (không phân biệt hoa thường).
 * Trả về [index, matchedSubstring] hoặc null.
 */
function findFirstMatchIgnoreCase(text: string, anchor: string): [number, string] | null {
  if (!anchor) return null;
  const lower = text.toLowerCase();
  const anchorLower = anchor.toLowerCase();
  const idx = lower.indexOf(anchorLower);
  if (idx === -1) return null;
  const matched = text.slice(idx, idx + anchor.length);
  return [idx, matched];
}

/**
 * Chèn internal link vào đoạn seoBody: mỗi anchor chỉ thay lần đầu.
 * So khớp không phân biệt hoa thường (để "Giày tây Nam" trong cây vẫn match "giày tây nam" trong đoạn).
 * Trả về HTML an toàn (đã escape), dùng với dangerouslySetInnerHTML.
 */
export function linkifySeoBody(
  seoBody: string,
  linkMap: InternalLinkItem[]
): string {
  if (!linkMap.length) return escapeHtml(seoBody);

  let text = seoBody;
  const placeholders: { ph: string; url: string; anchor: string }[] = [];

  for (const { anchor, url } of linkMap) {
    if (!anchor) continue;
    const found = findFirstMatchIgnoreCase(text, anchor);
    if (!found) continue;
    const [idx, matchedText] = found;
    const ph = `__IL__${placeholders.length}__`;
    placeholders.push({ ph, url, anchor: matchedText });
    text = text.slice(0, idx) + ph + text.slice(idx + matchedText.length);
  }

  let html = escapeHtml(text);
  for (const { ph, url, anchor } of placeholders) {
    const safeUrl = escapeHtml(url);
    const safeAnchor = escapeHtml(anchor);
    html = html.replace(ph, `<a href="${safeUrl}" class="text-[#ea580c] hover:underline font-medium">${safeAnchor}</a>`);
  }

  return html;
}
