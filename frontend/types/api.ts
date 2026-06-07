// frontend/types/api.ts - CONSOLIDATED TYPES (ĐÃ SỬA)
export interface SiteSaleProductPricing {
  list_price?: number;
  display_price?: number;
  savings_amount?: number;
  percent?: number;
  phase?: 'teaser' | 'active' | null;
  expected_sale_price?: number;
  event_label?: string | null;
  event_date?: string | null;
  countdown_to?: string | null;
}

export interface SiteSaleCalendarState {
  enabled: boolean;
  phase?: 'teaser' | 'active' | null;
  event_date?: string | null;
  event_label?: string | null;
  discount_percent?: number;
  teaser_days?: number;
  active_start_at?: string | null;
  active_end_at?: string | null;
  countdown_to?: string | null;
}

export interface ProductColor {
  name: string;
  img?: string;
  value?: string;
}

export interface Product {
  id: number;
  product_id: string;
  code: string;
  name: string;
  /** Segment hoặc URL đầy đủ https://…/products/… (API trả chuẩn public). */
  slug: string;
  price: number;
  
  // MÔ TẢ SẢN PHẨM: từ cột F - pro_content
  description?: string;  // <-- THÊM DÒNG NÀY
  
  // Thư viện ảnh: từ cột P - gallery_images
  images?: string[];
  
  // Ảnh chi tiết: từ cột Q - detail_images
  gallery?: string[];
  
  main_image?: string;
  available?: number;
  /** Listing nhóm khi hết hàng (API attach_group_listing) */
  group_listing_path?: string;
  product_description?: string; // Giữ lại cho tương thích ngược
  origin?: string;
  brand_name?: string;
  chinese_name?: string;
  /** Tên shop Trung Quốc (Excel «Shop Trung Quốc») */
  shop_name_chinese?: string;
  status?: string;
  created_at: string;
  updated_at?: string;
  original_price?: number;
  site_sale?: SiteSaleProductPricing;
  shop_name?: string;
  shop_id?: string;
  pro_lower_price?: string;
  pro_high_price?: string;
  sizes?: string[];
  colors?: ProductColor[];
  /** URL ảnh từng màu (gallery màu / partner enrich). */
  color_image_urls?: string[];
  /** Biến thể màu có tên + ảnh (NanoAI / import). */
  color_variants?: NanoaiColorVariant[];
  content?: string[];
  link_default?: string;
  video_link?: string;
  likes?: number;
  purchases?: number;
  rating_total?: number;
  question_total?: number;
  rating_point?: number;
  group_rating?: number;
  group_question?: number;
  category?: string;
  subcategory?: string;
  sub_subcategory?: string;
  raw_category?: string;
  raw_subcategory?: string;
  gender?: string;
  style?: string;
  fashion_style?: string;
  material?: string;
  occasion?: string;
  features?: string[];
  deposit_require?: boolean;
  is_active?: boolean;
  meta_title?: string;
  meta_description?: string;
  meta_keywords?: string;
  /** Cột AK: Thông tin sản phẩm (JSON: product_info, specifications, variants, target_audience, market_info) */
  product_info?: ProductInfoJSON | string | null;
  /** UUID kho partner / Open Catalog (nếu backend trả về) — NanoAI chat ctx_inventory */
  inventory_id?: string | null;
  /** Slug danh mục taxonomy cấp 1 (slug gốc trong cây category) — trang / popup «chọn size». */
  category_level1_slug?: string | null;
  category_level2_slug?: string | null;
  source_stock_status?: 'unknown' | 'queued' | 'checking' | 'in_stock' | 'out_of_stock' | 'error' | string | null;
  source_stock_checked_at?: string | null;
  source_stock_next_check_at?: string | null;
  source_stock_error?: string | null;
  /** Nguồn 1688/Taobao báo hết hàng — chỉ còn đặt hàng kho thanh lý (nếu có). */
  source_oos?: boolean;
  /** Dòng kho thanh lý (product_id có /). */
  is_warehouse_clearance?: boolean;
  /** Biến thể kho thanh lý duyệt hoàn (block B trên PDP). */
  warehouse_variants?: WarehouseClearanceVariant[];
  warehouse_clearance?: {
    enabled?: boolean;
    discount_percent?: number;
  };
}

export interface WarehouseClearanceVariant {
  id: number;
  product_id: string;
  color?: string | null;
  size?: string | null;
  available: number;
  list_price: number;
  display_price: number;
  original_price: number;
  savings_amount: number;
  clearance_percent: number;
  main_image?: string | null;
  /** Ảnh từ cột Variant (img) khi import kho thanh lý. */
  color_image?: string | null;
}

export type WarehouseVariantPricing = {
  displayPrice: number;
  originalPrice: number;
  listPrice: number;
  percent: number;
  hasDiscount: boolean;
  savingsAmount: number;
};

/** Biến thể màu từ NanoAI (schema partner): tên + ảnh nguyên bản. */
export interface NanoaiColorVariant {
  name?: string | null;
  img?: string | null;
}

/** Kết quả từ NanoAI image-search / text-search (proxy backend) — khớp schema partner (có thể bổ sung sau enrich). */
export interface NanoaiSearchProduct {
  inventory_id?: string;
  name?: string;
  sku?: string | null;
  image_url?: string | null;
  product_url?: string | null;
  score?: number | null;
  /** Gợi ý giá dạng chuỗi từ NanoAI, ví dụ "199000 VND" */
  price_hint?: string | null;
  /** Ảnh màu / chi tiết từ kho (luôn là mảng; có thể rỗng) */
  color_image_urls?: string[];
  /** Biến thể màu có tên + URL ảnh (ưu tiên hiển thị thẻ màu) */
  color_variants?: NanoaiColorVariant[];
  /** Một số bản partner trả camelCase — ưu tiên dùng `color_image_urls` sau chuẩn hóa backend */
  colorImageUrls?: string[];
  colorVariants?: NanoaiColorVariant[];
  /** Số từ catalog shop khi enrich (fallback định dạng tiền tệ) */
  price?: number | null;
  /** Tên màu từ DB khi không có / ít ảnh màu */
  color_display?: string | null;
}

export interface NanoaiSearchResponse {
  ok?: boolean;
  products: NanoaiSearchProduct[];
  error?: string | null;
}

export interface ProductInfoJSON {
  product_info?: { sku?: string; name?: string; brand?: string; origin?: string; category?: { level_1?: string; level_2?: string; level_3?: string } };
  specifications?: Record<string, unknown> & { upper_material?: string; lining_material?: string; outsole_material?: string; insole_material?: string; construction?: string; toe_shape?: string; heel_height?: string; weight_grams?: number; wearing_style?: string; features?: string[] };
  variants?: { colors?: string[]; sizes?: number[] };
  target_audience?: { gender?: string; age_range?: string; style?: string };
  market_info?: { season?: string; export_ready?: boolean; lead_time_days?: string; main_sales_regions?: string[] };
}

export interface ProductReviewItem {
  id: number;
  /** Khách đăng nhập đánh giá sau khi mua — có id thì hiển thị tích xanh đã mua */
  user_id?: number | null;
  user_name: string;
  star: number;
  title: string;
  content: string;
  group: number;
  product_id: number | null;
  useful: number;
  user_has_voted?: boolean;
  display_created_at?: string | null;
  display_reply_at?: string | null;
  reply_name?: string;
  reply_content?: string;
  reply_at?: string | null;
  images?: string[];
  is_imported?: boolean;
  created_at?: string | null;
  /** True nếu là đánh giá của user đang đăng nhập (API sắp xếp lên đầu) */
  is_current_user?: boolean;
}

export interface ProductQuestionItem {
  id: number;
  user_name: string;
  content: string;
  group: number;
  product_id: number | null;
  useful: number;
  user_has_voted?: boolean;
  display_created_at?: string | null;
  display_reply_admin_at?: string | null;
  display_reply_user_one_at?: string | null;
  display_reply_user_two_at?: string | null;
  reply_admin_name?: string;
  reply_admin_content?: string;
  reply_admin_at?: string | null;
  reply_user_one_name?: string;
  reply_user_one_content?: string;
  reply_user_one_at?: string | null;
  /** Trả lời từ tài khoản đã mua (API reply) */
  reply_user_one_id?: number | null;
  reply_user_two_name?: string;
  reply_user_two_content?: string;
  reply_user_two_at?: string | null;
  reply_user_two_id?: number | null;
  reply_count: number;
  is_active: boolean;
  /** Câu hỏi import Excel — cho phép hiển thị tích xanh cạnh buyer reply có nội dung */
  is_imported?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  /** True khi khách đang xem là người hỏi (API chỉ đánh dấu cho chính họ) */
  is_my_question?: boolean;
}

export interface ProductListResponse {
  total: number;
  products: Product[];
  page: number;
  size: number;
  total_pages: number;
  /** true khi API home-feed sắp xếp theo lượt xem / yêu thích */
  personalized?: boolean;
  applied_query?: string | null;
  normalized_query?: string | null;
  suggested_queries?: string[];
  suggested_categories?: { name?: string; path?: string }[];
  redirect_path?: string;
  ai_processed?: boolean;
}

/** API GET /user-behavior/categories/popular-for-profile */
export interface PopularCategoryForProfile {
  name: string;
  purchases: number;
  product_count: number;
  view_hits?: number;
}

export type PopularCategoryHeroSource =
  | 'profile_gender'
  | 'recent_views'
  | 'cached_db'
  | 'cached_db_profile';

export type HeroCategoryAspectRatio = 'portrait' | 'landscape' | 'square';

/** Tile danh mục hero (cấp 1 / 2 / 3). */
export interface HeroCategoryTile {
  level: 1 | 2 | 3;
  name: string;
  short_name?: string;
  category: string;
  subcategory?: string | null;
  sub_subcategory?: string | null;
  product_count: number;
  purchases: number;
  ctr_hint: string;
  aspect_ratio: HeroCategoryAspectRatio;
  image_url?: string | null;
  col_span?: number;
  row_span?: number;
}

export interface HeroCategoryTilesResponse {
  tiles: HeroCategoryTile[];
  gender_label: string | null;
  heading: string | null;
  subtitle: string | null;
  anchor_category: string | null;
  source: PopularCategoryHeroSource;
}

/** GET /categories/from-products/catalog-tiles — lưới /danh-muc */
export interface CategoryCatalogTilesResponse {
  tiles: HeroCategoryTile[];
}

/** GET /user-behavior/categories/inferred-gender — ưu tiên sắp menu danh mục */
export interface InferredCategoryGenderResponse {
  gender_suffix: 'Nam' | 'Nữ' | null;
  gender_label: 'Nam' | 'Nữ' | null;
  source: PopularCategoryHeroSource;
  recent_view_count?: number;
}

/** API /user-behavior/products/viewed-by-same-age-gender */
export type SameAgeGenderCohortMode =
  | 'requires_login'
  | 'profile_incomplete'
  | 'exact_cohort'
  | 'gender_peers'
  | 'popular_fallback';

/** API /user-behavior/products/home-recommendation-block */
export interface HomeRecommendationBlockResponse {
  same_shop_products: Product[];
  same_shop_total: number;
  same_shop_seed: number | null;
  same_shop_can_load_more: boolean;
  same_age_gender_products: Product[];
  same_age_gender_cohort_mode: SameAgeGenderCohortMode;
  mixed_recommendation_products: Product[];
  cohort_badge_product_ids: number[];
}

/** API GET /user-behavior/home/recommendation-snapshot */
export interface HomeRecommendationSnapshotResponse {
  found: boolean;
  computed_at?: string | null;
  recommendation?: HomeRecommendationBlockResponse;
  main_feed?: {
    products: Product[];
    total: number;
    personalized: boolean;
    page?: number;
    size?: number;
  };
}

/** Danh mục cấp 3 (cột AD) */
export interface CategoryLevel3 {
  name: string;
  slug?: string;
}

/** Danh mục cấp 2 (cột AC) */
export interface CategoryLevel2 {
  name: string;
  slug?: string;
  children: CategoryLevel3[];
}

/** Danh mục cấp 1 (cột AB) - cây từ sản phẩm */
export interface CategoryLevel1 {
  name: string;
  slug?: string;
  children: CategoryLevel2[];
}

/** Thông tin danh mục theo path (SEO, by-path API) */
export interface CategoryByPath {
  level: 1 | 2 | 3;
  name: string;
  full_name: string;
  breadcrumb_names: string[];
  product_count: number;
}

export interface ProductSearchParams {
  page?: number;
  skip?: number;
  limit?: number;
  category?: string;
  sub_subcategory?: string;
  q?: string;
  query?: string;
  subcategory?: string;
  shop_name?: string;
  shop_id?: string;
  chinese_name?: string;
  shop_name_chinese?: string;
  pro_lower_price?: string;
  pro_high_price?: string;
  gender?: string;
  style?: string;
  fashion_style?: string;
  material?: string;
  brand?: string;
  origin?: string;
  min_price?: number;
  max_price?: number;
  /** Lọc size (JSON `sizes`) — khớp backend */
  size?: string;
  /** Lọc màu — khớp backend */
  color?: string;
  /** Lọc kiểu phổ thông tự rút từ tên/thông tin sản phẩm */
  style_tag?: string;
  /** Sắp xếp: random | id_desc | views_desc | newest | oldest | purchases_desc */
  sort?: string;
  /** Cache-bust khi sort=random (client gửi mỗi lần F5/tìm lại) */
  search_refresh?: string;
  /** Bỏ COUNT(*) — PDP / khối liên quan */
  skip_total?: boolean;
  /** Gắn biến thể kho thanh lý (storefront; admin không dùng) */
  include_warehouse_clearance?: boolean;
  /** Chỉ SP hàng thanh lý kho — trang /kho-sale */
  warehouse_clearance_only?: boolean;
  min_rating?: number;
  is_active?: boolean;
  has_deposit?: boolean;
  sort_by?: string;
  in_stock?: boolean;
}

export interface CartItem {
  id: number;
  product_id: number;
  quantity: number;
  selected_size?: string;
  selected_color?: string;
  unit_price: number;
  total_price: number;
  added_at: string;
  requires_deposit?: boolean;
  product_data: {
    id: number;
    product_id: string;
    name: string;
    price: number;
    main_image?: string;
    brand_name?: string;
    original_price?: number;
    available?: number;
    deposit_require?: boolean;
  };
}

export interface Cart {
  id: number;
  user_id: number;
  total_items: number;
  total_price: number;
  items: CartItem[];
  created_at?: string;
  updated_at?: string;
  requires_deposit?: boolean;
  // Loyalty fields
  loyalty_discount_percent?: number;
  loyalty_discount_amount?: number;
  final_price?: number;
  loyalty_tier_name?: string;
  birthday_discount_active?: boolean;
  birthday_discount_percent?: number;
  birthday_discount_amount?: number;
  birthday_next_date?: string | null;
}

export interface CartResponse {
  items: CartItem[];
  total_items: number;
  total_price: number;
}

export interface OrderItem {
  id: number;
  product_id: number;
  product_name: string;
  product_image?: string;
  quantity: number;
  price: number;
  selected_size?: string;
  selected_color?: string;
}

export interface Order {
  id: number;
  user_id: number;
  total_amount: number;
  status: string;
  payment_method: string;
  payment_status: string;
  shipping_address: string;
  shipping_phone?: string;
  shipping_name?: string;
  note?: string;
  created_at: string;
  items: OrderItem[];
}

export interface Category {
  id: number;
  name: string;
  slug: string;
  icon?: string;
  description?: string;
  parent_id?: number;
  is_active?: boolean;
  product_count?: number;
  created_at?: string;
}

export interface User {
  id: number;
  phone: string;
  email?: string;
  full_name: string;
  address?: string;
  is_active: boolean;
  created_at: string;
}

/** Địa chỉ giao hàng trong sổ địa chỉ */
export interface UserAddress {
  id: number;
  user_id: number;
  full_name: string;
  phone: string;
  province?: string | null;
  district?: string | null;
  ward?: string | null;
  street_address: string;
  is_default: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AddressCreateInput {
  full_name: string;
  phone: string;
  province?: string;
  district?: string;
  ward?: string;
  street_address: string;
  is_default?: boolean;
}

export interface AddressUpdateInput {
  full_name?: string;
  phone?: string;
  province?: string;
  district?: string;
  ward?: string;
  street_address?: string;
  is_default?: boolean;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface SimpleProductResponse {
  found: boolean;
  product?: Product;
  products?: Product[];
  message?: string;
}

export interface ImportResults {
  total: number;
  success: number;
  updated: number;
  errors: string[];
  skipped: string[];
}

export interface ImportResponse {
  message: string;
  results: ImportResults;
}

export interface FiltersResponse {
  categories: string[];
  brands: string[];
  materials: string[];
  styles: string[];
  fashion_styles: string[];
  genders: string[];
  origins: string[];
  occasions: string[];
}
