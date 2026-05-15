/**
 * Khớp `backend/app/api/endpoints/import_1688.py`:
 * `_excel_export_columns_and_vi_headers` + `_excel_row_from_product`.
 * Dùng để hiển thị preview trong admin (vuốt ngang như file Excel).
 */

export type Import1688ExcelExportRow = Record<string, string | number>;

/** [khóa cột Excel, nhãn tiếng Việt — hàng 2 file xuất] */
export const IMPORT_1688_EXCEL_COLUMNS: ReadonlyArray<readonly [string, string]> = [
  ['id', 'Id sản phẩm'],
  ['sku', 'Mã sản phẩm'],
  ['origin', 'Xuất xứ'],
  ['brand', 'Thương hiệu'],
  ['name', 'Tên'],
  ['pro_content', 'Mô tả sản phẩm'],
  ['price', 'Giá'],
  ['shop_name', 'Tên shop'],
  ['shop_id', 'Shop id'],
  ['pro_lower_price', 'Sp giá thấp hơn'],
  ['pro_high_price', 'Sp giá cao hơn'],
  ['rating_group_id', 'Nhóm đánh giá'],
  ['question_group_id', 'Nhóm câu hỏi'],
  ['sizes', 'Size'],
  ['Variant', 'Biến thể'],
  ['gallery_images', 'Thư viện ảnh'],
  ['detail_images', 'Nội dung'],
  ['product_url', 'Link mặc định'],
  ['video_url', 'Link Video'],
  ['main_image', 'Link img'],
  ['likes_count', 'Thích'],
  ['purchases_count', 'Mua'],
  ['reviews_count', 'Lượt đánh giá'],
  ['questions_count', 'Lượt hỏi'],
  ['rating_score', 'Điểm đánh giá'],
  ['stock_quantity', 'Số lượng có thể mua'],
  ['deposit_required', 'Cần đặt cọc'],
  ['Main Category', 'Danh mục cấp 1'],
  ['Subcategory', 'Danh mục cấp 2'],
  ['Sub-subcategory', 'Danh mục cấp 3'],
  ['Material', 'Chất liệu'],
  ['Style', 'Kiểu dáng'],
  ['Color', 'màu sắc'],
  ['Occasion', 'Dịp'],
  ['Features', 'Tính năng'],
  ['Weight', 'Trọng lượng'],
  ['product_info', 'Thông tin sản phẩm'],
  ['chinese_name', 'Tên tiếng trung'],
  ['shop_name_chinese', 'Shop Trung Quốc'],
];

function jsonExcelCell(value: unknown): string {
  if (value === undefined || value === null) return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, (_, v) => (typeof v === 'bigint' ? String(v) : v));
  } catch {
    return String(value);
  }
}

/** Khớp `product_crud.deposit_require_to_excel_int` (frontend). */
export function depositRequireToExcelInt(raw: unknown, defaultVal = 1): number {
  if (raw === null || raw === undefined) return defaultVal;
  if (typeof raw === 'number' && Number.isNaN(raw)) return defaultVal;
  if (typeof raw === 'string') {
    const s = raw.trim().toLowerCase();
    if (s === '') return defaultVal;
    if (s === '0' || s === 'false' || s === 'no' || s === 'off' || s === 'f') return 0;
    if (s === '1' || s === 'true' || s === 'yes' || s === 'on' || s === 't') return 1;
    const n = Number.parseFloat(s);
    if (!Number.isFinite(n)) return defaultVal;
    return n !== 0 ? 1 : 0;
  }
  if (raw === false) return 0;
  if (raw === true) return 1;
  const n = Number(raw);
  if (!Number.isFinite(n)) return defaultVal;
  return n !== 0 ? 1 : 0;
}

function styleCellFromPd(pd: Record<string, unknown>): string {
  const v = pd.style;
  if (v === undefined || v === null) return '';
  return typeof v === 'string' ? v.trim() : String(v).trim();
}

/** Chuỗi ô Excel — tránh `unknown` là object làm TS báo lỗi. */
function excelStr(v: unknown): string {
  if (v == null) return '';
  if (typeof v === 'string') return v;
  if (typeof v === 'number' || typeof v === 'boolean') return String(v);
  return '';
}

function excelNum(v: unknown, fallback: number): number {
  if (typeof v === 'number' && Number.isFinite(v)) return v;
  if (typeof v === 'string' && v.trim()) {
    const n = Number.parseFloat(v.replace(/\s/g, '').replace(/,/g, ''));
    if (Number.isFinite(n)) return n;
  }
  return fallback;
}

/**
 * Một dòng giống `_excel_row_from_product` — để đối chiếu file Export Excel Import 1688.
 */
function emptyExcelExportRow(): Import1688ExcelExportRow {
  const empty: Import1688ExcelExportRow = {};
  const numericZeros = new Set([
    'price',
    'rating_group_id',
    'question_group_id',
    'likes_count',
    'purchases_count',
    'reviews_count',
    'questions_count',
    'rating_score',
  ]);
  for (const [k] of IMPORT_1688_EXCEL_COLUMNS) {
    if (k === 'deposit_required') empty[k] = 1;
    else if (k === 'stock_quantity') empty[k] = 500;
    else if (numericZeros.has(k)) empty[k] = 0;
    else empty[k] = '';
  }
  return empty;
}

export function excelExportRowFromProductData(
  productData: Record<string, unknown> | undefined,
): Import1688ExcelExportRow {
  if (!productData || typeof productData !== 'object') {
    return emptyExcelExportRow();
  }

  const pd = productData;
  const styleCell = styleCellFromPd(pd);

  return {
    id: pd.product_id != null ? String(pd.product_id) : '',
    sku: pd.code != null ? String(pd.code) : '',
    origin: '',
    brand: '',
    name: excelStr(pd.name),
    pro_content: excelStr(pd.description),
    price: excelNum(pd.price, 0),
    shop_name: '',
    shop_id: '',
    pro_lower_price: '',
    pro_high_price: '',
    rating_group_id: excelNum(pd.group_rating, 0),
    question_group_id: excelNum(pd.group_question, 0),
    sizes: jsonExcelCell(pd.sizes ?? []),
    Variant: jsonExcelCell(pd.colors ?? []),
    gallery_images: jsonExcelCell(pd.images ?? []),
    detail_images: jsonExcelCell(pd.gallery ?? []),
    product_url: excelStr(pd.link_default),
    video_url: excelStr(pd.video_link),
    main_image: excelStr(pd.main_image),
    likes_count: excelNum(pd.likes, 0),
    purchases_count: excelNum(pd.purchases, 0),
    reviews_count: excelNum(pd.rating_total, 0),
    questions_count: excelNum(pd.question_total, 0),
    rating_score: excelNum(pd.rating_point, 0),
    stock_quantity: excelNum(pd.available, 500),
    deposit_required: depositRequireToExcelInt(pd.deposit_require, 1),
    'Main Category': excelStr(pd.category),
    Subcategory: excelStr(pd.subcategory),
    'Sub-subcategory': excelStr(pd.sub_subcategory),
    Material: excelStr(pd.material),
    Style: styleCell,
    Color: excelStr(pd.color),
    Occasion: excelStr(pd.occasion),
    Features: jsonExcelCell(pd.features ?? []),
    Weight: excelStr(pd.weight),
    product_info: jsonExcelCell(pd.product_info ?? {}),
    chinese_name: excelStr(pd.chinese_name),
    shop_name_chinese: excelStr(pd.shop_name_chinese),
  };
}
