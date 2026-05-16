/**
 * Kiểm tra nháp Import (product_data) trước khi cho tick đăng từ modal «Sản phẩm đã crawl xong trong đợt».
 * Khớp cấu trúc `excelExportRowFromProductData`: `images` = thư viện, `gallery` = ảnh chi tiết/mô tả.
 */

function trimStr(v: unknown): string {
  if (v == null) return '';
  if (typeof v === 'string') return v.trim();
  if (typeof v === 'number' || typeof v === 'boolean') return String(v).trim();
  return '';
}

function isBlankExcelText(v: unknown): boolean {
  const s = trimStr(v);
  return !s || s.toLowerCase() === 'nan';
}

function hasChineseScript(s: string): boolean {
  return /[\u3400-\u9FFF\uF900-\uFAFF]/.test(s);
}

function countHttpImageUrls(raw: unknown): number {
  if (!Array.isArray(raw)) return 0;
  let n = 0;
  for (const u of raw) {
    if (typeof u === 'string' && /^https?:\/\//i.test(u.trim())) n += 1;
  }
  return n;
}

const APPAREL_SHOE_RES: RegExp[] = [
  /\bgiày\b/i,
  /\bdép\b/i,
  /\bsandal\b/i,
  /\bboots?\b/i,
  /\bsneaker/i,
  /\bquần\b/i,
  /\báo\b/i,
  /\bváy\b/i,
  /\bđầm\b/i,
  /\blót\b/i,
  /\btất\b/i,
  /\bvớ\b/i,
  /鞋/u,
  /靴/u,
  /拖鞋/u,
  /凉鞋/u,
  /运动鞋/u,
  /裤/u,
  /裙/u,
  /上衣/u,
  /衬衫/u,
  /T恤/u,
  /卫衣/u,
  /外套/u,
  /袜/u,
  /\bshoes?\b/i,
  /\bslipper/i,
  /\bsandal/i,
  /\bpants?\b/i,
  /\bjeans\b/i,
  /\bdress\b/i,
  /\bjacket\b/i,
  /\bshirt\b/i,
  /\bshorts\b/i,
];

export function productDataLooksLikeApparelOrFootwear(pd: Record<string, unknown>): boolean {
  const hay = [
    trimStr(pd.name),
    trimStr(pd.chinese_name),
    trimStr(pd.category),
    trimStr(pd.subcategory),
    trimStr(pd.sub_subcategory),
    trimStr(pd.description).slice(0, 600),
  ]
    .join(' ')
    .trim();
  if (!hay) return false;
  return APPAREL_SHOE_RES.some((re) => re.test(hay));
}

function isFreeSizeLabel(s: string): boolean {
  const t = s.trim().toLowerCase();
  if (!t) return false;
  if (/均码|均碼|ㄧ码|統碼/.test(s)) return true;
  if (/\bone[\s_-]?size\b/i.test(t)) return true;
  if (/\bfree[\s_-]?size\b/i.test(t)) return true;
  if (/\bfreesize\b/i.test(t)) return true;
  if (/\bos\b/i.test(t) && t.length <= 12) return true;
  if (/^fs$/i.test(t) || /^os$/i.test(t)) return true;
  if (t.includes('free sz')) return true;
  if (t.includes('đồng size')) return true;
  return false;
}

export function normalizeProductDataSizes(raw: unknown): string[] {
  if (raw == null) return [];
  if (Array.isArray(raw)) {
    return raw.map((x) => trimStr(x)).filter(Boolean);
  }
  if (typeof raw === 'string') {
    const s = raw.trim();
    if (!s) return [];
    try {
      const j = JSON.parse(s) as unknown;
      if (Array.isArray(j)) return j.map((x) => trimStr(x)).filter(Boolean);
    } catch {
      /* pipe / comma lists */
    }
    return s
      .split(/[,;|]/g)
      .map((x) => x.trim())
      .filter(Boolean);
  }
  return [];
}

function sizesMeetApparelFootwearRule(sizes: string[]): boolean {
  if (sizes.length === 0) return false;
  const nonFree = sizes.filter((x) => !isFreeSizeLabel(x));
  if (nonFree.length === 0) return true;
  return nonFree.length >= 3;
}

function validateColorVariants(colorsRaw: unknown): string[] {
  const issues: string[] = [];
  if (!Array.isArray(colorsRaw) || colorsRaw.length === 0) {
    issues.push('Thiếu biến thể màu (mỗi màu cần tên + URL ảnh)');
    return issues;
  }
  for (let i = 0; i < colorsRaw.length; i++) {
    const c = colorsRaw[i];
    if (typeof c !== 'object' || c === null) {
      issues.push(`Màu #${i + 1}: dữ liệu không hợp lệ`);
      continue;
    }
    const rec = c as Record<string, unknown>;
    const name = trimStr(rec.name);
    const img = trimStr(rec.img ?? rec.image_url ?? rec.url);
    if (!name) issues.push(`Màu #${i + 1}: thiếu tên`);
    if (!/^https?:\/\//i.test(img)) issues.push(`Màu «${name || '?'}»: thiếu ảnh (URL http/https)`);
  }
  return issues;
}

/**
 * Danh sách lý do không cho đăng (tiếng Việt). Rỗng = được phép tick (trừ các chặn khác như đã có trong shop).
 */
export function getListingDraftPublishBlockers(pd: Record<string, unknown> | undefined): string[] {
  const issues: string[] = [];
  if (!pd || typeof pd !== 'object') {
    issues.push('Thiếu product_data');
    return issues;
  }

  const cn = trimStr(pd.chinese_name);
  const shopCn = trimStr(pd.shop_name_chinese);
  if (!cn) issues.push('Thiếu tên tiếng Trung');
  else if (!hasChineseScript(cn)) issues.push('Tên tiếng Trung cần có chữ Hán');
  if (!shopCn) issues.push('Thiếu tên shop tiếng Trung');
  else if (!hasChineseScript(shopCn)) issues.push('Tên shop tiếng Trung cần có chữ Hán');

  if (isBlankExcelText(pd.category)) issues.push('Thiếu danh mục cấp 1');
  if (isBlankExcelText(pd.subcategory)) issues.push('Thiếu danh mục cấp 2');
  if (isBlankExcelText(pd.sub_subcategory)) issues.push('Thiếu danh mục cấp 3');

  const lib = countHttpImageUrls(pd.images);
  const detail = countHttpImageUrls(pd.gallery);
  if (detail <= lib) {
    issues.push(`Ảnh chi tiết (${detail}) phải nhiều hơn ảnh thư viện (${lib})`);
  }

  issues.push(...validateColorVariants(pd.colors));

  if (productDataLooksLikeApparelOrFootwear(pd)) {
    const sizes = normalizeProductDataSizes(pd.sizes);
    if (!sizesMeetApparelFootwearRule(sizes)) {
      issues.push('Giày dép / quần áo: cần ít nhất 3 size ghi rõ, hoặc chỉ free size / đồng size');
    }
  }

  return issues;
}

export function isListingDraftPublishReady(pd: Record<string, unknown> | undefined): boolean {
  return getListingDraftPublishBlockers(pd).length === 0;
}
