/**
 * Khớp backend: `import_1688.export_import_1688_draft_excel` + `_excel_row_from_product`
 * và file `sample_import_template.xlsx` (37 cột A–AK; row 1 key EN, row 2 nhãn VI).
 */
export type DraftExcelColumnKey = (typeof DRAFT_IMPORT_EXCEL_COLUMNS)[number]['key'];

export const DRAFT_IMPORT_EXCEL_COLUMNS = [
  { key: 'id', labelVi: 'Id sản phẩm', sampleHint: 'A746204251298a188b0038' },
  { key: 'sku', labelVi: 'Mã sản phẩm', sampleHint: 'B0038' },
  { key: 'origin', labelVi: 'Xuất xứ', sampleHint: 'Việt Nam' },
  { key: 'brand', labelVi: 'Thương hiệu', sampleHint: 'SHTDC' },
  {
    key: 'name',
    labelVi: 'Tên',
    sampleHint: 'Giày Tây Oxford Nam Da Thật Mũi Nhọn…',
  },
  {
    key: 'pro_content',
    labelVi: 'Mô tả sản phẩm',
    sampleHint: 'Giày Tây Oxford Nam Da Thật là một lựa chọn…',
  },
  { key: 'price', labelVi: 'Giá', sampleHint: '2260000' },
  { key: 'shop_name', labelVi: 'Tên shop', sampleHint: 'giày tây nam shtdc' },
  { key: 'shop_id', labelVi: 'Shop id', sampleHint: 'nam G05' },
  { key: 'pro_lower_price', labelVi: 'Sp giá thấp hơn', sampleHint: 'giày dép nam G04' },
  { key: 'pro_high_price', labelVi: 'Sp giá cao hơn', sampleHint: 'giày dép nam G06' },
  { key: 'rating_group_id', labelVi: 'Nhóm đánh giá', sampleHint: '90' },
  { key: 'question_group_id', labelVi: 'Nhóm câu hỏi', sampleHint: '99' },
  {
    key: 'sizes',
    labelVi: 'Size',
    sampleHint: '["37","38",…] JSON mảng',
  },
  {
    key: 'Variant',
    labelVi: 'Biến thể',
    sampleHint: '[{"name":"Màu đen","img":"https://img.alicdn.com/…"}]',
  },
  {
    key: 'gallery_images',
    labelVi: 'Thư viện ảnh',
    sampleHint: '["https://img.alicdn.com/…"]',
  },
  {
    key: 'detail_images',
    labelVi: 'Nội dung',
    sampleHint: '["https://188.com.vn/uploads/…"]',
  },
  { key: 'product_url', labelVi: 'Link mặc định', sampleHint: 'https://188.com.vn/product/B0038' },
  {
    key: 'video_url',
    labelVi: 'Link Video',
    sampleHint: 'https://cloud.video.taobao.com/play/u/…/….mp4',
  },
  {
    key: 'main_image',
    labelVi: 'Link img',
    sampleHint: '//img.alicdn.com/img/ibank/…-cib.jpg',
  },
  { key: 'likes_count', labelVi: 'Thích', sampleHint: '100' },
  { key: 'purchases_count', labelVi: 'Mua', sampleHint: '81' },
  { key: 'reviews_count', labelVi: 'Lượt đánh giá', sampleHint: '72' },
  { key: 'questions_count', labelVi: 'Lượt hỏi', sampleHint: '90' },
  { key: 'rating_score', labelVi: 'Điểm đánh giá', sampleHint: '4.9' },
  { key: 'stock_quantity', labelVi: 'Số lượng có thể mua', sampleHint: '500' },
  { key: 'deposit_required', labelVi: 'Cần đặt cọc', sampleHint: '1' },
  { key: 'Main Category', labelVi: 'Danh mục cấp 1', sampleHint: 'Giày dép Nam' },
  { key: 'Subcategory', labelVi: 'Danh mục cấp 2', sampleHint: 'Giày tây Nam' },
  {
    key: 'Sub-subcategory',
    labelVi: 'Danh mục cấp 3',
    sampleHint: 'Giày Oxford Nam',
  },
  { key: 'Material', labelVi: 'Chất liệu', sampleHint: 'Da bò' },
  { key: 'Style', labelVi: 'Kiểu dáng', sampleHint: 'Dây buộc' },
  { key: 'Color', labelVi: 'màu sắc', sampleHint: 'Đen, Xanh' },
  { key: 'Occasion', labelVi: 'Dịp', sampleHint: 'Lễ cưới, dự tiệc' },
  { key: 'Features', labelVi: 'Tính năng', sampleHint: 'Nâng đế, tăng cao' },
  { key: 'Weight', labelVi: 'Trọng lượng', sampleHint: '500g' },
  {
    key: 'product_info',
    labelVi: 'Thông tin sản phẩm',
    sampleHint: '{ "product_info": {…}, "specifications": {…} }',
  },
] as const;

function colLetter(index1Based: number): string {
  let n = index1Based;
  let s = '';
  while (n > 0) {
    const r = (n - 1) % 26;
    s = String.fromCharCode(65 + r) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
}

export function draftExcelColumnLetter(index: number): string {
  return colLetter(index + 1);
}

function j(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

/** Khớp `deposit_require_to_excel_int` backend: 1/0; thiếu field → 1 (mặc định cần cọc). */
export function depositRequireToExcelCell(raw: unknown): '1' | '0' {
  if (raw === undefined || raw === null) return '1';
  if (typeof raw === 'boolean') return raw ? '1' : '0';
  if (typeof raw === 'number') return raw !== 0 ? '1' : '0';
  const s = String(raw).trim().toLowerCase();
  if (s === '' || s === 'nan') return '1';
  if (['0', 'false', 'no', 'off', 'f'].includes(s)) return '0';
  if (['1', 'true', 'yes', 'on', 't'].includes(s)) return '1';
  const n = Number(s);
  if (!Number.isNaN(n)) return n !== 0 ? '1' : '0';
  return '1';
}

/**
 * Giống `_excel_row_from_product` (import_1688.py) — dùng hiển thị đối chiếu file mẫu.
 */
export function productDataToDraftExcelRow(
  productData: Record<string, unknown> | undefined | null,
): Record<DraftExcelColumnKey, string> {
  const empty = Object.fromEntries(
    DRAFT_IMPORT_EXCEL_COLUMNS.map((c) => [c.key, '']),
  ) as Record<DraftExcelColumnKey, string>;
  if (!productData || typeof productData !== 'object') return empty;

  const p = productData;

  return {
    id: String(p.product_id ?? ''),
    sku: String(p.code ?? ''),
    origin: String(p.origin ?? ''),
    brand: String(p.brand_name ?? ''),
    name: String(p.name ?? ''),
    pro_content: String(p.description ?? ''),
    price: String(p.price ?? ''),
    shop_name: String(p.shop_name ?? ''),
    shop_id: String(p.shop_id ?? ''),
    pro_lower_price: String(p.pro_lower_price ?? ''),
    pro_high_price: String(p.pro_high_price ?? ''),
    rating_group_id: String(p.group_rating ?? ''),
    question_group_id: String(p.group_question ?? ''),
    sizes: j(p.sizes),
    Variant: j(p.colors),
    gallery_images: j(p.images),
    detail_images: j(p.gallery),
    product_url: String(p.link_default ?? ''),
    video_url: String(p.video_link ?? ''),
    main_image: String(p.main_image ?? ''),
    likes_count: String(p.likes ?? ''),
    purchases_count: String(p.purchases ?? ''),
    reviews_count: String(p.rating_total ?? ''),
    questions_count: String(p.question_total ?? ''),
    rating_score: String(p.rating_point ?? ''),
    stock_quantity: String(p.available ?? 500),
    deposit_required: depositRequireToExcelCell(p.deposit_require),
    'Main Category': String(p.category ?? ''),
    Subcategory: String(p.subcategory ?? ''),
    'Sub-subcategory': String(p.sub_subcategory ?? ''),
    Material: String(p.material ?? ''),
    Style: String(p.style ?? ''),
    Color: String(p.color ?? ''),
    Occasion: String(p.occasion ?? ''),
    Features: j(p.features),
    Weight: String(p.weight ?? ''),
    product_info: j(p.product_info),
  };
}

export function shortenPreview(text: string, maxLen = 160): string {
  const t = (text || '').replace(/\s+/g, ' ').trim();
  if (t.length <= maxLen) return t;
  return `${t.slice(0, maxLen - 1)}…`;
}
