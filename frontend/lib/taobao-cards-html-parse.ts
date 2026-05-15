/**
 * Parse HTML snippet từ trang listing Taobao/Tmall (doubleCardWrapperAdapt, item_id_*) hoặc 1688 selloffer (search-offer-wrapper, detail.m.1688 offerId).
 */

export type ParsedTaobaoCardRow = {
  row: number;
  /**
   * ID sản phẩm: chữ số; hoặc `T`+số khi link có Taobao/Tmall; hoặc `A`+số khi link có 1688.com.
   */
  item_id: string;
  /** Link sản phẩm (https://…), từ href thẻ card */
  item_url: string;
  main_image_url: string;
  title: string;
  /** Tên shop — thường là <span class="shopNameText--…">…</span> */
  shop_name: string;
  /** Tên shop NCC (thường tiếng Trung) — trùng `shop_name` từ listing; cột Excel `shop_name_chinese` sau import. */
  shop_name_chinese: string;
  /** Tên SP tiếng Trung — trùng `title` từ listing; cột Excel `chinese_name`. */
  chinese_name: string;
  /** `appUid` trong URL shop `view_shop.htm`, nếu có */
  shop_app_uid: string;
  /** Wangwang nick — `data-nick` trên `.ww-light` */
  seller_nick: string;
  tags: string;
  price_raw: string;
  /** `href` bọc vùng giá nếu có; không có thì trùng `item_url` khi đã có link SP */
  price_link: string;
  sales_text: string;
  sku_thumb_urls: string;
  sku_thumb_count: number;
  /** Số nhân dân tệ suy từ `price_raw`; null nếu không đọc được. */
  price_cny_approx: number | null;
  /** Hệ số nhân theo lưới IF Excel (theo giá nhân dân tệ). */
  cny_exchange_multiplier: number | null;
  /** Nguồn parse đặc biệt (ảnh/shop có thể thiếu). */
  parsed_source?: 'hibox_grid' | '1688_text_table';
  /** Số nguyên MNT suy từ `price_raw` (nối chữ số); chỉ khi `parsed_source === 'hibox_grid'`. */
  price_hibox_mnt_integer?: number | null;
};

const PLACEHOLDER_OSS_PATH = 'O1CN01CYtPWu1MUBqQAUK9D';

/**
 * Hệ số nhân nhân dân tệ (J5 trong Excel IF) để nhân giá nhân dân tệ — sync backend `listing_cny_grid.cny_exchange_multiplier_from_grid`.
 */
export function cnyExchangeMultiplierFromGrid(cnyPrice: number): number {
  const j = cnyPrice;
  if (!Number.isFinite(j) || j <= 0) return 0;
  if (j <= 90) return 3;
  if (j <= 100) return 2.9;
  if (j <= 120) return 2.8;
  if (j <= 140) return 2.7;
  if (j <= 160) return 2.6;
  if (j <= 180) return 2.6;
  if (j <= 200) return 2.6;
  if (j <= 240) return 2.6;
  if (j <= 280) return 2.6;
  if (j <= 320) return 2.5;
  if (j <= 370) return 2.5;
  if (j <= 400) return 2.5;
  return 2.5;
}

/** Tỷ giá mặc định (VNĐ cho 1 CN¥) khi không nhập / không hợp lệ trong UI và CSV — khớp backend LISTING_IMPORT_VND_PER_CNY (3580). */
export const DEFAULT_VND_PER_CNY_FOR_LISTING_ESTIMATE = 3580;

/**
 * Ước lượng số đơn vị MNT trên 1 CN¥ — quy đổi giá lưới Hibox (`span.currency`) sang «Giá Tệ» / lưới IF.
 * Khớp cách đọc giá MNT trong `import_hibox_scraper._parse_display_price_integer` (nối mọi chữ số).
 * Chỉnh hằng số này nếu ~VNĐ sau quy đổi lệch thực tế (tỷ giá MNT/CNY thay đổi).
 */
export const DEFAULT_MNT_PER_CNY_FOR_HIBOX_LISTING = 475;

/** Bội số VNĐ sau quy đổi (làm tròn lên). Khớp `listing_cny_grid.LISTING_VND_PRICE_CEILING_STEP`. */
export const LISTING_VND_PRICE_CEILING_STEP = 10_000;

/**
 * Giá hiển thị kiểu `78.900` / `78,900 ₮` — lấy số nguyên bằng cách nối mọi chữ số.
 * Khớp `import_hibox_scraper._parse_display_price_integer`.
 */
export function parseHiboxDisplayPriceIntegerMnt(raw: string): number | null {
  const t = String(raw ?? '')
    .normalize('NFKC')
    .replace(/\u00a0/g, '')
    .trim();
  if (!/[0-9]/.test(t)) return null;
  const digits = t.replace(/\D/g, '');
  if (!digits) return null;
  let n = Number.parseInt(digits, 10);
  if (!Number.isFinite(n) || n <= 0) return null;
  const cap = 9_999_999_999;
  if (n > cap) n = cap;
  return n;
}

/** MNT (số nguyên hiển thị) → ~CN¥ cho pipeline lưới IF / cột Giá Tệ. */
export function hiboxMntIntegerToApproxCny(
  mntInteger: number,
  mntPerOneCny: number = DEFAULT_MNT_PER_CNY_FOR_HIBOX_LISTING,
): number | null {
  if (!Number.isFinite(mntInteger) || mntInteger <= 0) return null;
  if (!Number.isFinite(mntPerOneCny) || mntPerOneCny <= 0) return null;
  const cny = mntInteger / mntPerOneCny;
  if (!Number.isFinite(cny) || cny <= 0) return null;
  return cny;
}

/**
 * Gắn cột «Shop Trung Quốc» (`shop_name_chinese`) và «Tên tiếng trung» (`chinese_name`)
 * — đồng bộ với nháp/Excel sau import — từ `shop_name` và `title` đã parse từ listing.
 */
export function withListingCnExportFields(r: ParsedTaobaoCardRow): ParsedTaobaoCardRow {
  const shop = (r.shop_name || '').trim();
  const tit = (r.title || '').trim();
  return {
    ...r,
    shop_name_chinese: shop,
    chinese_name: tit,
  };
}

function withListingCnExportRows(rows: ParsedTaobaoCardRow[]): ParsedTaobaoCardRow[] {
  return rows.map(withListingCnExportFields);
}

/**
 * Áp tỷ giá ₮/CN¥ để ghi đè `price_cny_approx` và `cny_exchange_multiplier` cho dòng lưới Hibox.
 */
export function applyHiboxMntRateToRow(
  r: ParsedTaobaoCardRow,
  mntPerOneCny: number,
): ParsedTaobaoCardRow {
  if (r.parsed_source !== 'hibox_grid' || r.price_hibox_mnt_integer == null) {
    return r;
  }
  const rate =
    typeof mntPerOneCny === 'number' && Number.isFinite(mntPerOneCny) && mntPerOneCny > 0
      ? mntPerOneCny
      : DEFAULT_MNT_PER_CNY_FOR_HIBOX_LISTING;
  const cny = hiboxMntIntegerToApproxCny(r.price_hibox_mnt_integer, rate);
  if (cny == null) {
    return { ...r, price_cny_approx: null, cny_exchange_multiplier: null };
  }
  const coef = cnyExchangeMultiplierFromGrid(cny);
  return { ...r, price_cny_approx: cny, cny_exchange_multiplier: coef };
}

/**
 * Lấy giá nhân dân tệ (~CN¥) từ text giá trong listing — NFKC / ký hiệu ¥ / thập phân / số nguyên.
 */
export function parseApproxCnyAmountFromPriceRaw(raw: string): number | null {
  const flat = String(raw ?? '')
    .normalize('NFKC')
    .replace(/\u00a0/g, '')
    .trim();
  if (!/[0-9]/.test(flat)) return null;

  const canon = flat.replace(/\s+/g, '').replace(/¥|￥|元/gi, '');
  const trimmed = canon.replace(/^[^\d]+/, '');
  if (!/[0-9]/.test(trimmed)) return null;

  /** Ưu tiên phần thập phân dạng 118.00 hoặc 118,88 */
  const decimalTok = trimmed.match(/^(\d{1,11}[.,]\d{1,7})(?!\d)/)?.[1];
  const tokenStr = decimalTok ?? trimmed.match(/^(\d{1,11})/)?.[1];
  if (!tokenStr) return null;

  let token = tokenStr.replace(',', '.').replace(/^0+(\d)/, '$1');
  /** Nếu còn nhiều . coi là phân cách nghìn kiểu 11.398.113 — gộp rồi chỉ giữ lần chấm cuối là thập phân không khả thi đơn giản → bỏ hết . */
  if ((token.match(/\./g) || []).length > 1) {
    token = token.replace(/\./g, '');
  }
  const n = Number.parseFloat(token);
  if (!Number.isFinite(n) || n <= 0 || n > 999_999_999) return null;
  return n;
}

/**
 * ~VNĐ = CN¥ × hệ_số_lưới × tỷ_giá, `Math.round` về nguyên, rồi làm tròn **lên** bội `LISTING_VND_PRICE_CEILING_STEP`.
 */
export function estimateListingVndRounded(
  row: Pick<ParsedTaobaoCardRow, 'price_cny_approx' | 'cny_exchange_multiplier'>,
  vndPerOneCny: number,
): number | null {
  const cny = row.price_cny_approx;
  const coef = row.cny_exchange_multiplier;
  if (
    cny == null ||
    coef == null ||
    coef <= 0 ||
    !Number.isFinite(vndPerOneCny) ||
    vndPerOneCny <= 0
  )
    return null;
  const rounded = Math.round(cny * coef * vndPerOneCny);
  const step = LISTING_VND_PRICE_CEILING_STEP;
  return Math.ceil(rounded / step) * step;
}

function extractTitle(titleEl: Element | null): string {
  if (!titleEl) return '';
  const clone = titleEl.cloneNode(true) as HTMLElement;
  clone.querySelectorAll('img,svg,video').forEach((n) => n.remove());
  return (clone.textContent || '').replace(/\s+/g, ' ').trim();
}

function uniquePush(urls: string[], u: string) {
  const t = u.trim();
  if (!t) return;
  if (!urls.includes(t)) urls.push(t);
}

/** Ảnh placeholder 2×2 — thường không phải ảnh biến thể thật */
export function stripPlaceholderSkuImages(urls: string[]): string[] {
  return urls.filter((u) => !u.includes(PLACEHOLDER_OSS_PATH));
}

function titleSelectorWithin(card: Element): Element | null {
  let titleEl =
    card.querySelector('.offer-title-row .title-text') ||
    card.querySelector('[class*="offer-title-row"] [class*="title-text"]') ||
    /** 1688: đôi khi copy DOM thiếu `offer-title-row`, chỉ còn `title-text`. */
    (card.matches?.('[class*="search-offer-wrapper"], [class*="search-offer-item"]')
      ? card.querySelector('[class*="title-text"]')
      : null) ||
    card.querySelector(
      '[class*="search-offer-wrapper"] [class*="title-text"], [class*="search-offer-item"] [class*="title-text"]',
    ) ||
    card.querySelector('[class*="title--"]') ||
    card.querySelector('[class*="Title--"]') ||
    card.querySelector('[class*="itemTitle"], [class*="ItemTitle"], [class*="goodsTitle"], [class*="GoodsTitle"]') ||
    card.querySelector('[data-spm-d*="title"]') ||
    card.querySelector('[class*="descContainer"] [class*="title"]');
  if (!titleEl) {
    const desc =
      card.querySelector(
        '[class*="descContainer"], [class*="DescContainer"], [class*="descRow"], [class*="descBox"], [class*="desc--"], [class*="descWrapper--"]',
      );
    if (desc) {
      titleEl = desc.querySelector('[class*="title"]');
    }
  }
  if (!titleEl && card.matches?.('[class*="title-text"]')) titleEl = card;
  return titleEl;
}

/** Khi tên tiếng Trung (1688/extension) dán thành «chính chủ + chính chủ» dính liền. */
function dedupeRepeatedCnProductTitle(raw: string): string {
  const s = raw.replace(/\s+/g, ' ').trim();
  if (s.length < 20 || s.length % 2 !== 0) return s;
  const mid = s.length / 2;
  if (s.slice(0, mid) === s.slice(mid)) return s.slice(0, mid).trim();
  return s;
}

/**
 * `offer-title-row` chỉ có hậu tố `…">`, thiếu `<div`; `class title-text` không có `=`.
 * Xảy ra khi DevTools/extension copy outerHTML không đầy đủ hoặc dán qua chỗ chỉnh sửa.
 */
function patchBroken1688ListingPaste(html: string): string {
  if (!/(?:offer-title-row|title-text|search-offer-wrapper|detail\.m\.1688|\b1688\.com\b)/i.test(html)) {
    return html;
  }
  let s = html;
  s = s.replace(/(^|[\s>])(offer-title-row)\s*">\s*/gim, '$1<div class="$2">');
  s = s.replace(/<div\s+class\s+(title-text|offer-title-row)\b([\s>/])/gi, '<div class="$1"$2');
  return s;
}

/** Fallback khi bọc `.title-text` chỉ còn ô `<div>tên SP</div>` (DOM lỗi / thẻ anh em rác như «class teen…»). */
function extract1688TitleLooseFallback(scope: Element): string {
  const d =
    scope.querySelector('[class*="title-text"] > div:last-of-type') ||
    scope.querySelector('[class*="title-text"] > div:first-of-type') ||
    scope.querySelector('[class*="title-text"] div') ||
    scope.querySelector('[class*="offer-title-row"] [class*="title-text"] div');
  return extractTitle(d);
}

/** 1688 selloffer: giá hiển thị dòng khối (113), không ghép các tier trong offer-hover-wrapper. */
function extract1688OfferListPrice(card: Element): string {
  const row = card.querySelector('[class*="offer-price-row"]');
  if (!row) return '';
  const mainEl =
    row.querySelector(':scope > .col-desc .price-item > .text-main') ||
    row.querySelector(':scope .col-desc .price-item > .text-main') ||
    row.querySelector(':scope .price-item:first-of-type > .text-main') ||
    row.querySelector(':scope > .col-desc .text-main');
  const main = (mainEl?.textContent || '').replace(/\s+/g, '').trim();
  const priceItem = mainEl?.closest('.price-item, [class*="price-item"]');
  const units = (
    priceItem?.querySelector('.price-units, [class*="price-units"]')?.textContent || ''
  )
    .replace(/\s+/g, '')
    .trim();
  if (!main && !units) return '';
  return `${units}${main || ''}` || '';
}

function normalize1688CategoryBreadcrumb(raw: string): string {
  const t = raw.replace(/\s+/g, ' ').trim();
  if (!t || t.length < 3) return '';
  if (!/>|＞|&gt;/.test(t) && !/\s[·•]\s/.test(t)) return '';
  return t.replace(/\s*&gt;\s*/g, ' > ').replace(/＞/g, '>').replace(/\s+/g, ' ').trim();
}

/** `span[title]` có breadcrumb danh mục (鞋 > 女鞋 > …). */
function pickCategoryFromSpanTitles(root: Element): string {
  for (const sp of [...root.querySelectorAll('span[title]')]) {
    const title = (sp.getAttribute('title') || '').trim();
    const text = (sp.textContent || '').trim();
    const n = normalize1688CategoryBreadcrumb(title || text);
    if (n) return n;
  }
  return '';
}

/**
 * Layout không có/plugin cắt: `<span>类目:</span>` + `<span title="鞋 &gt; …">`.
 * Áp dụng cho `div[style*="flex"]` hoặc bất kỳ hàng có nhãn 类目 độc.
 */
function extract1688CategoryLeimuLabelRow(card: Element): string {
  for (const lb of card.querySelectorAll('span')) {
    const labelText = (lb.textContent || '').replace(/\s+/g, ' ').trim();
    if (!/^类目\s*[:：]?\s*$/u.test(labelText)) continue;
    let sib: Element | null = lb.nextElementSibling;
    while (sib && sib.tagName !== 'SPAN') sib = sib.nextElementSibling;
    if (!sib) continue;
    const raw = (sib.getAttribute('title') || sib.textContent || '').trim();
    const n = normalize1688CategoryBreadcrumb(raw);
    if (n) return n;
  }
  return '';
}

/** Danh mục (类目) — plugin-offer-search-card, hoặc hàng 「类目» + span title, hoặc span[title] breadcrumb trong card. */
function extract1688ListCategory(card: Element): string {
  const plugin = card.querySelector('[class*="plugin-offer-search-card"]');
  if (plugin) {
    const fromPlugin = pickCategoryFromSpanTitles(plugin);
    if (fromPlugin) return fromPlugin;
  }
  const fromLeimu = extract1688CategoryLeimuLabelRow(card);
  if (fromLeimu) return fromLeimu;
  return pickCategoryFromSpanTitles(card);
}

/** TB PC mới often tách ếInt/Float; không có text-price một khối. */
function extractPriceRaw(card: Element): string {
  const px1688 = extract1688OfferListPrice(card);
  if (px1688) return px1688;

  const legacy =
    card.querySelector('[class*="text-price"]') ||
    card.querySelector('[class*="price--"] [class*="text"]') ||
    card.querySelector('[class*="priceContainer"] [class*="text"]');
  const legacyTxt = (legacy?.textContent || '').replace(/\s+/g, ' ').trim();
  if (legacyTxt) return legacyTxt;

  const unit = (card.querySelector('[class*="unit--"], [class*="Unit--"]')?.textContent || '').trim();
  const intP = (
    card.querySelector('[class*="priceInt--"], [class*="PriceInt--"]')?.textContent || ''
  ).trim();
  const floatP = (
    card.querySelector('[class*="priceFloat--"], [class*="PriceFloat--"]')?.textContent || ''
  ).trim();
  const compact = `${unit}${intP}${floatP}`.trim().replace(/\s+/g, '');
  if (compact) return compact;

  const inner =
    card.querySelector('[class*="innerNormalPriceWrapper"]') ||
    card.querySelector('[class*="InnerNormalPriceWrapper"]') ||
    card.querySelector('[class*="priceWrapper--"]') ||
    card.querySelector('[class*="PriceWrapper"]') ||
    card.querySelector('[class*="priceSale"], [class*="PriceSale"], [class*="salePrice"], [class*="actualPrice"]') ||
    card.querySelector('[class*="commodityPrice"], [class*="CommodityPrice"]');
  const innerTxt = (inner?.textContent || '').replace(/\s+/g, ' ').trim();
  if (innerTxt) return innerTxt;

  /* Fallback cuối: hover giá tier — chỉ khi không có offer-price-row */
  const hoverPm = card.querySelector('.offer-hover-wrapper [class*="price-item"] > .text-main');
  return (hoverPm?.textContent || '').replace(/\s+/g, ' ').trim();
}

function extractShopName(card: Element): string {
  const scoped =
    card.querySelector('[class*="offer-shop-row"] a.offer-desc-item .desc-text') ||
    card.querySelector('[class*="offer-shop-row"] a[href*=".1688.com"][href*="shop"] .desc-text') ||
    card.querySelector('[class*="offer-shop-row"] [class*="col-left"] .desc-text');
  const nmScoped = (scoped?.textContent || '').replace(/\s+/g, ' ').trim();
  if (nmScoped.length >= 2 && nmScoped.length < 200) return nmScoped;

  const el =
    card.querySelector('[class*="offer-shop-row"] [class*="desc-text"]') ||
    card.querySelector('span[class*="shopNameText"]') ||
    card.querySelector('[class*="shopNameText--"]') ||
    card.querySelector('a[class*="shopName--"]') ||
    card.querySelector('[class*="shopName"], a[href*="view_shop.htm"] span') ||
    card.querySelector('[class*="shopInfo--"] [class*="shopName"]');
  return (el?.textContent || '').replace(/\s+/g, ' ').trim();
}

function normalizeTaobaoHref(href: string): string {
  const t = href.trim();
  if (!t) return '';
  if (t.startsWith('//')) return `https:${t}`;
  return t;
}

/** href trang chi tiết offer 1688 — không dùng Wangwang/air.1688, không trang「找相似」. */
function is1688ProductDetailHref(href: string): boolean {
  const h = href.trim().toLowerCase();
  if (!h || !h.includes('1688.com')) return false;
  if (h.includes('air.1688.com') || h.includes('ocms-fusion')) return false;
  if (h.includes('similar_search') || h.includes('selloffer/similar')) return false;
  if (/\/offer\/\d{6,}/i.test(h)) return true;
  if (h.includes('detail.m.1688.com') && /[?&]offerid=\d+/i.test(h)) return true;
  if (h.includes('detail.1688.com') && /[?&]offerid=\d+/i.test(h)) return true;
  return false;
}

function firstOfferDetailAnchorIn(card: Element): HTMLAnchorElement | null {
  const tryList =
    card.querySelectorAll<HTMLAnchorElement>('a.search-offer-wrapper[href], a[class*="search-offer-wrapper"][href]');
  for (const x of [...tryList]) {
    const h = (x.getAttribute('href') || '').trim();
    if (is1688ProductDetailHref(h)) return x;
  }
  const tiers = card.querySelectorAll<HTMLAnchorElement>(
    'a[href*="detail.m.1688.com"], a[href*="detail.1688.com/offer"], a[href*="1688.com/offer"], a[href*="1688.com"][href*="offerId="]',
  );
  for (const x of [...tiers]) {
    const h = (x.getAttribute('href') || '').trim();
    if (is1688ProductDetailHref(h)) return x;
  }
  return null;
}

/** URL trang chi tiết SP từ thẻ a card hoặc con (TB/Tmall/1688). */
function extractItemUrl(card: Element): string {
  if (card instanceof HTMLAnchorElement) {
    const selfHref = (card.getAttribute('href') ?? '').trim();
    if (selfHref && is1688ProductDetailHref(selfHref))
      return normalizeTaobaoHref(selfHref);
  }
  const a1688 = firstOfferDetailAnchorIn(card);
  const a =
    (card.matches?.('a[id^="item_id_"]') ? (card as HTMLAnchorElement) : null) ||
    card.querySelector<HTMLAnchorElement>('a[id^="item_id_"]') ||
    card.querySelector<HTMLAnchorElement>('a[href*="item.htm"][href*="id="]') ||
    card.querySelector<HTMLAnchorElement>('a[href*="detail.tmall.com"]') ||
    card.querySelector<HTMLAnchorElement>('a[href*="item.taobao.com/item.htm"]') ||
    card.querySelector<HTMLAnchorElement>(
      'a[href*="click.simba.taobao.com"], a[href*="simba.taobao.com"], a[href*="s.click.taobao.com"]',
    ) ||
    a1688 ||
    card.querySelector<HTMLAnchorElement>('a[href*="1688.com"]') ||
    card.querySelector<HTMLAnchorElement>('a[href*="taobao.com"]') ||
    card.querySelector<HTMLAnchorElement>('a[href*="tmall.com"]');
  const rawHref = (a?.getAttribute?.('href') ?? '').trim();
  const href =
    rawHref && /1688\.com/i.test(rawHref) && !is1688ProductDetailHref(rawHref)
      ? (() => {
          const alt = firstOfferDetailAnchorIn(card);
          return (alt?.getAttribute('href') || '').trim();
        })()
      : rawHref;
  return href ? normalizeTaobaoHref(href) : '';
}

/** Offer id trong URL 1688 (`/offer/…`, `offerId=` …). Dùng khi ghép link import 1688 PC. */
export function extractOfferId1688FromHref(href: string): string | null {
  const raw = href.trim();
  if (!raw || raw.length > 8192 || !/1688\.com/i.test(raw)) return null;
  try {
    const decoded = decodeURIComponent(raw.replace(/\+/g, ' '));
    const mPath = decoded.match(/\/offer\/(\d{6,})(?:\.html?)?(?:[?#]|$)/i);
    if (mPath?.[1]) return mPath[1];
    const mOfferParam = decoded.match(/(?:[&#?]|%26|%3F|%3D)offerId=(\d+)/i);
    if (mOfferParam?.[1]) return mOfferParam[1];
    const mOfferSnake = decoded.match(/(?:[&#?]|%26|%3F|%3D)offer_id=(\d+)/i);
    if (mOfferSnake?.[1]) return mOfferSnake[1];
  } catch {
    /* ignore */
  }
  return null;
}

/** `A`+(1688) hoặc `T`+(taobao/tmall), còn lại chỉ số. */
function formatListingItemIdPrefixed(numericOrEmpty: string, itemUrlAbsoluteOrEmpty: string): string {
  const raw = (numericOrEmpty || '').trim();
  if (!raw || !/^\d+$/.test(raw)) return raw;

  const u = (itemUrlAbsoluteOrEmpty || '').trim();
  if (!u) return raw;

  const low = u.toLowerCase();
  if (low.includes('1688.com')) return `A${raw}`;
  if (low.includes('taobao') || low.includes('tmall')) return `T${raw}`;
  return raw;
}

function looksLikeDomHtmlSnippet(s: string): boolean {
  return /<\s*(!DOCTYPE|html|body|div|table|a\b|span\b|img\b|section\b)/i.test(s.trim());
}

function nextNonBlankLineIndex(lines: string[], from: number): number {
  let j = Math.max(0, from);
  while (j < lines.length && !lines[j].trim()) j++;
  return j;
}

/**
 * Dòng log/export seller 1688 dạng text (vd. có «商品信息», `ID: 942397061385`, hàng tab giá, «类目»).
 */
function looksLike1688TextTablePaste(raw: string): boolean {
  const t = raw.trim();
  if (!t || t.length < 20) return false;
  if (looksLikeDomHtmlSnippet(t)) return false;
  const idLines = t.match(/^ID:\s*\d{6,}\s*$/gm) ?? [];
  if (idLines.length === 0) return false;
  if (/商品信息/.test(t) && /(?:价格|类目)/.test(t)) return true;
  if (/\t\d+\t/.test(t)) return true;
  return idLines.length >= 2;
}

/**
 * Parse paste bảng text 1688 (không phải HTML): tiêu đề · `ID: offerId` · dòng tab (giá cột đầu) · dòng mục · dòng nhãn phụ.
 */
export function parse1688TextTablePaste(raw: string): ParsedTaobaoCardRow[] {
  const text = raw.replace(/^\uFEFF/, '').replace(/\r\n/g, '\n');
  const lines = text.split('\n');
  const seen = new Set<string>();
  const out: ParsedTaobaoCardRow[] = [];

  for (let i = 0; i < lines.length; i++) {
    const idLineTrim = lines[i].trim();
    const idm = /^ID:\s*(\d{6,})\s*$/i.exec(idLineTrim);
    if (!idm) continue;
    const oid = idm[1];
    if (seen.has(oid)) continue;
    seen.add(oid);

    let title = '';
    for (let j = i - 1; j >= 0 && j >= i - 14; j--) {
      const t = lines[j].trim();
      if (!t) continue;
      if (/^\d+$/.test(t)) continue;
      if (/^ID:/i.test(t)) continue;
      if (/商品信息|(?:^|[\t])价格(?:[\t]|$)|类目|标签|代发价|月成交|发货时间|上架时间/.test(t)) continue;
      if (t.includes('\t') && t.split(/\t/).filter(Boolean).length >= 4) continue;
      title = t;
      break;
    }

    let price_raw = '';
    let tabParts: string[] = [];
    let tabIdx = nextNonBlankLineIndex(lines, i + 1);
    if (tabIdx < lines.length && lines[tabIdx].includes('\t')) {
      tabParts = lines[tabIdx].trim().split(/\t/).map((x) => x.trim());
      const pickPrice = (cell: string | undefined): cell is string =>
        !!cell && /^\d+(\.\d+)?$/.test(cell);
      if (pickPrice(tabParts[0])) price_raw = tabParts[0];
      else if (pickPrice(tabParts[1])) price_raw = tabParts[1];
    }

    let category = '';
    let extraTag = '';
    let catIdx = nextNonBlankLineIndex(lines, tabIdx + 1);
    if (catIdx < lines.length && lines[catIdx].includes('\t')) {
      catIdx = nextNonBlankLineIndex(lines, catIdx + 1);
    }
    if (catIdx < lines.length) {
      const l = lines[catIdx].trim();
      if (l && !l.includes('\t') && !/^ID:/i.test(l)) category = l;
    }
    const tagIdx = nextNonBlankLineIndex(lines, catIdx + 1);
    if (tagIdx < lines.length && category) {
      const l = lines[tagIdx].trim();
      if (l && !l.includes('\t') && !/^ID:/i.test(l)) extraTag = l;
    }

    const tagBits: string[] = [];
    if (category) tagBits.push(`类目：${category}`);
    if (extraTag) tagBits.push(extraTag);
    const tags = tagBits.join(' · ');

    let sales_text = '';
    if (tabParts.length > 3 && tabParts[2]) sales_text = `销量 ${tabParts[2]}`;

    const item_url = `https://detail.1688.com/offer/${oid}.html`;
    const item_id = formatListingItemIdPrefixed(oid, item_url);
    const price_cny_approx = parseApproxCnyAmountFromPriceRaw(price_raw);
    const cny_exchange_multiplier =
      price_cny_approx != null ? cnyExchangeMultiplierFromGrid(price_cny_approx) : null;

    out.push({
      row: out.length + 1,
      item_id,
      item_url,
      main_image_url: '',
      title: title || `Offer ${oid}`,
      shop_name: '',
      shop_name_chinese: '',
      chinese_name: (title || `Offer ${oid}`).trim(),
      shop_app_uid: '',
      seller_nick: '',
      tags,
      price_raw,
      price_link: item_url,
      sales_text,
      sku_thumb_urls: '',
      sku_thumb_count: 0,
      price_cny_approx,
      cny_exchange_multiplier,
      parsed_source: '1688_text_table',
    });
  }

  return withListingCnExportRows(out);
}

/** Giá trị `appUid` trong link shop (store.taobao.com/…/view_shop.htm?appUid=…). */
function extractShopAppUid(card: Element): string {
  const shopA =
    card.querySelector<HTMLAnchorElement>('a[class*="shopName--"]') ||
    card.querySelector<HTMLAnchorElement>('a[href*="view_shop.htm"]') ||
    card.querySelector<HTMLAnchorElement>('a[href*="store.taobao.com/shop"]');
  const raw = shopA?.getAttribute?.('href')?.trim();
  if (!raw) return '';
  const normalized = normalizeTaobaoHref(raw);
  try {
    return new URL(normalized).searchParams.get('appUid')?.trim() ?? '';
  } catch {
    const m = /[?&]appUid=([^&]+)/i.exec(raw);
    return m?.[1] ? decodeURIComponent(m[1].replace(/\+/g, ' ')) : '';
  }
}

function extractWwSellerNick(card: Element): string {
  const el = card.querySelector('[class*="ww-light"][data-nick]');
  return (el?.getAttribute('data-nick') ?? '').trim();
}

/** Các item id trong phạm vi — không mở rộng ô parse khi đã chứa nhiều sản phẩm khác nhau */
function distinctListingIdsInScope(scope: Element): Set<string> {
  const ids = new Set<string>();
  const addFromHref = (href: string) => {
    const raw = href.trim();
    if (!raw) return;
    const o1688 = extractOfferId1688FromHref(raw);
    if (o1688) ids.add(o1688);
    try {
      const decoded = decodeURIComponent(raw.replace(/\+/g, ' '));
      const hit = decoded.match(/(?:[&#?]|%26|%3F|%3D)id=(\d+)/);
      if (hit?.[1]) ids.add(hit[1]);
    } catch {
      const hit = raw.match(/(?:[&#?]|%26|%3F|%3D)id=(\d+)/);
      if (hit?.[1]) ids.add(hit[1]);
    }
  };
  scope.querySelectorAll('a[id^="item_id_"]').forEach((a) => {
    const m = /^item_id_(\d+)/i.exec(a.id.trim());
    if (m?.[1]) ids.add(m[1]);
  });
  scope
    .querySelectorAll(
      'a[href*="item.htm"], a[href*="detail.tmall.com"], a[href*="tmall.com/item"], a[href*="1688.com"]',
    )
    .forEach((a) => {
      const h = ((a as HTMLAnchorElement).getAttribute?.('href') ?? '').trim();
      if (h) addFromHref(h);
    });
  return ids;
}

/**
 * Khi root là `<a id="item_id_*">`, tiêu đề/tên shop/giá có thể nằm ở tổ tiên (cột mô tả bên cạnh ảnh).
 */
function expandListingCardScope(cardRoot: Element): Element {
  let expanded = cardRoot;
  let el: Element | null = cardRoot;
  for (let hop = 0; hop < 16 && el; hop++) {
    const parentEl: Element | null = el.parentElement;
    if (!parentEl) break;
    if (parentEl.getAttribute?.('data-tb-cards-parse-root') === '1') break;
    const ids = distinctListingIdsInScope(parentEl);
    if (ids.size > 1) break;
    expanded = parentEl;
    el = parentEl;
  }
  return expanded;
}

/**
 * 1688 list: một card thường bọc trong `<a.search-offer-wrapper href=…offerId>` nhưng bên trong còn
 * các `<a>` khác («找相似»…). Chuẩn HTML không cho `<a>` lồng `<a>` — DomParser đóng thẻ ngoài sớm,
 * nên chỉ còn `<a>` rất ngắn (thường có ảnh), còn tiêu đề/giá/shop là các sibling đứng sau.
 * Gom `seed + nextElementSibling` tới trước anchor offer tiếp theo trong list.
 */
function collect1688OfferSiblingChain(seed: Element, maxSiblings: number): Element[] {
  const chain: Element[] = [seed];
  let cur: Element | null = seed;
  for (let i = 0; i < maxSiblings; i++) {
    const nx: Element | null = cur?.nextElementSibling ?? null;
    if (!nx) break;
    if (
      nx.tagName === 'A' &&
      (nx.matches?.('[class*="search-offer-wrapper"]') || nx.matches?.('[class*="search-offer-item"]'))
    )
      break;
    chain.push(nx);
    cur = nx;
  }
  return chain;
}

function resolve1688ListingQueryRoots(card: Element, scope: Element, itemUrl: string): Element[] {
  const anchor1688 =
    /1688\.com/i.test(itemUrl.trim()) &&
    !!card.matches?.('a[class*="search-offer-wrapper"], a[class*="search-offer-item"]');
  if (!anchor1688) return [scope];
  /** Cây ô listing còn nguyên — không đụng sibling */
  if (scope.querySelector('[class*="offer-title-row"], [class*="title-text"]')) return [scope];
  return collect1688OfferSiblingChain(card, 56);
}

function qsFirstInRoots<R extends Element>(roots: Element[], selector: string): R | null {
  for (const r of roots) {
    const n = r.querySelector(selector);
    if (n) return n as R;
  }
  return null;
}

function titleSelectorWithinRoots(roots: Element[]): Element | null {
  for (const r of roots) {
    const t = titleSelectorWithin(r);
    if (t) return t;
  }
  return null;
}

function extract1688TitleLooseFallbackRoots(roots: Element[]): string {
  for (const r of roots) {
    const t = extract1688TitleLooseFallback(r);
    if (t) return t;
  }
  return '';
}

function extractShopNameRoots(roots: Element[]): string {
  for (const r of roots) {
    const s = extractShopName(r).trim();
    if (s.length >= 2 && s.length < 200) return s;
    if (s) return s;
  }
  return '';
}

function extractShopAppUidRoots(roots: Element[]): string {
  for (const r of roots) {
    const u = extractShopAppUid(r).trim();
    if (u) return u;
  }
  return '';
}

function extractWwSellerNickRoots(roots: Element[]): string {
  for (const r of roots) {
    const u = extractWwSellerNick(r).trim();
    if (u) return u;
  }
  return '';
}

function extract1688ListCategoryRoots(roots: Element[]): string {
  for (const r of roots) {
    const c = extract1688ListCategory(r).trim();
    if (c) return c;
  }
  return '';
}

function extractPriceRawRoots(roots: Element[]): string {
  for (const r of roots) {
    const p = extractPriceRaw(r).trim();
    if (p) return p;
  }
  return '';
}

function extractPriceLinkRoots(roots: Element[]): string {
  for (const r of roots) {
    const p = extractPriceLink(r).trim();
    if (p) return p;
  }
  return '';
}

function extractTitleFromMainImageAltRoots(roots: Element[]): string {
  for (const r of roots) {
    const t = extractTitleFromMainImageAlt(r).trim();
    if (t.length >= 5) return t;
  }
  return '';
}

function extractPriceLink(card: Element): string {
  const seeds: (Element | null)[] = [
    card.querySelector('[class*="innerNormalPriceWrapper"]'),
    card.querySelector('[class*="InnerNormalPriceWrapper"]'),
    card.querySelector('[class*="priceWrapper--"], [class*="PriceWrapper"]'),
    card.querySelector('[class*="priceInt--"], [class*="PriceInt"]'),
    card.querySelector('[class*="priceFloat--"], [class*="PriceFloat"]'),
    card.querySelector('[class*="text-price"], [class*="TextPrice"]'),
  ];
  for (const s of seeds) {
    if (!s) continue;
    const a = (s.closest('a[href]') || s.querySelector('a[href]')) as HTMLAnchorElement | null;
    const raw = (a?.getAttribute?.('href') ?? '').trim();
    if (!raw || raw.toLowerCase().startsWith('javascript')) continue;
    return normalizeTaobaoHref(raw);
  }
  return '';
}

function extractTitleFromMainImageAlt(card: Element): string {
  const img =
    card.querySelector<HTMLImageElement>('img.main-img') ||
    card.querySelector<HTMLImageElement>('[class*="offer-img-inner"] img') ||
    card.querySelector<HTMLImageElement>('img[class*="mainPic"]') ||
    card.querySelector<HTMLImageElement>('[class*="mainPicAndDesc"] img') ||
    card.querySelector<HTMLImageElement>('img[class*="mainImg"]') ||
    card.querySelector<HTMLImageElement>('[class*="mainImg"] img');
  const alt = (img?.getAttribute('alt') || '').trim().replace(/\s+/g, ' ');
  if (alt.length < 5) return '';
  if (/^(?:1\s*x\s*1|loading|淘宝|taobao)$/i.test(alt)) return '';
  return alt;
}

function extractRow(card: Element, idx: number): ParsedTaobaoCardRow | null {
  const numericId = extractTaobaoItemIdFromCardRoot(card) ?? '';
  const item_url = extractItemUrl(card);
  /** Một ô card listing thường rộng hơn chỉ `<a item_id>` để chứa cả khối mô tả + giá. */
  const scope = expandListingCardScope(card);
  const roots = resolve1688ListingQueryRoots(card, scope, item_url);
  /** TB PC ưu tiên ảnh trong mainPicAdapt (visible); mainImg trong imageSwitch có thể hidden. */
  const mainPicFirst =
    qsFirstInRoots<HTMLImageElement>(roots, 'img.main-img') ||
    qsFirstInRoots<HTMLImageElement>(
      roots,
      '[class*="offer-img-inner"] img[src*="cbu01"], [class*="offer-img-inner"] img[src*="alicdn"]',
    ) ||
    qsFirstInRoots<HTMLImageElement>(roots, 'img[class*="mainPic"]') ||
    qsFirstInRoots<HTMLImageElement>(
      roots,
      '[class*="mainPicAndDesc"] img[src*="alicdn"], [class*="mainPicAndDesc"] img[src*="gw.alicdn"]',
    );
  const secondary =
    qsFirstInRoots<HTMLImageElement>(roots, '[class*="mainImage"] img') ||
    qsFirstInRoots<HTMLImageElement>(roots, '[class*="MainImage"] img') ||
    qsFirstInRoots<HTMLImageElement>(roots, 'img[class*="mainImg"]') ||
    qsFirstInRoots<HTMLImageElement>(roots, '[class*="mainImg"] img');
  const mainImg = mainPicFirst || secondary;

  /** Ẩn thumbnail adapt */
  let mainSrc =
    mainImg?.getAttribute('src')?.trim() ||
    mainImg?.getAttribute('data-src')?.trim() ||
    mainImg?.src?.trim() ||
    '';
  if (!mainSrc) {
    const alt =
      qsFirstInRoots<HTMLImageElement>(
        roots,
        'img[class*="mainPic--"], [class*="mainPic"] img',
      ) || secondary;
    mainSrc =
      alt?.getAttribute('src')?.trim() ||
      alt?.getAttribute('data-src')?.trim() ||
      alt?.src?.trim() ||
      '';
  }

  const listing1688ish =
    /1688\.com/i.test(item_url) ||
    !!scope.closest?.('[class*="search-offer-wrapper"]') ||
    scope.matches?.('[class*="search-offer-wrapper"], [class*="search-offer-item"]');

  const titleEl = titleSelectorWithinRoots(roots);
  let title = extractTitle(titleEl);
  if (!title) title = extractTitleFromMainImageAltRoots(roots);
  if (!title && listing1688ish) title = extract1688TitleLooseFallbackRoots(roots);
  if (listing1688ish) title = dedupeRepeatedCnProductTitle(title);

  const shop_name = extractShopNameRoots(roots);
  const item_id = formatListingItemIdPrefixed(numericId, item_url);
  const shop_app_uid = extractShopAppUidRoots(roots);
  const seller_nick = extractWwSellerNickRoots(roots);

  const tagSpansLegacy = roots.flatMap((r) => [
    ...r.querySelectorAll('[class*="tags--"] span, [class*="Tags"] span'),
  ]);
  const tagSpansAbstract = roots.flatMap((r) => [
    ...r.querySelectorAll(
      '[class*="abstractWrapper"] [class*="text--"], [class*="descBox"] [class*="text--"]',
    ),
  ]);
  const cat1688 = extract1688ListCategoryRoots(roots);
  const tagParts = [
    ...(cat1688 ? [`类目：${cat1688}`] : []),
    ...[...tagSpansLegacy, ...tagSpansAbstract].map((s) => (s.textContent || '').trim()),
  ];
  const tags = [...new Set(tagParts)].filter(Boolean).join(' · ');

  const price_raw = extractPriceRawRoots(roots);
  const price_link = extractPriceLinkRoots(roots) || item_url || '';

  const qty1688 = qsFirstInRoots<Element>(
    roots,
    '[class*="offer-price-row"] [class*="col-desc_after"] .desc-text',
  );
  const qty1688Txt = (qty1688?.textContent || '').replace(/\s+/g, ' ').trim();
  let countEl: Element | null = null;
  if (!qty1688Txt) {
    for (const r of roots) {
      countEl =
        r.querySelector('[class*="realSales"]') ||
        r.querySelector('[class*="RealSales"]') ||
        r.querySelector('[class*="count--"]') ||
        r.querySelector('[class*="Count--"]') ||
        r.querySelector('[class*="sales"]');
      if (countEl) break;
    }
  }
  const sales_text =
    qty1688Txt || (countEl?.textContent || '').replace(/\s+/g, ' ').trim();

  const skuImgs = roots.flatMap((r) => [
    ...r.querySelectorAll<HTMLImageElement>(
      '[class*="skuItemImage"] img, [class*="SkuItemImage"] img, [class*="skuItem"] img',
    ),
  ]);
  const rawUrls: string[] = [];
  skuImgs.forEach((img) => {
    const s =
      (img.getAttribute('src') || img.getAttribute('data-src') || img.src || '').trim();
    if (s) uniquePush(rawUrls, s);
  });

  const cleaned = stripPlaceholderSkuImages(rawUrls);
  const finalSkus = cleaned.length > 0 ? cleaned : rawUrls;

  const sku_thumb_urls = finalSkus.join('\n');

  const price_cny_approx = parseApproxCnyAmountFromPriceRaw(price_raw);
  const cny_exchange_multiplier =
    price_cny_approx != null ? cnyExchangeMultiplierFromGrid(price_cny_approx) : null;

  if (!mainSrc && !title && !shop_name && !price_raw && finalSkus.length === 0 && !item_id) {
    return null;
  }

  return {
    row: idx + 1,
    item_id,
    item_url,
    main_image_url: mainSrc,
    title,
    shop_name,
    shop_name_chinese: shop_name.trim(),
    chinese_name: title.trim(),
    shop_app_uid,
    seller_nick,
    tags,
    price_raw,
    price_link,
    sales_text,
    sku_thumb_urls,
    sku_thumb_count: finalSkus.length,
    price_cny_approx,
    cny_exchange_multiplier,
  };
}

/** Path `/v/abb-…` hoặc `/v/{id}` từ href tương đối hoặc absolute hibox.mn. */
function hiboxListingPathFromHref(rawHref: string): string {
  const t = rawHref.trim();
  if (!t) return '';
  try {
    const urlStr =
      t.startsWith('//') ? `https:${t}` : /^https?:\/\//i.test(t) ? t : `https://hibox.mn${t.startsWith('/') ? t : `/${t}`}`;
    const u = new URL(urlStr);
    let p = u.pathname.replace(/\/+$/, '');
    if (!p.startsWith('/')) p = `/${p}`;
    return p;
  } catch {
    if (!t.startsWith('/')) return '';
    return t.split('?')[0].split('#')[0].replace(/\/+$/, '') || '/';
  }
}

/** Thẻ `<a>` trỏ tới trang SP Hibox (`/v/abb-{1688}` hoặc `/v/{taobao id}`). */
function collectHiboxGridAnchors(doc: Document): HTMLAnchorElement[] {
  const out: HTMLAnchorElement[] = [];
  for (const a of doc.querySelectorAll<HTMLAnchorElement>('a[href]')) {
    const h = (a.getAttribute('href') || '').trim();
    if (!h || h.length > 2048) continue;
    const path = hiboxListingPathFromHref(h);
    if (/^\/v\/abb-\d+$/i.test(path) || /^\/v\/\d+$/i.test(path)) {
      out.push(a);
    }
  }
  return out;
}

function extractRowFromHiboxGridCard(a: HTMLAnchorElement, idx: number): ParsedTaobaoCardRow | null {
  const rawHref = (a.getAttribute('href') || '').trim();
  const path = hiboxListingPathFromHref(rawHref);

  const abb = /^\/v\/abb-(\d+)$/i.exec(path);
  let item_url = '';
  let numericId = '';
  if (abb) {
    numericId = abb[1];
    item_url = `https://detail.1688.com/offer/${numericId}.html`;
  } else {
    const tb = /^\/v\/(\d+)$/i.exec(path);
    if (!tb) return null;
    numericId = tb[1];
    item_url = `https://item.taobao.com/item.htm?id=${numericId}`;
  }

  const item_id = formatListingItemIdPrefixed(numericId, item_url);

  const titleDiv =
    a.querySelector('.max-h-10.overflow-hidden.leading-5') ||
    a.querySelector('[class*="max-h-10"][class*="overflow-hidden"][class*="leading-5"]');
  let title = (titleDiv?.textContent || '').replace(/\s+/g, ' ').trim();

  const img =
    a.querySelector<HTMLImageElement>('img[src], img[data-src]') ||
    a.querySelector<HTMLImageElement>('img');
  let mainSrc =
    img?.getAttribute('src')?.trim() ||
    img?.getAttribute('data-src')?.trim() ||
    img?.src?.trim() ||
    '';
  mainSrc = normalizeTaobaoHref(mainSrc);
  if (!title) {
    const alt = (img?.getAttribute('alt') || '').trim().replace(/\s+/g, ' ');
    if (alt.length >= 3 && !/^(?:loading|1\s*x\s*1)$/i.test(alt)) title = alt;
  }

  const cur = a.querySelector('span.currency');
  const price_raw = (cur?.textContent || '').replace(/\s+/g, '').trim();

  const mntInt = parseHiboxDisplayPriceIntegerMnt(price_raw);
  const price_cny_approx =
    mntInt != null ? hiboxMntIntegerToApproxCny(mntInt) : parseApproxCnyAmountFromPriceRaw(price_raw);
  const cny_exchange_multiplier =
    price_cny_approx != null ? cnyExchangeMultiplierFromGrid(price_cny_approx) : null;

  if (!item_id && !item_url && !title && !mainSrc && !price_raw) return null;

  return {
    row: idx + 1,
    item_id,
    item_url,
    main_image_url: mainSrc,
    title,
    shop_name: '',
    shop_name_chinese: '',
    chinese_name: title.trim(),
    shop_app_uid: '',
    seller_nick: '',
    tags: '',
    price_raw,
    price_link: item_url,
    sales_text: '',
    sku_thumb_urls: '',
    sku_thumb_count: 0,
    price_hibox_mnt_integer: mntInt,
    price_cny_approx,
    cny_exchange_multiplier,
    parsed_source: 'hibox_grid',
  };
}

function parseHiboxListingGrid(doc: Document): ParsedTaobaoCardRow[] {
  const anchors = collectHiboxGridAnchors(doc);
  const seenPath = new Set<string>();
  const rows: ParsedTaobaoCardRow[] = [];
  for (const a of anchors) {
    const path = hiboxListingPathFromHref((a.getAttribute('href') || '').trim()).toLowerCase();
    if (!path || seenPath.has(path)) continue;
    seenPath.add(path);
    const row = extractRowFromHiboxGridCard(a, rows.length);
    if (row) rows.push(row);
  }
  return rows;
}

/**
 * Chuẩn hóa snippet khi không có <!DOCTYPE>/<html>; DomParser ổn định hơn với một gốc bọc khi BOM/cắt fragment.
 */
function coerceHtmlSnippetForParsing(raw: string): { html: string; wrapped: boolean } {
  let t = raw.replace(/^\uFEFF/, '').trim();
  t = patchBroken1688ListingPaste(t);
  if (/^\s*<!DOCTYPE\b/i.test(t) || /^\s*<html\b/i.test(t)) {
    return { html: t, wrapped: false };
  }
  return { html: `<div data-tb-cards-parse-root="1">${t}</div>`, wrapped: true };
}

/** Class layout card + anchor id listing PC (fallback khi đổi tên CSS module). */
const TB_CARD_ROOT_SEL = [
  '[class*="doubleCardWrapperAdapt"]',
  '[class*="DoubleCardWrapperAdapt"]',
  'a.search-offer-wrapper',
  'a[class*="search-offer-wrapper"]',
  'a[class*="search-offer-item"][href*="1688.com"]',
  'a[id^="item_id_"][href*="item.htm"]',
  'a[data-spm-protocol="i"][href*="item.taobao.com/item.htm"]',
  'a[data-spm-protocol="i"][href*="/item.htm"]',
].join(', ');

/** id sản phẩm trong listing TB (duplicate DOM / hover layers). */
function extractTaobaoItemIdFromCardRoot(root: Element): string | null {
  const fromDomId =
    root.matches?.('a[id^="item_id_"]') ? root : root.querySelector?.('a[id^="item_id_"]');
  if (fromDomId?.id) {
    const m = /^item_id_(\d+)/i.exec(fromDomId.id.trim());
    if (m?.[1]) return m[1];
  }

  const anchors: Element[] = [];
  const visit = (a: Element) => anchors.push(a);
  if (
    root.matches?.(
      'a[href*="item.htm"], a[href*="item.taobao"], a[href*="detail.tmall.com"], a[href*="tmall.com/item"], a[href*="1688.com"], a[href*="detail.m.1688.com"]',
    )
  )
    visit(root);
  root
    .querySelectorAll(
      'a[href*="item.htm"], a[href*="item.taobao"], a[href*="detail.tmall.com"], a[href*="tmall.com/item"], a[href*="1688.com"], a[href*="detail.m.1688.com"]',
    )
    .forEach(visit);

  const reHtmlId = /(?:[&#?]|%26|%3F|%3D)id=(\d+)/;
  /** Item link thường có id=item trên pathname search params */
  for (const a of anchors) {
    const href =
      (((a as HTMLAnchorElement).getAttribute?.('href') ?? '') ||
        (a instanceof HTMLAnchorElement ? a.href : '')) ||
      '';
    if (!href || href.length > 8192) continue;
    const oid1688 = extractOfferId1688FromHref(href);
    if (oid1688) return oid1688;
    try {
      const decoded = decodeURIComponent(href.replace(/\+/g, ' '));
      const hit = decoded.match(reHtmlId) || href.match(/[?&]id=(\d+)/);
      if (hit?.[1]) return hit[1];
    } catch {
      /* ignore */
    }
  }
  return null;
}

function cardRootScore(el: Element): number {
  const isTbWrapCard =
    el.matches?.('[class*="doubleCardWrapperAdapt"]') ||
    el.matches?.('[class*="DoubleCardWrapperAdapt"]');
  if (el.matches?.('a') && isTbWrapCard && el.matches?.('a[href*="item"]'))
    return 5;
  if (el.matches?.('a') && isTbWrapCard) return 4;
  if (el.matches?.('a[class*="search-offer-wrapper"], a[class*="search-offer-item"]')) return 4;
  if (
    el.matches?.(
      'a[id^="item_id_"], a[href*="item.htm"], a[href*="detail.tmall.com"], a[href*="detail.m.1688.com"], a[href*="1688.com"]',
    )
  )
    return 3;
  return el.matches?.('a') ? 2 : 1;
}

/** Khử trùng cùng sản phẩm — nếu không có id thì bỏ tổ tiên khi trong list đã có con. */
function normalizeCardRoots(roots: Element[]): Element[] {
  if (!roots.length) return roots;

  const byId = new Map<string, Element>();
  let noId: Element[] = [];

  const consider = (el: Element, idStr: string | null) => {
    if (!idStr) {
      noId.push(el);
      return;
    }
    const prev = byId.get(idStr);
    if (!prev || cardRootScore(el) > cardRootScore(prev)) byId.set(idStr, el);
  };

  for (const root of roots) consider(root, extractTaobaoItemIdFromCardRoot(root));

  const cmpDoc = (a: Element, b: Element) => {
    const pos = a.compareDocumentPosition(b);
    if (pos & Node.DOCUMENT_POSITION_PRECEDING) return 1;
    if (pos & Node.DOCUMENT_POSITION_FOLLOWING) return -1;
    return 0;
  };

  const withIdOrdered = [...byId.values()].sort(cmpDoc);

  noId.sort(cmpDoc);
  /** Giữ chỉ root «nhỏ nhất»: bỏ tổ tiên nếu vẫn còn con trong danh sách không-id */
  noId = noId.filter((el) => !noId.some((other) => other !== el && el.contains(other)));

  return [...withIdOrdered, ...noId];
}

function collectProductCardRoots(doc: Document): Element[] {
  const seen = new Set<Element>();
  const out: Element[] = [];

  const pushUnique = (el: Element) => {
    if (seen.has(el)) return;
    seen.add(el);
    out.push(el);
  };

  /**
   * TB PC: chủ yếu `<a … doubleCardWrapperAdapt–…>`. Thêm fallback `a#item_id_*` khi họ đổi tên
   * class hoặc khi chỉ có outerHTML không khớp chuỗi chính xác.
   */
  const tbAnchors = doc.querySelectorAll(TB_CARD_ROOT_SEL);
  if (tbAnchors.length > 0) {
    tbAnchors.forEach((el) => pushUnique(el));
    return normalizeCardRoots(out);
  }

  const cardSelectors = [
    '[class*="cardContainer"]',
    '[class*="CardContainer"]',
    '[class*="card_container"]',
    '[class*="productCard"]',
    '[class*="ProductCard"]',
    '[class*="goodsCard"]',
    '[class*="GoodsCard"]',
  ];
  for (const sel of cardSelectors) {
    doc.querySelectorAll(sel).forEach((el) => pushUnique(el));
  }

  if (out.length === 0) {
    doc.querySelectorAll('[class*="doubleCard--"]').forEach((el) => {
      if (
        el.closest('[class*="doubleCardWrapperAdapt"]') ||
        el.closest('[class*="DoubleCardWrapperAdapt"]')
      ) {
        return;
      }
      pushUnique(el);
    });
    doc
      .querySelectorAll(
        'a[href*="1688.com/offer"], a[href*="detail.1688.com/offer"], a[href*="detail.m.1688.com/page"], a[href*="offerId="][href*="1688.com"]',
      )
      .forEach((el) => {
        const h = ((el as HTMLAnchorElement).getAttribute('href') || '').trim();
        if (!h || !is1688ProductDetailHref(h)) return;
        pushUnique(el);
      });
  }

  if (out.length > 0) {
    return normalizeCardRoots(out);
  }

  /** Fallback: mỗi khối ảnh chính — parent của `…mainImage…` thường là cả card */
  doc
    .querySelectorAll(
      '[class*="mainImage"] img, [class*="MainImage"] img, [class*="mainImg"] img, img[class*="mainImg"]',
    )
    .forEach((img) => {
      const wrap =
        img.closest('[class*="mainImage"]') ||
        img.closest('[class*="MainImage"]') ||
        img.closest('[class*="mainImg"]') ||
        img.closest('[class*="imageSwitch"]');
      const root = wrap?.parentElement;
      if (root) {
        pushUnique(root);
      }
    });

  if (out.length > 0) {
    return normalizeCardRoots(out);
  }

  /** Fallback 2: tìm wrapper có cả ảnh alicdn + vùng giá/tiêu đề (HTML bị cắt mất lớp ngoài) */
  const candidates = doc.querySelectorAll(
    'img[src*="alicdn.com"], img[src*="gw.alicdn.com"], img[src*="img.alicdn.com"]',
  );
  candidates.forEach((img) => {
    if (!(img instanceof HTMLImageElement)) return;
    let el: Element | null = img.parentElement;
    for (let depth = 0; depth < 8 && el; depth++, el = el.parentElement) {
      const hasPriceOrTitle =
        el.querySelector(
          '[class*="text-price"], [class*="price--"], [class*="priceWrapper"], [class*="priceInt--"], [class*="innerNormalPriceWrapper"], [class*="offer-price-row"], [class*="offer-title-row"], [class*="title-text"], [class*="title--"], [class*="Title"]',
        ) !== null;
      if (hasPriceOrTitle) {
        pushUnique(el);
        break;
      }
    }
  });

  return normalizeCardRoots(out);
}

/** Một ô card sản phẩm trong listing — class CSS có hash nên chỉ khớp phần gốc. */
export function parseTaobaoListingHtml(html: string): ParsedTaobaoCardRow[] {
  const trimmed = html.replace(/^\uFEFF/, '');
  if (looksLike1688TextTablePaste(trimmed)) {
    const tableRows = parse1688TextTablePaste(trimmed);
    if (tableRows.length > 0) return tableRows;
  }

  if (typeof window === 'undefined' || typeof DOMParser === 'undefined') {
    return [];
  }

  const { html: snippet, wrapped } = coerceHtmlSnippetForParsing(trimmed);
  let doc = new DOMParser().parseFromString(snippet, 'text/html');

  let hiboxRows = parseHiboxListingGrid(doc);
  if (hiboxRows.length === 0 && wrapped) {
    doc = new DOMParser().parseFromString(trimmed.trim(), 'text/html');
    hiboxRows = parseHiboxListingGrid(doc);
  }
  if (hiboxRows.length > 0) {
    return withListingCnExportRows(hiboxRows);
  }

  /** Nếu đã bọc mà không tìm thấy ô — một số trình đọc được HTML «thô» tốt hơn fragment lớn. */
  let cards = collectProductCardRoots(doc);
  if (cards.length === 0 && wrapped) {
    doc = new DOMParser().parseFromString(trimmed.trim(), 'text/html');
    cards = collectProductCardRoots(doc);
  }

  const rows: ParsedTaobaoCardRow[] = [];

  cards.forEach((card, idx) => {
    const row = extractRow(card, idx);
    if (row) rows.push(row);
  });

  return withListingCnExportRows(rows);
}

export function rowsToCsv(
  rows: ParsedTaobaoCardRow[],
  vndPerOneCny: number = DEFAULT_VND_PER_CNY_FOR_LISTING_ESTIMATE,
): string {
  const headers = [
    'row',
    'item_id',
    'item_url',
    'main_image_url',
    'title',
    'shop_name',
    'tags',
    'price_raw',
    'price_cny_approx',
    'cny_exchange_multiplier',
    'vnd_per_cny_used',
    'approx_vnd',
  ] as const;

  const esc = (v: string) => {
    if (v.includes('"') || v.includes(',') || v.includes('\n') || v.includes('\r')) {
      return `"${v.replace(/"/g, '""')}"`;
    }
    return v;
  };

  const numOrEmpty = (v: number | null) => (v == null ? '' : String(v));

  const rate =
    typeof vndPerOneCny === 'number' && Number.isFinite(vndPerOneCny) && vndPerOneCny > 0
      ? vndPerOneCny
      : DEFAULT_VND_PER_CNY_FOR_LISTING_ESTIMATE;

  const lines = [headers.join(',')];
  for (const r of rows) {
    const approx = estimateListingVndRounded(r, rate);
    lines.push(
      [
        String(r.row),
        esc(r.item_id),
        esc(r.item_url),
        esc(r.main_image_url),
        esc(r.title),
        esc(r.shop_name),
        esc(r.tags),
        esc(r.price_raw),
        numOrEmpty(r.price_cny_approx),
        numOrEmpty(r.cny_exchange_multiplier),
        String(rate),
        numOrEmpty(approx),
      ].join(','),
    );
  }
  return lines.join('\r\n');
}
