// frontend/types/api.ts - CONSOLIDATED TYPES (ĐÃ SỬA)
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
  product_description?: string; // Giữ lại cho tương thích ngược
  origin?: string;
  brand_name?: string;
  chinese_name?: string;
  status?: string;
  created_at: string;
  updated_at?: string;
  original_price?: number;
  shop_name?: string;
  shop_id?: string;
  pro_lower_price?: string;
  pro_high_price?: string;
  sizes?: string[];
  colors?: ProductColor[];
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
}

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
  reply_user_two_name?: string;
  reply_user_two_content?: string;
  reply_user_two_at?: string | null;
  reply_count: number;
  is_active: boolean;
  created_at?: string | null;
  updated_at?: string | null;
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

/** API /user-behavior/products/viewed-by-same-age-gender */
export type SameAgeGenderCohortMode =
  | 'requires_login'
  | 'profile_incomplete'
  | 'exact_cohort'
  | 'gender_peers'
  | 'popular_fallback';

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
